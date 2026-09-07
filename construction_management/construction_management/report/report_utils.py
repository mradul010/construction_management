from functools import lru_cache

import frappe
from frappe import _
from frappe.utils import cint, flt, fmt_money, formatdate

from construction_management.construction_management.advance_management import (
	get_project_advance_summary,
)


INTERNAL_REPORT_ROLES = {
	"System Manager",
	"Construction Manager",
	"Projects Manager",
	"Project Manager",
	"Estimator",
}

STANDARD_FIELDS = {
	"name",
	"owner",
	"creation",
	"modified",
	"modified_by",
	"docstatus",
	"idx",
	"parent",
	"parenttype",
	"parentfield",
}


def parse_filters(filters=None):
	if isinstance(filters, str):
		filters = frappe.parse_json(filters) or {}
	return frappe._dict(filters or {})


def ensure_report_access():
	if frappe.session.user == "Administrator":
		return

	if set(frappe.get_roles()) & INTERNAL_REPORT_ROLES:
		return

	frappe.throw(_("Not permitted"), frappe.PermissionError)


@lru_cache(maxsize=None)
def doctype_has_field(doctype, fieldname):
	if fieldname in STANDARD_FIELDS:
		return True

	try:
		return bool(frappe.get_meta(doctype).has_field(fieldname))
	except Exception:
		return False


@lru_cache(maxsize=None)
def table_exists(doctype):
	try:
		return bool(frappe.db.table_exists(doctype))
	except Exception:
		return False


def existing_fields(doctype, fields):
	return [fieldname for fieldname in fields if doctype_has_field(doctype, fieldname)]


def sql_field(doctype, alias, fieldname, default="NULL"):
	if doctype_has_field(doctype, fieldname):
		return f"{alias}.`{fieldname}`"
	return default


def is_checked(value):
	return value not in (None, "", "0", 0, False)


def get_list(doctype, filters=None, fields=None, order_by=None):
	fields = existing_fields(doctype, fields or ["name"]) or ["name"]
	kwargs = {
		"filters": filters or {},
		"fields": fields,
		"limit_page_length": 0,
	}
	if order_by:
		kwargs["order_by"] = order_by

	return frappe.get_list(doctype, **kwargs)


def filter_rows_by_dates(rows, filters, from_field="billing_period_from", to_field="billing_period_to"):
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")

	if not from_date and not to_date:
		return rows

	filtered = []
	for row in rows:
		row_date = row.get(to_field) or row.get(from_field) or row.get("creation")
		if not row_date:
			filtered.append(row)
			continue
		row_date = str(row_date)[:10]
		if from_date and row_date < str(from_date):
			continue
		if to_date and row_date > str(to_date):
			continue
		filtered.append(row)

	return filtered


def format_period(from_date, to_date):
	if from_date and to_date:
		return f"{formatdate(from_date)} - {formatdate(to_date)}"
	if from_date:
		return formatdate(from_date)
	if to_date:
		return formatdate(to_date)
	return ""


def safe_percent(value, total):
	total = flt(total)
	return (flt(value) / total * 100) if total else 0


def group_by(rows, key):
	grouped = {}
	for row in rows:
		grouped.setdefault(row.get(key), []).append(row)
	return grouped


def sum_field(rows, fieldname):
	return sum(flt(row.get(fieldname)) for row in rows)


def average_field(rows, fieldname):
	values = [flt(row.get(fieldname)) for row in rows]
	return sum(values) / len(values) if values else 0


def first_currency(rows):
	for row in rows:
		if row.get("currency"):
			return row.get("currency")
	return None


def normalize_currency_code(currency):
	return (currency or "").strip().upper()


def format_currency_with_code(value, currency, precision=2):
	currency = normalize_currency_code(currency)
	amount = fmt_money(flt(value), precision=precision, currency=None)
	return f"{currency} {amount}" if currency else amount


def summary_metric(label, value, datatype="Currency", currency=None, indicator="Blue"):
	if datatype == "Currency":
		return {
			"value": format_currency_with_code(value, currency),
			"label": _(label),
			"datatype": "Data",
			"indicator": indicator,
		}

	metric = {
		"value": flt(value),
		"label": _(label),
		"datatype": datatype,
		"indicator": indicator,
	}
	if currency:
		metric["currency"] = currency
	return metric


