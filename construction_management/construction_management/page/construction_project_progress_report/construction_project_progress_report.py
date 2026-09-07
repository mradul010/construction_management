import frappe
from frappe import _
from frappe.utils import cint, flt


FULL_ACCESS_ROLES = {"System Manager", "Construction Manager"}
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


def _has_full_access():
	return bool(set(frappe.get_roles()) & FULL_ACCESS_ROLES)


def _doctype_has_field(doctype, fieldname):
	if fieldname in STANDARD_FIELDS:
		return True

	try:
		return frappe.get_meta(doctype).has_field(fieldname)
	except Exception:
		return False


def _table_exists(doctype):
	try:
		return frappe.db.table_exists(doctype)
	except Exception:
		return False


def _existing_fields(doctype, fields):
	return [fieldname for fieldname in fields if _doctype_has_field(doctype, fieldname)]


def _parse_filters(filters=None):
	if isinstance(filters, str):
		filters = frappe.parse_json(filters) or {}

	filters = frappe._dict(filters or {})
	date_range = filters.get("date_range")

	if isinstance(date_range, str):
		try:
			date_range = frappe.parse_json(date_range)
		except Exception:
			date_range = [part.strip() for part in date_range.split(",") if part.strip()]

	if isinstance(date_range, (list, tuple)):
		if len(date_range) > 0 and not filters.get("from_date"):
			filters.from_date = date_range[0]
		if len(date_range) > 1 and not filters.get("to_date"):
			filters.to_date = date_range[1]

	return filters