def get_project_rows(filters):
	project_fields = ["name", "project_name", "customer", "sales_order", "company", "status", "current_boq"]
	project_filters = {}

	if filters.get("project"):
		project_filters["name"] = filters.project
	if filters.get("company") and doctype_has_field("Project", "company"):
		project_filters["company"] = filters.company
	if filters.get("customer") and doctype_has_field("Project", "customer"):
		project_filters["customer"] = filters.customer
	if filters.get("sales_order") and doctype_has_field("Project", "sales_order"):
		project_filters["sales_order"] = filters.sales_order
	if filters.get("project_status") and doctype_has_field("Project", "status"):
		project_filters["status"] = filters.project_status

	return get_list(
		"Project",
		filters=project_filters,
		fields=project_fields,
		order_by="modified desc",
	)


def get_boq_rows(filters, fields=None, project_names=None, include_cancelled=False):
	fields = fields or [
		"name",
		"project",
		"sales_order",
		"client",
		"currency",
		"global_margin_percent",
		"revision_no",
		"revision_status",
		"is_active_revision",
		"total_cost",
		"grand_total",
		"status",
		"creation",
		"modified",
		"docstatus",
		"original_boq",
		"parent_boq",
		"revision_reason",
		"superseded_by",
	]
	boq_filters = {}

	if not include_cancelled:
		boq_filters["docstatus"] = ["!=", 2]
	if project_names is not None:
		if not project_names:
			return []
		boq_filters["project"] = ["in", project_names]
	elif filters.get("project"):
		boq_filters["project"] = filters.project
	if filters.get("boq"):
		boq_filters["name"] = filters.boq
	if filters.get("sales_order") and doctype_has_field("BOQ", "sales_order"):
		boq_filters["sales_order"] = filters.sales_order
	if filters.get("customer") and doctype_has_field("BOQ", "client"):
		boq_filters["client"] = filters.customer
	if filters.get("status") and doctype_has_field("BOQ", "status"):
		boq_filters["status"] = filters.status
	if filters.get("revision_status") and doctype_has_field("BOQ", "revision_status"):
		boq_filters["revision_status"] = filters.revision_status
	if filters.get("active_revision") not in (None, "") and doctype_has_field("BOQ", "is_active_revision"):
		boq_filters["is_active_revision"] = 1 if is_checked(filters.active_revision) else 0

	return get_list(
		"BOQ",
		filters=boq_filters,
		fields=fields,
		order_by="project asc, revision_no desc, modified desc",
	)


def get_ra_bill_rows(filters, fields=None, project_names=None, submitted_only=False, require_invoice=False):
	fields = fields or [
		"name",
		"bill_no",
		"ra_bill_no",
		"project",
		"boq",
		"sales_order",
		"customer",
		"currency",
		"billing_period_from",
		"billing_period_to",
		"status",
		"gross_amount",
		"retention_percent",
		"retention_amount",
		"net_payable",
		"total_advance_received",
		"previously_recovered_advance",
		"remaining_advance_before_current_bill",
		"advance_recovery_percent",
		"proposed_advance_recovery",
		"actual_advance_recovered",
		"remaining_advance_after_current_bill",
		"total_advance",
		"sales_invoice",
		"creation",
		"modified",
		"docstatus",
	]
	rb_filters = {}

	rb_filters["docstatus"] = 1 if submitted_only else ["!=", 2]
	if project_names is not None:
		if not project_names:
			return []
		rb_filters["project"] = ["in", project_names]
	elif filters.get("project"):
		rb_filters["project"] = filters.project
	if filters.get("ra_bill"):
		rb_filters["name"] = filters.ra_bill
	if filters.get("boq"):
		rb_filters["boq"] = filters.boq
	if filters.get("sales_order") and doctype_has_field("RA Bill", "sales_order"):
		rb_filters["sales_order"] = filters.sales_order
	if filters.get("customer"):
		rb_filters["customer"] = filters.customer
	if filters.get("status"):
		rb_filters["status"] = filters.status
	if filters.get("sales_invoice"):
		rb_filters["sales_invoice"] = filters.sales_invoice
	elif require_invoice:
		rb_filters["sales_invoice"] = ["is", "set"]

	rows = get_list(
		"RA Bill",
		filters=rb_filters,
		fields=fields,
		order_by="billing_period_to desc, bill_no desc, modified desc",
	)
	return filter_rows_by_dates(rows, filters)


def get_category_filter_condition(alias, filters, params):
	if not filters.get("category"):
		return []

	params["category"] = filters.category
	boq_category_field = sql_field("BOQ Item", alias, "boq_category", "''")
	ra_category_field = sql_field("RA Bill Item", alias, "category_name", "''")
	ra_sub_category_field = sql_field("RA Bill Item", alias, "sub_category", "''")
	return [
		f"({boq_category_field} = %(category)s "
		f"OR {ra_category_field} = %(category)s "
		f"OR {ra_sub_category_field} = %(category)s)"
	]


def amount_after_margin_expr(alias="bi"):
	qty = f"COALESCE({alias}.`qty`, 0)" if doctype_has_field("BOQ Item", "qty") else "0"
	unit_rate = f"COALESCE({alias}.`unit_rate`, 0)" if doctype_has_field("BOQ Item", "unit_rate") else "0"
	calculated = f"{qty} * {unit_rate}"

	if doctype_has_field("BOQ Item", "amount_after_margin"):
		return f"COALESCE(NULLIF({alias}.`amount_after_margin`, 0), {calculated})"
	if doctype_has_field("BOQ Item", "amount"):
		return f"COALESCE(NULLIF({alias}.`amount`, 0), {calculated})"
	return calculated


def get_boq_values(boq_rows):
	values = {}
	boq_names = [row.name for row in boq_rows]

	for row in boq_rows:
		values[row.name] = flt(row.get("grand_total")) or flt(row.get("total_cost"))

	missing = [name for name in boq_names if not values.get(name)]
	if not missing:
		return values

	conditions = [
		"bi.`parent` IN %(boqs)s",
		"bi.`parenttype` = 'BOQ'",
		"bi.`parentfield` = 'items'",
	]
	if doctype_has_field("BOQ Item", "is_deleted_in_revision"):
		conditions.append("COALESCE(bi.`is_deleted_in_revision`, 0) = 0")

	rows = frappe.db.sql(
		f"""
		SELECT bi.`parent`, COALESCE(SUM({amount_after_margin_expr("bi")}), 0) AS total
		FROM `tabBOQ Item` bi
		WHERE {" AND ".join(conditions)}
		GROUP BY bi.`parent`
		""",
		{"boqs": tuple(missing)},
		as_dict=True,
	)

	for row in rows:
		values[row.parent] = flt(row.total)

	return values


def get_boq_item_rows(boq_rows, filters):
	boq_names = [row.name for row in boq_rows]
	if not boq_names:
		return []

	params = {"boqs": tuple(boq_names)}
	conditions = [
		"bi.`parent` IN %(boqs)s",
		"bi.`parenttype` = 'BOQ'",
		"bi.`parentfield` = 'items'",
	]
	if doctype_has_field("BOQ Item", "is_deleted_in_revision"):
		conditions.append("COALESCE(bi.`is_deleted_in_revision`, 0) = 0")
	if filters.get("item"):
		params["item"] = filters.item
		item_field = sql_field("BOQ Item", "bi", "item", "''")
		conditions.append(f"{item_field} = %(item)s")
	if filters.get("category"):
		params["category"] = filters.category
		category_field = sql_field("BOQ Item", "bi", "boq_category", "''")
		conditions.append(f"{category_field} = %(category)s")

	return frappe.db.sql(
		f"""
		SELECT
			bi.`name` AS name,
			bi.`parent` AS boq,
			b.`project` AS project,
			b.`currency` AS currency,
			{sql_field("BOQ Item", "bi", "boq_item_key", "''")} AS boq_item_key,
			{sql_field("BOQ Item", "bi", "component_key", "''")} AS component_key,
			{sql_field("BOQ Item", "bi", "boq_parent_category", "''")} AS category,
			{sql_field("BOQ Item", "bi", "boq_category", "''")} AS sub_category,
			{sql_field("BOQ Item", "bi", "item", "''")} AS item,
			{sql_field("BOQ Item", "bi", "item_name", "''")} AS item_name,
			{sql_field("BOQ Item", "bi", "qty", "0")} AS qty,
			{sql_field("BOQ Item", "bi", "uom", "''")} AS uom,
			{sql_field("BOQ Item", "bi", "unit_cost", "0")} AS unit_cost,
			{sql_field("BOQ Item", "bi", "unit_rate", "0")} AS unit_rate,
			{sql_field("BOQ Item", "bi", "amount", "0")} AS amount,
			{sql_field("BOQ Item", "bi", "amount_after_margin", "0")} AS amount_after_margin,
			{sql_field("BOQ Item", "bi", "margin_percent", "0")} AS margin_percent
		FROM `tabBOQ Item` bi
		INNER JOIN `tabBOQ` b ON b.`name` = bi.`parent`
		WHERE {" AND ".join(conditions)}
		ORDER BY b.`project` asc, bi.`parent` asc, bi.`idx` asc
		""",
		params,
		as_dict=True,
	)