def _ensure_report_access():
	if _has_full_access():
		return

	if not frappe.has_permission("Project", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _can_read_project(project):
	if not project:
		return False
	if _has_full_access():
		return True
	return frappe.has_permission("Project", "read", doc=project)


def _require_project_permission(project):
	if not _can_read_project(project):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _date_conditions(alias, filters, params):
	conditions = []
	date_fields = []

	for fieldname in ("billing_period_to", "billing_period_from"):
		if _doctype_has_field("RA Bill", fieldname):
			date_fields.append(f"{alias}.`{fieldname}`")

	date_fields.append(f"DATE({alias}.`creation`)")
	date_expr = f"COALESCE({', '.join(date_fields)})"

	if filters.get("from_date"):
		conditions.append(f"{date_expr} >= %(from_date)s")
		params["from_date"] = filters.from_date

	if filters.get("to_date"):
		conditions.append(f"{date_expr} <= %(to_date)s")
		params["to_date"] = filters.to_date

	return conditions


def _sql_field(doctype, alias, fieldname, default="NULL"):
	if _doctype_has_field(doctype, fieldname):
		return f"{alias}.`{fieldname}`"
	return default


def _get_projects(filters):
	project_fields = _existing_fields(
		"Project",
		["name", "project_name", "customer", "status", "current_boq"],
	)
	project_filters = {}

	if filters.get("customer") and _doctype_has_field("Project", "customer"):
		project_filters["customer"] = filters.customer

	if filters.get("project"):
		project_filters["name"] = filters.project

	if filters.get("status") and _doctype_has_field("Project", "status"):
		project_filters["status"] = filters.status

	getter = frappe.get_all if _has_full_access() else frappe.get_list
	return getter(
		"Project",
		filters=project_filters,
		fields=project_fields,
		order_by="modified desc",
	)


def _get_boq_rows(projects):
	if not projects:
		return []

	fields = _existing_fields(
		"BOQ",
		[
			"name",
			"project",
			"client",
			"currency",
			"status",
			"docstatus",
			"grand_total",
			"amount_after_margin",
			"revision_no",
			"revision_status",
			"is_active_revision",
			"original_boq",
			"creation",
			"modified",
		],
	)

	return frappe.get_all(
		"BOQ",
		filters={
			"project": ["in", projects],
			"docstatus": ["!=", 2],
		},
		fields=fields,
		order_by="project asc, revision_no desc, modified desc",
	)


def _group_by(rows, key):
	grouped = {}
	for row in rows:
		grouped.setdefault(row.get(key), []).append(row)
	return grouped


def _sort_boq_key(row):
	return (
		cint(row.get("is_active_revision")),
		cint(row.get("revision_no")),
		str(row.get("modified") or row.get("creation") or ""),
		row.get("name") or "",
	)


def _get_current_boq_map(project_rows, boqs_by_project):
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
			current_boqs[project] = sorted(active, key=_sort_boq_key, reverse=True)[0]
			continue

		if boqs:
			current_boqs[project] = sorted(boqs, key=_sort_boq_key, reverse=True)[0]

	return current_boqs


def _boq_item_amount_expr():
	qty = "COALESCE(`qty`, 0)" if _doctype_has_field("BOQ Item", "qty") else "0"
	unit_rate = (
		"COALESCE(`unit_rate`, 0)"
		if _doctype_has_field("BOQ Item", "unit_rate")
		else "0"
	)
	calculated = f"{qty} * {unit_rate}"

	if _doctype_has_field("BOQ Item", "amount_after_margin"):
		return f"COALESCE(NULLIF(`amount_after_margin`, 0), {calculated})"

	if _doctype_has_field("BOQ Item", "amount"):
		return f"COALESCE(NULLIF(`amount`, 0), {calculated})"

	return calculated


def _get_boq_values(boq_rows):
	values = {}
	boq_names = [row.name for row in boq_rows]

	for row in boq_rows:
		values[row.name] = flt(row.get("amount_after_margin")) or flt(row.get("grand_total"))

	missing = [name for name in boq_names if not values.get(name)]
	if not missing:
		return values

	conditions = [
		"`parent` IN %(boqs)s",
		"`parenttype` = 'BOQ'",
		"`parentfield` = 'items'",
	]
	if _doctype_has_field("BOQ Item", "is_deleted_in_revision"):
		conditions.append("COALESCE(`is_deleted_in_revision`, 0) = 0")

	rows = frappe.db.sql(
		f"""
		SELECT `parent`, COALESCE(SUM({_boq_item_amount_expr()}), 0) AS total
		FROM `tabBOQ Item`
		WHERE {" AND ".join(conditions)}
		GROUP BY `parent`
		""",
		{"boqs": tuple(missing)},
		as_dict=True,
	)

	for row in rows:
		values[row.parent] = flt(row.total)

	return values


def _get_ra_bill_aggregates(projects, filters):
	if not projects:
		return {}

	params = {"projects": tuple(projects)}
	conditions = [
		"rb.`project` IN %(projects)s",
		"rb.`docstatus` != 2",
	]
	conditions.extend(_date_conditions("rb", filters, params))

	rows = frappe.db.sql(
		f"""
		SELECT
			rb.`project`,
			COUNT(rb.`name`) AS ra_bill_count,
			COALESCE(SUM(rb.`gross_amount`), 0) AS total_ra_billed,
			COALESCE(SUM(rb.`net_payable`), 0) AS total_net_payable
		FROM `tabRA Bill` rb
		WHERE {" AND ".join(conditions)}
		GROUP BY rb.`project`
		""",
		params,
		as_dict=True,
	)

	return {row.project: row for row in rows}


def _get_invoice_totals(projects, filters):
	if not projects:
		return {}

	params = {"projects": tuple(projects)}
	conditions = [
		"rb.`project` IN %(projects)s",
		"rb.`docstatus` != 2",
		"rb.`sales_invoice` IS NOT NULL",
		"rb.`sales_invoice` != ''",
		"si.`docstatus` != 2",
	]
	conditions.extend(_date_conditions("rb", filters, params))

	rows = frappe.db.sql(
		f"""
		SELECT
			rb.`project`,
			COALESCE(SUM(si.`grand_total`), 0) AS total_invoiced
		FROM `tabRA Bill` rb
		INNER JOIN `tabSales Invoice` si ON si.`name` = rb.`sales_invoice`
		WHERE {" AND ".join(conditions)}
		GROUP BY rb.`project`
		""",
		params,
		as_dict=True,
	)

	return {row.project: flt(row.total_invoiced) for row in rows}


def _completed_amount_expr(alias="rbi"):
	current_amount = (
		f"COALESCE({alias}.`current_amount`, 0)"
		if _doctype_has_field("RA Bill Item", "current_amount")
		else "0"
	)
	current_qty = (
		f"COALESCE({alias}.`current_qty`, 0)"
		if _doctype_has_field("RA Bill Item", "current_qty")
		else "0"
	)
	boq_qty = (
		f"COALESCE({alias}.`boq_qty`, 0)"
		if _doctype_has_field("RA Bill Item", "boq_qty")
		else "0"
	)
	work_percent = (
		f"COALESCE({alias}.`work_percent`, 0)"
		if _doctype_has_field("RA Bill Item", "work_percent")
		else "0"
	)
	boq_rate = (
		f"COALESCE({alias}.`boq_rate`, 0)"
		if _doctype_has_field("RA Bill Item", "boq_rate")
		else "0"
	)

	return f"""
		CASE
			WHEN {current_amount} > 0 THEN {current_amount}
			WHEN {current_qty} > 0 THEN {current_qty} * {boq_rate}
			ELSE ({boq_qty} * {work_percent} / 100) * {boq_rate}
		END
	"""


def _get_completed_amount_by_project(projects, filters):
	if not projects:
		return {}

	params = {"projects": tuple(projects)}
	conditions = [
		"rb.`project` IN %(projects)s",
		"rb.`docstatus` = 1",
		"rbi.`parenttype` = 'RA Bill'",
		"rbi.`parentfield` = 'items'",
	]
	conditions.extend(_date_conditions("rb", filters, params))

	rows = frappe.db.sql(
		f"""
		SELECT
			rb.`project`,
			COALESCE(SUM({_completed_amount_expr("rbi")}), 0) AS completed_amount
		FROM `tabRA Bill Item` rbi
		INNER JOIN `tabRA Bill` rb ON rb.`name` = rbi.`parent`
		WHERE {" AND ".join(conditions)}
		GROUP BY rb.`project`
		""",
		params,
		as_dict=True,
	)

	return {row.project: flt(row.completed_amount) for row in rows}


def _safe_percent(value, total):
	total = flt(total)
	return (flt(value) / total * 100) if total else 0


@frappe.whitelist()
def get_project_progress_list(filters=None):
	filters = _parse_filters(filters)
	_ensure_report_access()

	projects = _get_projects(filters)
	project_names = [row.name for row in projects]
	if not project_names:
		return []

	boq_rows = _get_boq_rows(project_names)
	boqs_by_project = _group_by(boq_rows, "project")
	current_boqs = _get_current_boq_map(projects, boqs_by_project)
	boq_values = _get_boq_values(boq_rows)
	ra_bill_totals = _get_ra_bill_aggregates(project_names, filters)
	invoice_totals = _get_invoice_totals(project_names, filters)
	completed_amounts = _get_completed_amount_by_project(project_names, filters)

	out = []
	for project in projects:
		project_boqs = boqs_by_project.get(project.name, [])
		current_boq = current_boqs.get(project.name)
		total_boq_value = _get_project_boq_value(
			project.name,
			project_boqs,
			boq_values,
			project_doc=project,
			current_boq=current_boq,
		)
		ra_totals = ra_bill_totals.get(project.name, frappe._dict())
		completed_amount = completed_amounts.get(project.name, 0)

		out.append(
			{
				"project": project.name,
				"project_name": project.get("project_name"),
				"customer": project.get("customer"),
				"status": project.get("status"),
				"current_boq": current_boq.name if current_boq else None,
				"currency": current_boq.get("currency") if current_boq else None,
				"boq_count": len(project_boqs),
				"ra_bill_count": cint(ra_totals.get("ra_bill_count")),
				"total_boq_value": flt(total_boq_value),
				"total_ra_billed": flt(ra_totals.get("total_ra_billed")),
				"total_net_payable": flt(ra_totals.get("total_net_payable")),
				"total_invoiced": flt(invoice_totals.get(project.name)),
				"completed_amount": flt(completed_amount),
				"overall_completion_percent": _safe_percent(completed_amount, total_boq_value),
			}
		)

	return out


def _get_project_doc(project):
	fields = _existing_fields(
		"Project",
		["name", "project_name", "customer", "status", "current_boq"],
	)
	return frappe.db.get_value("Project", project, fields, as_dict=True)


def _get_boq_detail_rows(project):
	rows = _get_boq_rows([project])
	boq_values = _get_boq_values(rows)

	for row in rows:
		row.total_boq_value = flt(boq_values.get(row.name))

	return rows


def _get_ra_bill_rows(project, filters):
	params = {"project": project}
	conditions = [
		"rb.`project` = %(project)s",
		"rb.`docstatus` != 2",
	]
	conditions.extend(_date_conditions("rb", filters, params))

	rows = frappe.db.sql(
		f"""
		SELECT
			rb.`name`,
			rb.`bill_no`,
			rb.`ra_bill_no`,
			rb.`boq`,
			rb.`billing_period_from`,
			rb.`billing_period_to`,
			rb.`status`,
			rb.`gross_amount`,
			rb.`retention_amount`,
			rb.`net_payable`,
			rb.`sales_invoice`,
			rb.`currency`,
			rb.`docstatus`
		FROM `tabRA Bill` rb
		WHERE {" AND ".join(conditions)}
		ORDER BY rb.`billing_period_to` desc, rb.`bill_no` desc, rb.`modified` desc
		""",
		params,
		as_dict=True,
	)
	return rows


def _get_category_labels(category_names):
	category_names = [name for name in set(category_names) if name]
	if not category_names:
		return {}

	rows = frappe.get_all(
		"BOQ Category",
		filters={"name": ["in", category_names]},
		fields=["name", "category_name"],
	)
	return {row.name: row.category_name or row.name for row in rows}


def _get_original_boq(boq, cache=None):
	if not boq:
		return None

	if cache is not None and boq in cache:
		return cache[boq]

	if not _doctype_has_field("BOQ", "original_boq"):
		if cache is not None:
			cache[boq] = boq
		return boq

	values = frappe.db.get_value(
		"BOQ",
		boq,
		_existing_fields("BOQ", ["name", "original_boq", "parent_boq"]),
		as_dict=True,
	)
	if not values:
		original_boq = boq
	elif values.get("original_boq"):
		original_boq = values.original_boq
	elif values.get("parent_boq"):
		original_boq = _get_original_boq(values.parent_boq, cache)
	else:
		original_boq = boq

	if cache is not None:
		cache[boq] = original_boq
	return original_boq


def _get_work_base_boqs(project, boqs, project_doc=None, current_boq=None):
	if not boqs:
		return []

	if current_boq is None:
		project_doc = project_doc or _get_project_doc(project)
		current_boq_map = _get_current_boq_map([project_doc], {project: boqs}) if project_doc else {}
		current_boq = current_boq_map.get(project)

	groups = {}

	for row in boqs:
		original_boq = row.get("original_boq") or row.name
		groups.setdefault(original_boq, []).append(row)

	base_boqs = []
	for group_rows in groups.values():
		active = [row for row in group_rows if cint(row.get("is_active_revision"))]
		if active:
			base_boqs.append(sorted(active, key=_sort_boq_key, reverse=True)[0])
			continue

		if current_boq and current_boq.name in {row.name for row in group_rows}:
			base_boqs.append(current_boq)
			continue

		base_boqs.append(sorted(group_rows, key=_sort_boq_key, reverse=True)[0])

	return sorted(base_boqs, key=lambda row: row.name)


def _get_project_boq_value(project, boqs, boq_values, project_doc=None, current_boq=None):
	base_boqs = _get_work_base_boqs(project, boqs, project_doc=project_doc, current_boq=current_boq)
	if base_boqs:
		return sum(flt(boq_values.get(row.name)) for row in base_boqs)

	if current_boq:
		return flt(boq_values.get(current_boq.name))

	return 0


def _get_base_items(project, boqs):
	base_boqs = _get_work_base_boqs(project, boqs)
	base_boq_names = [row.name for row in base_boqs]
	if not base_boq_names:
		return []

	fields = _existing_fields(
		"BOQ Item",
		[
			"name",
			"parent",
			"idx",
			"boq_item_key",
			"component_key",
			"boq_category",
			"boq_parent_category",
			"item",
			"item_name",
			"qty",
			"uom",
			"unit_rate",
			"amount_after_margin",
			"is_deleted_in_revision",
		],
	)
	filters = {
		"parent": ["in", base_boq_names],
		"parenttype": "BOQ",
		"parentfield": "items",
	}
	if _doctype_has_field("BOQ Item", "is_deleted_in_revision"):
		filters["is_deleted_in_revision"] = 0

	rows = frappe.get_all(
		"BOQ Item",
		filters=filters,
		fields=fields,
		order_by="parent asc, idx asc",
	)

	category_labels = _get_category_labels([row.get("boq_category") for row in rows])
	original_cache = {}

	for row in rows:
		row.original_boq = _get_original_boq(row.parent, original_cache)
		row.item_key = row.get("boq_item_key") or row.get("component_key") or row.name
		row.sub_category = category_labels.get(row.get("boq_category"), row.get("boq_category"))
		row.category = row.get("boq_parent_category") or row.sub_category

	return rows


def _get_boq_item_context(boq_item, cache):
	if not boq_item:
		return frappe._dict()

	if boq_item not in cache:
		fields = _existing_fields(
			"BOQ Item",
			["name", "parent", "boq_item_key", "component_key", "qty", "unit_rate"],
		)
		cache[boq_item] = frappe.db.get_value(
			"BOQ Item",
			boq_item,
			fields,
			as_dict=True,
		) or frappe._dict()

	return cache[boq_item]


def _completion_key(row, item_cache, original_cache):
	boq_item = row.get("boq_item")
	item_context = _get_boq_item_context(boq_item, item_cache)
	boq = row.get("boq_revision") or row.get("boq") or item_context.get("parent")
	original_boq = row.get("original_boq") or _get_original_boq(boq, original_cache)
	item_key = (
		row.get("boq_item_key")
		or item_context.get("boq_item_key")
		or item_context.get("component_key")
		or boq_item
	)

	if not original_boq or not item_key:
		return None

	return f"{original_boq}::{item_key}"


def _row_completed_qty(row):
	current_qty = flt(row.get("current_qty"))
	if current_qty:
		return current_qty
	return flt(row.get("boq_qty")) * flt(row.get("work_percent")) / 100


def _row_completed_amount(row):
	current_amount = flt(row.get("current_amount"))
	if current_amount:
		return current_amount
	return _row_completed_qty(row) * flt(row.get("boq_rate"))


def _aggregate_completion_rows(rows):
	totals = {}
	item_cache = {}
	original_cache = {}

	for row in rows:
		key = _completion_key(row, item_cache, original_cache)
		if not key:
			continue

		entry = totals.setdefault(
			key,
			{
				"completed_qty": 0,
				"completed_amount": 0,
				"related_ra_bills": set(),
			},
		)
		entry["completed_qty"] += _row_completed_qty(row)
		entry["completed_amount"] += _row_completed_amount(row)
		if row.get("ra_bill"):
			entry["related_ra_bills"].add(row.ra_bill)

	return totals


def _get_transaction_completion_rows(project, filters):
	if not _table_exists("RA Bill Transaction") or not _doctype_has_field("RA Bill Transaction", "ra_bill"):
		return []

	params = {"project": project}
	conditions = [
		"rb.`project` = %(project)s",
		"rb.`docstatus` = 1",
	]
	conditions.extend(_date_conditions("rb", filters, params))

	rows = frappe.db.sql(
		f"""
		SELECT
			{_sql_field("RA Bill Transaction", "t", "ra_bill", "''")} AS ra_bill,
			{_sql_field("RA Bill Transaction", "t", "boq", "''")} AS boq,
			{_sql_field("RA Bill Transaction", "t", "original_boq", "''")} AS original_boq,
			{_sql_field("RA Bill Transaction", "t", "boq_revision", "''")} AS boq_revision,
			{_sql_field("RA Bill Transaction", "t", "boq_item_key", "''")} AS boq_item_key,
			{_sql_field("RA Bill Transaction", "t", "boq_item", "''")} AS boq_item,
			{_sql_field("RA Bill Transaction", "t", "boq_qty", "0")} AS boq_qty,
			{_sql_field("RA Bill Transaction", "t", "boq_rate", "0")} AS boq_rate,
			{_sql_field("RA Bill Transaction", "t", "work_percent", "0")} AS work_percent,
			{_sql_field("RA Bill Transaction", "t", "current_qty", "0")} AS current_qty,
			{_sql_field("RA Bill Transaction", "t", "current_amount", "0")} AS current_amount
		FROM `tabRA Bill Transaction` t
		INNER JOIN `tabRA Bill` rb ON rb.`name` = t.`ra_bill`
		WHERE {" AND ".join(conditions)}
		""",
		params,
		as_dict=True,
	)
	return rows


def _get_ra_bill_item_completion_rows(project, filters):
	params = {"project": project}
	conditions = [
		"rb.`project` = %(project)s",
		"rb.`docstatus` = 1",
		"rbi.`parenttype` = 'RA Bill'",
		"rbi.`parentfield` = 'items'",
	]
	conditions.extend(_date_conditions("rb", filters, params))

	rows = frappe.db.sql(
		f"""
		SELECT
			rb.`name` AS ra_bill,
			rb.`boq` AS boq,
			{_sql_field("RA Bill Item", "rbi", "original_boq", "''")} AS original_boq,
			{_sql_field("RA Bill Item", "rbi", "boq_revision", "''")} AS boq_revision,
			{_sql_field("RA Bill Item", "rbi", "boq_item_key", "''")} AS boq_item_key,
			{_sql_field("RA Bill Item", "rbi", "boq_item", "''")} AS boq_item,
			{_sql_field("RA Bill Item", "rbi", "boq_qty", "0")} AS boq_qty,
			{_sql_field("RA Bill Item", "rbi", "boq_rate", "0")} AS boq_rate,
			{_sql_field("RA Bill Item", "rbi", "work_percent", "0")} AS work_percent,
			{_sql_field("RA Bill Item", "rbi", "current_qty", "0")} AS current_qty,
			{_sql_field("RA Bill Item", "rbi", "current_amount", "0")} AS current_amount
		FROM `tabRA Bill Item` rbi
		INNER JOIN `tabRA Bill` rb ON rb.`name` = rbi.`parent`
		WHERE {" AND ".join(conditions)}
		""",
		params,
		as_dict=True,
	)
	return rows


def _get_completion_totals(project, filters):
	transaction_rows = _get_transaction_completion_rows(project, filters)
	fallback_rows = _get_ra_bill_item_completion_rows(project, filters)

	if not transaction_rows:
		return _aggregate_completion_rows(fallback_rows)

	totals = _aggregate_completion_rows(transaction_rows)
	fallback_totals = _aggregate_completion_rows(fallback_rows)

	for key, fallback_entry in fallback_totals.items():
		if key not in totals:
			totals[key] = fallback_entry

	return totals


def _get_work_completion(project, filters, boqs):
	base_items = _get_base_items(project, boqs)
	if not base_items:
		return []

	totals = _get_completion_totals(project, filters)
	rows = []

	for item in base_items:
		key = f"{item.original_boq}::{item.item_key}"
		completion = totals.get(
			key,
			{"completed_qty": 0, "completed_amount": 0, "related_ra_bills": set()},
		)
		boq_qty = flt(item.get("qty"))
		boq_rate = flt(item.get("unit_rate"))
		boq_amount = flt(item.get("amount_after_margin")) or (boq_qty * boq_rate)
		completed_qty = flt(completion.get("completed_qty"))
		completed_amount = flt(completion.get("completed_amount"))
		remaining_qty = max(0, boq_qty - completed_qty)
		remaining_amount = max(0, boq_amount - completed_amount)

		rows.append(
			{
				"boq": item.parent,
				"category": item.get("category"),
				"sub_category": item.get("sub_category"),
				"item_name": item.get("item_name") or item.get("item") or item.name,
				"boq_qty": boq_qty,
				"completed_qty": completed_qty,
				"remaining_qty": remaining_qty,
				"completion_percent": _safe_percent(completed_qty, boq_qty),
				"boq_rate": boq_rate,
				"boq_amount": boq_amount,
				"completed_amount": completed_amount,
				"remaining_amount": remaining_amount,
				"related_ra_bills": sorted(completion.get("related_ra_bills") or []),
			}
		)

	return rows


def _get_summary(project, project_doc, boqs, filters):
	current_boq_map = _get_current_boq_map([project_doc], {project: boqs})
	current_boq = current_boq_map.get(project)
	boq_values = _get_boq_values(boqs)
	ra_totals = _get_ra_bill_aggregates([project], filters).get(project, frappe._dict())
	invoiced = _get_invoice_totals([project], filters).get(project, 0)
	completed_amount = _get_completed_amount_by_project([project], filters).get(project, 0)
	boq_value = _get_project_boq_value(
		project,
		boqs,
		boq_values,
		project_doc=project_doc,
		current_boq=current_boq,
	)

	return {
		"project": project,
		"project_name": project_doc.get("project_name"),
		"customer": project_doc.get("customer"),
		"status": project_doc.get("status"),
		"current_boq": current_boq.name if current_boq else None,
		"currency": current_boq.get("currency") if current_boq else None,
		"boq_value": flt(boq_value),
		"total_ra_billed": flt(ra_totals.get("total_ra_billed")),
		"total_net_payable": flt(ra_totals.get("total_net_payable")),
		"total_invoiced": flt(invoiced),
		"completed_amount": flt(completed_amount),
		"completion_percent": _safe_percent(completed_amount, boq_value),
	}


@frappe.whitelist()
def get_project_progress_detail(project, filters=None):
	filters = _parse_filters(filters)
	_require_project_permission(project)

	project_doc = _get_project_doc(project)
	if not project_doc:
		frappe.throw(_("Project {0} not found").format(project))

	boqs = _get_boq_detail_rows(project)
	return {
		"project": project_doc,
		"summary": _get_summary(project, project_doc, boqs, filters),
		"boqs": boqs,
		"ra_bills": _get_ra_bill_rows(project, filters),
		"work_completion": _get_work_completion(project, filters, boqs),
	}


@frappe.whitelist()
def get_work_completion_for_project(project, filters=None):
	filters = _parse_filters(filters)
	_require_project_permission(project)
	return _get_work_completion(project, filters, _get_boq_detail_rows(project))