def sort_boq_key(row):
	return (
		cint(row.get("is_active_revision")),
		cint(row.get("revision_no")),
		str(row.get("modified") or row.get("creation") or ""),
		row.get("name") or "",
	)


def get_current_boq_map(project_rows, boqs_by_project):
	project_current = {
		row.name: row.get("current_boq")
		for row in project_rows
		if row.get("current_boq")
	}
	current_boqs = {}

	for project, boqs in boqs_by_project.items():
		by_name = {row.name: row for row in boqs}
		current = project_current.get(project)

		if current in by_name:
			current_boqs[project] = by_name[current]
			continue

		active = [row for row in boqs if cint(row.get("is_active_revision"))]
		if active:
			current_boqs[project] = sorted(active, key=sort_boq_key, reverse=True)[0]
			continue

		if boqs:
			current_boqs[project] = sorted(boqs, key=sort_boq_key, reverse=True)[0]

	return current_boqs


def get_work_base_boqs(project, boqs, current_boq=None, force_all=False):
	if not boqs:
		return []
	if force_all:
		return sorted(boqs, key=lambda row: row.name)

	groups = {}
	for row in boqs:
		original_boq = row.get("original_boq") or row.name
		groups.setdefault(original_boq, []).append(row)

	base_boqs = []
	for group_rows in groups.values():
		active = [row for row in group_rows if cint(row.get("is_active_revision"))]
		if active:
			base_boqs.append(sorted(active, key=sort_boq_key, reverse=True)[0])
			continue

		if current_boq and current_boq.name in {row.name for row in group_rows}:
			base_boqs.append(current_boq)
			continue

		base_boqs.append(sorted(group_rows, key=sort_boq_key, reverse=True)[0])

	return sorted(base_boqs, key=lambda row: row.name)


def get_project_boq_value(project, boqs, boq_values, current_boq=None, force_all=False):
	base_boqs = get_work_base_boqs(project, boqs, current_boq=current_boq, force_all=force_all)
	if base_boqs:
		return sum(flt(boq_values.get(row.name)) for row in base_boqs)
	if current_boq:
		return flt(boq_values.get(current_boq.name))
	return 0


def get_original_boq(boq, cache=None):
	if not boq:
		return None
	if cache is not None and boq in cache:
		return cache[boq]
	if not doctype_has_field("BOQ", "original_boq"):
		return boq

	values = frappe.db.get_value(
		"BOQ",
		boq,
		existing_fields("BOQ", ["name", "original_boq", "parent_boq"]),
		as_dict=True,
	)
	if not values:
		original_boq = boq
	elif values.get("original_boq"):
		original_boq = values.original_boq
	elif values.get("parent_boq"):
		original_boq = get_original_boq(values.parent_boq, cache)
	else:
		original_boq = boq

	if cache is not None:
		cache[boq] = original_boq
	return original_boq


def get_boq_item_context(boq_item, cache):
	if not boq_item:
		return frappe._dict()

	if boq_item not in cache:
		fields = existing_fields(
			"BOQ Item",
			["name", "parent", "boq_item_key", "component_key", "qty", "unit_rate"],
		)
		cache[boq_item] = frappe.db.get_value("BOQ Item", boq_item, fields, as_dict=True) or frappe._dict()

	return cache[boq_item]


def completion_key(row, item_cache, original_cache):
	boq_item = row.get("boq_item")
	item_context = get_boq_item_context(boq_item, item_cache)
	boq = row.get("boq_revision") or row.get("boq") or item_context.get("parent")
	original_boq = row.get("original_boq") or get_original_boq(boq, original_cache)
	item_key = (
		row.get("boq_item_key")
		or item_context.get("boq_item_key")
		or item_context.get("component_key")
		or boq_item
	)

	if not original_boq or not item_key:
		return None

	return f"{original_boq}::{item_key}"


def row_completed_qty(row):
	current_qty = flt(row.get("current_qty"))
	if current_qty:
		return current_qty
	return flt(row.get("boq_qty")) * flt(row.get("work_percent")) / 100


def row_completed_amount(row):
	current_amount = flt(row.get("current_amount"))
	if current_amount:
		return current_amount
	return row_completed_qty(row) * flt(row.get("boq_rate"))


def aggregate_completion_rows(rows):
	totals = {}
	item_cache = {}
	original_cache = {}

	for row in rows:
		key = completion_key(row, item_cache, original_cache)
		if not key:
			continue

		entry = totals.setdefault(key, {"completed_qty": 0, "completed_amount": 0})
		entry["completed_qty"] += row_completed_qty(row)
		entry["completed_amount"] += row_completed_amount(row)

	return totals


def get_transaction_completion_rows(ra_bill_names):
	if not ra_bill_names or not table_exists("RA Bill Transaction"):
		return []

	rows = frappe.db.sql(
		f"""
		SELECT
			{sql_field("RA Bill Transaction", "t", "ra_bill", "''")} AS ra_bill,
			{sql_field("RA Bill Transaction", "t", "boq", "''")} AS boq,
			{sql_field("RA Bill Transaction", "t", "original_boq", "''")} AS original_boq,
			{sql_field("RA Bill Transaction", "t", "boq_revision", "''")} AS boq_revision,
			{sql_field("RA Bill Transaction", "t", "boq_item_key", "''")} AS boq_item_key,
			{sql_field("RA Bill Transaction", "t", "boq_item", "''")} AS boq_item,
			{sql_field("RA Bill Transaction", "t", "boq_qty", "0")} AS boq_qty,
			{sql_field("RA Bill Transaction", "t", "boq_rate", "0")} AS boq_rate,
			{sql_field("RA Bill Transaction", "t", "work_percent", "0")} AS work_percent,
			{sql_field("RA Bill Transaction", "t", "current_qty", "0")} AS current_qty,
			{sql_field("RA Bill Transaction", "t", "current_amount", "0")} AS current_amount
		FROM `tabRA Bill Transaction` t
		WHERE t.`ra_bill` IN %(ra_bills)s
		""",
		{"ra_bills": tuple(ra_bill_names)},
		as_dict=True,
	)
	return rows


def get_ra_bill_item_completion_rows(ra_bill_names):
	if not ra_bill_names:
		return []

	rows = frappe.db.sql(
		f"""
		SELECT
			rb.`name` AS ra_bill,
			rb.`boq` AS boq,
			{sql_field("RA Bill Item", "rbi", "original_boq", "''")} AS original_boq,
			{sql_field("RA Bill Item", "rbi", "boq_revision", "''")} AS boq_revision,
			{sql_field("RA Bill Item", "rbi", "boq_item_key", "''")} AS boq_item_key,
			{sql_field("RA Bill Item", "rbi", "boq_item", "''")} AS boq_item,
			{sql_field("RA Bill Item", "rbi", "boq_qty", "0")} AS boq_qty,
			{sql_field("RA Bill Item", "rbi", "boq_rate", "0")} AS boq_rate,
			{sql_field("RA Bill Item", "rbi", "work_percent", "0")} AS work_percent,
			{sql_field("RA Bill Item", "rbi", "current_qty", "0")} AS current_qty,
			{sql_field("RA Bill Item", "rbi", "current_amount", "0")} AS current_amount
		FROM `tabRA Bill Item` rbi
		INNER JOIN `tabRA Bill` rb ON rb.`name` = rbi.`parent`
		WHERE rbi.`parent` IN %(ra_bills)s
			AND rbi.`parenttype` = 'RA Bill'
			AND rbi.`parentfield` = 'items'
		""",
		{"ra_bills": tuple(ra_bill_names)},
		as_dict=True,
	)
	return rows


def get_completion_totals(filters, project_names=None):
	ra_bills = get_ra_bill_rows(
		filters,
		fields=[
			"name",
			"project",
			"boq",
			"customer",
			"billing_period_from",
			"billing_period_to",
			"creation",
			"docstatus",
		],
		project_names=project_names,
		submitted_only=True,
	)
	ra_bill_names = [row.name for row in ra_bills]
	if not ra_bill_names:
		return {}

	transaction_rows = get_transaction_completion_rows(ra_bill_names)
	fallback_rows = get_ra_bill_item_completion_rows(ra_bill_names)

	if not transaction_rows:
		return aggregate_completion_rows(fallback_rows)

	totals = aggregate_completion_rows(transaction_rows)
	fallback_totals = aggregate_completion_rows(fallback_rows)

	for key, fallback_entry in fallback_totals.items():
		if key not in totals:
			totals[key] = fallback_entry

	return totals


def get_work_progress_rows(filters):
	project_rows = get_project_rows(filters)
	project_names = [row.name for row in project_rows]
	if not project_names:
		return []

	boq_rows = get_boq_rows(filters, project_names=project_names)
	if not boq_rows:
		return []

	boqs_by_project = group_by(boq_rows, "project")
	current_boqs = get_current_boq_map(project_rows, boqs_by_project)
	force_selected_boq = bool(filters.get("boq"))

	base_boqs = []
	for project, rows in boqs_by_project.items():
		base_boqs.extend(
			get_work_base_boqs(
				project,
				rows,
				current_boq=current_boqs.get(project),
				force_all=force_selected_boq,
			)
		)

	if not base_boqs:
		return []

	boq_by_name = {row.name: row for row in base_boqs}
	item_rows = get_boq_item_rows(base_boqs, filters)
	completion_totals = get_completion_totals(filters, project_names=project_names)
	original_cache = {}
	rows = []

	for item in item_rows:
		boq = boq_by_name.get(item.boq)
		if not boq:
			continue

		item_key = item.get("boq_item_key") or item.get("component_key") or item.get("name")
		if not item_key:
			item_key = item.get("item") or item.get("item_name")
		key = f"{get_original_boq(item.boq, original_cache)}::{item_key}"
		completion = completion_totals.get(key, {"completed_qty": 0, "completed_amount": 0})
		boq_qty = flt(item.get("qty"))
		boq_rate = flt(item.get("unit_rate"))
		boq_amount = flt(item.get("amount_after_margin")) or flt(item.get("amount")) or (boq_qty * boq_rate)
		completed_qty = flt(completion.get("completed_qty"))
		completed_amount = flt(completion.get("completed_amount"))
		remaining_qty = max(0, boq_qty - completed_qty)
		remaining_amount = max(0, boq_amount - completed_amount)

		rows.append(
			{
				"project": item.project,
				"boq": item.boq,
				"currency": item.currency,
				"category": item.get("category") or item.get("sub_category"),
				"sub_category": item.get("sub_category"),
				"item_name": item.get("item_name") or item.get("item"),
				"boq_qty": boq_qty,
				"completed_qty": completed_qty,
				"remaining_qty": remaining_qty,
				"completion_percent": safe_percent(completed_qty, boq_qty),
				"boq_amount": boq_amount,
				"completed_amount": completed_amount,
				"remaining_amount": remaining_amount,
			}
		)

	return rows


def get_ra_bill_item_rows(ra_bill_rows, filters):
	ra_bill_names = [row.name for row in ra_bill_rows]
	if not ra_bill_names:
		return []

	params = {"ra_bills": tuple(ra_bill_names)}
	conditions = [
		"rbi.`parent` IN %(ra_bills)s",
		"rbi.`parenttype` = 'RA Bill'",
		"rbi.`parentfield` = 'items'",
	]
	if filters.get("category"):
		params["category"] = filters.category
		category_field = sql_field("RA Bill Item", "rbi", "category_name", "''")
		sub_category_field = sql_field("RA Bill Item", "rbi", "sub_category", "''")
		conditions.append(
			f"({category_field} = %(category)s "
			f"OR {sub_category_field} = %(category)s)"
		)
	if filters.get("boq_item"):
		params["boq_item"] = filters.boq_item
		boq_item_field = sql_field("RA Bill Item", "rbi", "boq_item", "''")
		conditions.append(f"{boq_item_field} = %(boq_item)s")

	return frappe.db.sql(
		f"""
		SELECT
			rb.`name` AS ra_bill,
			rb.`ra_bill_no` AS ra_bill_no,
			rb.`project` AS project,
			rb.`boq` AS boq,
			rb.`currency` AS currency,
			{sql_field("RA Bill Item", "rbi", "category_name", "''")} AS category,
			{sql_field("RA Bill Item", "rbi", "sub_category", "''")} AS sub_category,
			COALESCE(NULLIF(bi.`item_name`, ''), bi.`item`, rbi.`boq_item`) AS item_name,
			{sql_field("RA Bill Item", "rbi", "boq_qty", "0")} AS boq_qty,
			{sql_field("RA Bill Item", "rbi", "previous_qty", "0")} AS previous_qty,
			{sql_field("RA Bill Item", "rbi", "current_qty", "0")} AS current_qty,
			{sql_field("RA Bill Item", "rbi", "cumulative_qty", "0")} AS cumulative_qty,
			{sql_field("RA Bill Item", "rbi", "remaining_qty", "0")} AS remaining_qty,
			{sql_field("RA Bill Item", "rbi", "work_percent", "0")} AS current_work_percent,
			{sql_field("RA Bill Item", "rbi", "current_amount", "0")} AS current_amount
		FROM `tabRA Bill Item` rbi
		INNER JOIN `tabRA Bill` rb ON rb.`name` = rbi.`parent`
		LEFT JOIN `tabBOQ Item` bi ON bi.`name` = rbi.`boq_item`
		WHERE {" AND ".join(conditions)}
		ORDER BY rb.`project` asc, rb.`bill_no` asc, rbi.`idx` asc
		""",
		params,
		as_dict=True,
	)


def get_invoice_rows_for_ra_bills(ra_bill_rows):
	ra_bill_names = [row.name for row in ra_bill_rows if row.get("sales_invoice")]
	if not ra_bill_names:
		return []

	return frappe.db.sql(
		"""
		SELECT
			rb.`sales_invoice` AS sales_invoice,
			rb.`name` AS ra_bill,
			rb.`project` AS project,
			rb.`boq` AS boq,
			rb.`sales_order` AS sales_order,
			rb.`customer` AS customer,
			rb.`currency` AS currency,
			si.`posting_date` AS posting_date,
			si.`grand_total` AS grand_total,
			COALESCE((
				SELECT SUM(sia.`allocated_amount`)
				FROM `tabSales Invoice Advance` sia
				WHERE sia.`parent` = si.`name`
			), 0) AS advance_allocated,
			si.`outstanding_amount` AS outstanding_amount,
			si.`status` AS status
		FROM `tabRA Bill` rb
		INNER JOIN `tabSales Invoice` si ON si.`name` = rb.`sales_invoice`
		WHERE rb.`name` IN %(ra_bills)s
			AND rb.`docstatus` != 2
			AND si.`docstatus` != 2
		ORDER BY si.`posting_date` desc, rb.`name` desc
		""",
		{"ra_bills": tuple(ra_bill_names)},
		as_dict=True,
	)


def get_project_construction_rows(filters):
	project_rows = get_project_rows(filters)
	project_names = [row.name for row in project_rows]
	if not project_names:
		return []

	boq_rows = get_boq_rows(filters, project_names=project_names)
	boqs_by_project = group_by(boq_rows, "project")
	current_boqs = get_current_boq_map(project_rows, boqs_by_project)
	boq_values = get_boq_values(boq_rows)

	ra_bills = get_ra_bill_rows(filters, project_names=project_names)
	ra_by_project = {}
	for row in ra_bills:
		entry = ra_by_project.setdefault(
			row.project,
			{"total_ra_billed": 0, "total_net_payable": 0, "total_advance_recovered": 0},
		)
		entry["total_ra_billed"] += flt(row.get("gross_amount"))
		entry["total_net_payable"] += flt(row.get("net_payable"))
		entry["total_advance_recovered"] += flt(
			row.get("actual_advance_recovered") or row.get("total_advance")
		)

	retention_by_project = {}
	if table_exists("Retention Record"):
		if table_exists("Sales Invoice Payment Breakdown"):
			retention_rows = frappe.db.sql(
				"""
				SELECT rr.project,
					SUM(COALESCE(sipb.amount, rr.retention_amount)) AS total_retention_held,
					SUM(
						CASE
							WHEN COALESCE(rr.retention_release_invoice, '') != ''
								AND COALESCE(rr.invoice_status, '') != 'Cancelled'
							THEN COALESCE(sipb.amount, rr.retention_amount)
							ELSE 0
						END
					) AS total_retention_invoiced,
					SUM(
						CASE
							WHEN sipb.name IS NOT NULL
							THEN GREATEST(0, COALESCE(sipb.amount, 0) - COALESCE(sipb.outstanding_amount, 0))
							ELSE rr.paid_amount
						END
					) AS total_retention_paid,
					SUM(COALESCE(sipb.outstanding_amount, rr.outstanding_amount)) AS total_retention_outstanding,
					SUM(COALESCE(sipb.outstanding_amount, rr.balance_amount)) AS retention_balance
				FROM `tabRetention Record` rr
				LEFT JOIN `tabSales Invoice Payment Breakdown` sipb
					ON sipb.parent = rr.sales_invoice
					AND sipb.parenttype = 'Sales Invoice'
					AND sipb.parentfield = 'payment_breakdown'
					AND sipb.type IN ('Retention Deduction', 'Retention Receivable')
				WHERE rr.project IN %(projects)s
					AND COALESCE(rr.status, '') != 'Cancelled'
				GROUP BY rr.project
				""",
				{"projects": tuple(project_names)},
				as_dict=True,
			)
		else:
			retention_rows = frappe.db.sql(
				"""
				SELECT project,
					SUM(retention_amount) AS total_retention_held,
					SUM(
						CASE
							WHEN COALESCE(retention_release_invoice, '') != ''
								AND COALESCE(invoice_status, '') != 'Cancelled'
							THEN retention_amount
							ELSE 0
						END
					) AS total_retention_invoiced,
					SUM(paid_amount) AS total_retention_paid,
					SUM(outstanding_amount) AS total_retention_outstanding,
					SUM(balance_amount) AS retention_balance
				FROM `tabRetention Record`
				WHERE project IN %(projects)s
					AND COALESCE(status, '') != 'Cancelled'
				GROUP BY project
				""",
				{"projects": tuple(project_names)},
				as_dict=True,
			)
		retention_by_project = {
			row.project: {
				"total_retention_held": flt(row.total_retention_held),
				"total_retention_invoiced": flt(row.total_retention_invoiced),
				"total_retention_paid": flt(row.total_retention_paid),
				"total_retention_outstanding": flt(row.total_retention_outstanding),
				"retention_balance": flt(row.retention_balance),
			}
			for row in retention_rows
			if row.get("project")
		}

	invoice_rows = get_invoice_rows_for_ra_bills(ra_bills)
	invoiced_by_project = {}
	outstanding_by_project = {}
	for row in invoice_rows:
		invoiced_by_project[row.project] = invoiced_by_project.get(row.project, 0) + flt(row.grand_total)
		outstanding_by_project[row.project] = outstanding_by_project.get(row.project, 0) + flt(
			row.outstanding_amount
		)

	completed_by_project = {}
	for row in get_work_progress_rows(filters):
		project = row.get("project")
		completed_by_project[project] = completed_by_project.get(project, 0) + flt(row.get("completed_amount"))

	out = []
	for project in project_rows:
		current_boq = current_boqs.get(project.name)
		project_boqs = boqs_by_project.get(project.name, [])
		boq_value = get_project_boq_value(
			project.name,
			project_boqs,
			boq_values,
			current_boq=current_boq,
			force_all=bool(filters.get("boq")),
		)
		ra_totals = ra_by_project.get(project.name, {})
		retention_totals = retention_by_project.get(project.name, {})
		advance_summary = get_project_advance_summary(project.name)
		completed_amount = completed_by_project.get(project.name, 0)

		out.append(
			{
				"project": project.name,
				"customer": project.get("customer"),
				"sales_order": project.get("sales_order") or (current_boq.get("sales_order") if current_boq else None),
				"current_active_boq": current_boq.name if current_boq else None,
				"currency": advance_summary.currency or (current_boq.get("currency") if current_boq else None),
				"total_sales_order_value": flt(advance_summary.total_sales_order_value),
				"total_customer_advance_received": flt(advance_summary.total_customer_advance_received),
				"total_advance_recovered": flt(advance_summary.total_advance_recovered),
				"remaining_advance_balance": flt(advance_summary.remaining_advance_balance),
				"advance_recovery_percent": flt(advance_summary.advance_recovery_percent),
				"sales_orders_with_advance": advance_summary.sales_orders_with_advance,
				"last_advance_receipt_date": advance_summary.last_advance_receipt_date,
				"last_advance_recovery_date": advance_summary.last_advance_recovery_date,
				"advance_status": advance_summary.advance_status,
				"boq_value": flt(boq_value),
				"total_ra_billed": flt(ra_totals.get("total_ra_billed")),
				"total_net_payable": flt(ra_totals.get("total_net_payable")),
				"total_invoiced": flt(invoiced_by_project.get(project.name)),
				"outstanding_receivable": flt(outstanding_by_project.get(project.name)),
				"total_retention_held": flt(retention_totals.get("total_retention_held")),
				"total_retention_invoiced": flt(retention_totals.get("total_retention_invoiced")),
				"total_retention_paid": flt(retention_totals.get("total_retention_paid")),
				"total_retention_outstanding": flt(retention_totals.get("total_retention_outstanding")),
				"retention_balance": flt(retention_totals.get("retention_balance")),
				"work_completion_percent": safe_percent(completed_amount, boq_value),
				"status": project.get("status"),
			}
		)

	return out


def get_boq_revision_differences(boq_names):
	if not boq_names or not doctype_has_field("BOQ Item", "amount_difference"):
		return {}

	rows = frappe.db.sql(
		"""
		SELECT bi.`parent`, COALESCE(SUM(bi.`amount_difference`), 0) AS total_difference
		FROM `tabBOQ Item` bi
		WHERE bi.`parent` IN %(boqs)s
			AND bi.`parenttype` = 'BOQ'
			AND bi.`parentfield` = 'items'
		GROUP BY bi.`parent`
		""",
		{"boqs": tuple(boq_names)},
		as_dict=True,
	)
	return {row.parent: flt(row.total_difference) for row in rows}
