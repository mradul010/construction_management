import calendar
from collections import defaultdict
from decimal import Decimal

import frappe
from frappe import _
from frappe.desk.reportview import get_match_cond
from frappe.utils import add_days, date_diff, flt, getdate, nowdate


MONTHS = {month: index for index, month in enumerate(calendar.month_name) if month}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	period = get_period(filters)
	check_permissions()

	received = get_received_quantities(filters, period)
	consumed = get_consumed_quantities(filters, period)
	returned = get_returned_quantities(filters, period)
	items = get_item_rows(filters, period, received, consumed, returned)

	columns = get_columns()
	data = get_heading_rows(filters, period)
	data.extend(get_transaction_rows(items, received, consumed, returned))
	return columns, data


def get_columns():
	return [
		{"label": " ", "fieldname": "sr_no", "fieldtype": "Data", "width": 60},
		{"label": " ", "fieldname": "item_description", "fieldtype": "Data", "width": 300},
		{"label": " ", "fieldname": "uom", "fieldtype": "Data", "width": 85},
		{"label": " ", "fieldname": "received_previous", "fieldtype": "Data", "width": 155},
		{"label": " ", "fieldname": "received_current", "fieldtype": "Data", "width": 110},
		{"label": " ", "fieldname": "received_total", "fieldtype": "Data", "width": 130},
		{"label": " ", "fieldname": "consumed_previous", "fieldtype": "Data", "width": 155},
		{"label": " ", "fieldname": "consumed_current", "fieldtype": "Data", "width": 110},
		{"label": " ", "fieldname": "consumed_total", "fieldtype": "Data", "width": 130},
		{"label": " ", "fieldname": "returned_to_store", "fieldtype": "Data", "width": 145},
		{"label": _("Balance"), "fieldname": "balance", "fieldtype": "Float", "width": 120},
	]


def get_period(filters):
	year = int(filters.get("year") or getdate(nowdate()).year)
	selected_month = filters.get("month") or calendar.month_name[getdate(nowdate()).month]
	month_value = str(selected_month).strip()
	if month_value.isdigit():
		month_number = int(month_value)
	else:
		month_number = MONTHS.get(month_value.casefold().capitalize())
	if not month_number:
		frappe.throw(_("Invalid month {0}.").format(selected_month))
	if month_number < 1 or month_number > 12:
		frappe.throw(_("Invalid month {0}.").format(selected_month))

	start = getdate(f"{year}-{month_number:02d}-01")
	end = getdate(f"{year}-{month_number:02d}-{calendar.monthrange(year, month_number)[1]}")
	if date_diff(end, start) < 0:
		frappe.throw(_("To Date cannot be before From Date."))

	previous_end = add_days(start, -1)
	return frappe._dict(
		{
			"start": start,
			"end": end,
			"previous_end": previous_end,
			"previous_label": f"{calendar.month_name[previous_end.month]} {previous_end.year}",
		}
	)


def check_permissions():
	for doctype in ("Purchase Invoice", "Site Material Consumption", "Item"):
		frappe.has_permission(doctype, "read", throw=True)


def get_heading_rows(filters, period):
	cumulative_label = f"Cumulative till  {period.previous_label}"
	return [
		# make_row("STORE RECONCILIATION", row_type="title"),
		make_row("", supplier_label(filters.get("supplier")), "", "RECEIVED", "", "", "CONSUMED", row_type="group_header"),

		make_row(
			"Sr. No.",
			"Item Description",
			"UOM",
			cumulative_label,
			"This Month",
			"Total Cumulative",
			cumulative_label,
			"This Month",
			"Total Cumulative",
			"Returned to Store",
			"Balance",
			row_type="column_header",
		),
	]


def make_row(*values, row_type=None):
	values = list(values)[:11]
	values.extend([""] * (11 - len(values)))
	return frappe._dict(
		{
			"sr_no": values[0],
			"item_description": values[1],
			"uom": values[2],
			"received_previous": values[3],
			"received_current": values[4],
			"received_total": values[5],
			"consumed_previous": values[6],
			"consumed_current": values[7],
			"consumed_total": values[8],
			"returned_to_store": values[9],
			"balance": values[10],
			"row_type": row_type,
		}
	)


def company_label(company):
	if not company:
		return ""
	return frappe.db.get_value("Company", company, "company_name") or company


def project_label(project):
	if not project:
		return ""
	return frappe.db.get_value("Project", project, "project_name") or project


def supplier_label(supplier):
	if not supplier:
		return ""
	row = frappe.db.get_value(
		"Supplier",
		supplier,
		["supplier_name", "mobile_no", "email_id"],
		as_dict=True,
	)
	if not row:
		return supplier

	label = row.supplier_name or supplier
	if row.mobile_no:
		label = f"{label} ({row.mobile_no})"
	if row.email_id:
		label = f"{label}{row.email_id}"
	return label


def get_transaction_rows(items, received, consumed, returned):
	data = []
	for index, item in enumerate(items, 1):
		item_code = item.get("item_code")
		received_row = received.get(item_code, {})
		consumed_row = consumed.get(item_code, {})
		returned_row = returned.get(item_code, {})

		received_previous = flt(received_row.get("previous_qty"))
		received_current = flt(received_row.get("current_qty"))
		consumed_previous = flt(consumed_row.get("previous_qty"))
		consumed_current = flt(consumed_row.get("current_qty"))
		returned_previous = flt(returned_row.get("previous_qty"))
		returned_current = flt(returned_row.get("current_qty"))
		received_total = received_previous + received_current
		consumed_total = consumed_previous + consumed_current
		returned_total = returned_previous + returned_current
		balance = received_total - consumed_total + returned_total

		data.append(
			make_row(
				index,
				item.get("item_description"),
				item.get("uom"),
				format_previous_qty(received_previous),
				format_qty(received_current),
				format_qty(received_previous + received_current),
				format_previous_qty(consumed_previous),
				format_qty(consumed_current),
				format_qty(consumed_total),
				format_returned_qty(returned_total),
				flt(balance, 6),
			)
		)
	return data


def format_previous_qty(value):
	return "" if flt(value) == 0 else format_qty(value)


def format_returned_qty(value):
	return "" if flt(value) == 0 else format_qty(value)


def format_qty(value):
	value = flt(value, 6)
	if value == int(value):
		return str(int(value))
	return str(Decimal(str(value)).normalize())


def get_received_quantities(filters, period):
	conditions, values = get_purchase_invoice_conditions(filters, period)
	add_match_condition(conditions, "Purchase Invoice")
	invoice_stock_qty = "coalesce(`tabPurchase Invoice Item`.stock_qty, `tabPurchase Invoice Item`.qty * ifnull(`tabPurchase Invoice Item`.conversion_factor, 1))"
	signed_invoice_stock_qty = f"case when ifnull(`tabPurchase Invoice`.is_return, 0) = 1 then -abs({invoice_stock_qty}) else abs({invoice_stock_qty}) end"

	rows = frappe.db.sql(
		f"""
		select
			`tabPurchase Invoice Item`.item_code as item_code,
			sum(
				case when `tabPurchase Invoice`.posting_date < %(period_start)s
				then {signed_invoice_stock_qty}
				else 0 end
			) as previous_qty,
			sum(
				case when `tabPurchase Invoice`.posting_date between %(period_start)s and %(period_end)s
				then {signed_invoice_stock_qty}
				else 0 end
			) as current_qty
		from `tabPurchase Invoice`
		inner join `tabPurchase Invoice Item`
			on `tabPurchase Invoice Item`.parent = `tabPurchase Invoice`.name
		left join `tabSite Material Consumption`
			on `tabPurchase Invoice`.site_material_consumption = `tabSite Material Consumption`.name
		inner join `tabItem`
			on `tabItem`.name = `tabPurchase Invoice Item`.item_code
		where {" and ".join(conditions)}
		group by `tabPurchase Invoice Item`.item_code
		""",
		values,
		as_dict=True,
	)
	return rows_by_item(rows)


def get_consumed_quantities(filters, period):
	conditions, values = get_material_issued_conditions(filters, period)
	conditions.append("ifnull(`tabSite Material Consumption`.transaction_type, 'Material Issue') = 'Material Issue'")
	add_match_condition(conditions, "Site Material Consumption")

	rows = frappe.db.sql(
		f"""
		select
			`tabSite Material Consumption Item`.item_code as item_code,
			sum(
				case when `tabSite Material Consumption`.posting_date < %(period_start)s
				then `tabSite Material Consumption Item`.qty * ifnull(`tabSite Material Consumption Item`.conversion_factor, 1)
				else 0 end
			) as previous_qty,
			sum(
				case when `tabSite Material Consumption`.posting_date between %(period_start)s and %(period_end)s
				then `tabSite Material Consumption Item`.qty * ifnull(`tabSite Material Consumption Item`.conversion_factor, 1)
				else 0 end
			) as current_qty
		from `tabSite Material Consumption`
		inner join `tabSite Material Consumption Item`
			on `tabSite Material Consumption Item`.parent = `tabSite Material Consumption`.name
		inner join `tabItem`
			on `tabItem`.name = `tabSite Material Consumption Item`.item_code
		where {" and ".join(conditions)}
		group by `tabSite Material Consumption Item`.item_code
		""",
		values,
		as_dict=True,
	)
	return rows_by_item(rows)


def get_returned_quantities(filters, period):
	returned = defaultdict(lambda: {"previous_qty": 0, "current_qty": 0})
	for rows in (
		get_direct_returned_quantities(filters, period),
		get_site_material_return_quantities(filters, period),
	):
		for item_code, row in rows.items():
			returned[item_code]["previous_qty"] += flt(row.get("previous_qty"))
			returned[item_code]["current_qty"] += flt(row.get("current_qty"))
	return returned


def get_direct_returned_quantities(filters, period):
	conditions, values = get_material_returned_conditions(filters, period)
	conditions.append("ifnull(`tabSite Material Consumption`.transaction_type, 'Material Issue') = 'Material Issue'")
	conditions.append("return_se.docstatus = 1")
	conditions.append("return_se.is_return = 1")
	add_match_condition(conditions, "Site Material Consumption")

	rows = frappe.db.sql(
		f"""
		select
			return_item.item_code as item_code,
			sum(
				case when return_se.posting_date < %(period_start)s
				then coalesce(return_item.transfer_qty, return_item.qty * ifnull(return_item.conversion_factor, 1)) else 0 end
			) as previous_qty,
			sum(
				case when return_se.posting_date between %(period_start)s and %(period_end)s
				then coalesce(return_item.transfer_qty, return_item.qty * ifnull(return_item.conversion_factor, 1)) else 0 end
			) as current_qty
		from `tabSite Material Consumption`
		inner join `tabStock Entry` original_se
			on original_se.name = `tabSite Material Consumption`.stock_entry
		inner join `tabStock Entry` return_se
			on return_se.is_return = 1
		inner join `tabStock Entry Detail` return_item
			on return_item.parent = return_se.name
			and return_item.against_stock_entry = original_se.name
		inner join `tabItem`
			on `tabItem`.name = return_item.item_code
		where {" and ".join(conditions)}
		group by return_item.item_code
		""",
		values,
		as_dict=True,
	)
	return rows_by_item(rows)


def get_site_material_return_quantities(filters, period):
	conditions, values = get_material_issued_conditions(filters, period)
	conditions.append("ifnull(`tabSite Material Consumption`.transaction_type, 'Material Issue') = 'Material Return'")
	add_match_condition(conditions, "Site Material Consumption")

	rows = frappe.db.sql(
		f"""
		select
			`tabSite Material Consumption Item`.item_code as item_code,
			sum(
				case when `tabSite Material Consumption`.posting_date < %(period_start)s
				then `tabSite Material Consumption Item`.qty * ifnull(`tabSite Material Consumption Item`.conversion_factor, 1)
				else 0 end
			) as previous_qty,
			sum(
				case when `tabSite Material Consumption`.posting_date between %(period_start)s and %(period_end)s
				then `tabSite Material Consumption Item`.qty * ifnull(`tabSite Material Consumption Item`.conversion_factor, 1)
				else 0 end
			) as current_qty
		from `tabSite Material Consumption`
		inner join `tabSite Material Consumption Item`
			on `tabSite Material Consumption Item`.parent = `tabSite Material Consumption`.name
		inner join `tabItem`
			on `tabItem`.name = `tabSite Material Consumption Item`.item_code
		where {" and ".join(conditions)}
		group by `tabSite Material Consumption Item`.item_code
		""",
		values,
		as_dict=True,
	)
	return rows_by_item(rows)


def get_material_returned_conditions(filters, period):
	conditions = [
		"`tabSite Material Consumption`.docstatus = 1",
		"`tabSite Material Consumption`.stock_entry is not null",
	]
	values = {"period_start": period.start, "period_end": period.end}

	add_filter(conditions, values, "`tabSite Material Consumption`.company", "company", filters)
	add_filter(conditions, values, "`tabSite Material Consumption`.subcontractor_supplier", "supplier", filters)
	add_filter(conditions, values, "return_item.item_code", "item", filters)
	add_filter(conditions, values, "`tabItem`.item_group", "item_group", filters)

	if filters.get("project"):
		conditions.append("`tabSite Material Consumption`.project in %(projects)s")
		values["projects"] = get_project_filter_values(filters.project)

	return conditions, values


def get_purchase_invoice_conditions(filters, period):
	conditions = [
		"`tabPurchase Invoice`.docstatus = 1",
		"(`tabSite Material Consumption`.name is null or `tabSite Material Consumption`.docstatus = 1)",
		"`tabPurchase Invoice`.posting_date <= %(period_end)s",
	]
	values = {"period_start": period.start, "period_end": period.end}

	add_filter(conditions, values, "`tabPurchase Invoice`.company", "company", filters)
	add_filter(conditions, values, "`tabPurchase Invoice`.supplier", "supplier", filters)
	add_filter(conditions, values, "`tabPurchase Invoice Item`.item_code", "item", filters)
	add_filter(conditions, values, "`tabItem`.item_group", "item_group", filters)

	if filters.get("project"):
		values["projects"] = get_project_filter_values(filters.project)
		conditions.append(
			"coalesce(nullif(`tabPurchase Invoice Item`.project, ''), nullif(`tabPurchase Invoice`.project, ''), `tabSite Material Consumption`.project) in %(projects)s"
		)

	return conditions, values


def get_purchase_order_conditions(filters, period):
	conditions = [
		"`tabPurchase Order`.docstatus = 1",
		"`tabPurchase Order`.transaction_date <= %(period_end)s",
	]
	values = {"period_start": period.start, "period_end": period.end}

	add_filter(conditions, values, "`tabPurchase Order`.company", "company", filters)
	add_filter(conditions, values, "`tabPurchase Order`.supplier", "supplier", filters)
	add_filter(conditions, values, "`tabPurchase Order Item`.item_code", "item", filters)
	add_filter(conditions, values, "`tabItem`.item_group", "item_group", filters)

	if filters.get("project"):
		values["projects"] = get_project_filter_values(filters.project)
		conditions.append(
			"coalesce(nullif(`tabPurchase Order Item`.project, ''), `tabPurchase Order`.project) in %(projects)s"
		)

	return conditions, values


def get_material_issued_conditions(filters, period):
	conditions = [
		"`tabSite Material Consumption`.docstatus = 1",
		"`tabSite Material Consumption`.posting_date <= %(period_end)s",
	]
	values = {"period_start": period.start, "period_end": period.end}

	add_filter(conditions, values, "`tabSite Material Consumption`.company", "company", filters)
	add_filter(conditions, values, "`tabSite Material Consumption`.subcontractor_supplier", "supplier", filters)
	add_filter(conditions, values, "`tabSite Material Consumption Item`.item_code", "item", filters)
	add_filter(conditions, values, "`tabItem`.item_group", "item_group", filters)

	if filters.get("project"):
		conditions.append("`tabSite Material Consumption`.project in %(projects)s")
		values["projects"] = get_project_filter_values(filters.project)

	return conditions, values


def add_filter(conditions, values, db_field, filter_name, filters):
	if filters.get(filter_name):
		conditions.append(f"{db_field} = %({filter_name})s")
		values[filter_name] = filters.get(filter_name)


def add_match_condition(conditions, doctype):
	match_cond = get_match_cond(doctype)
	if match_cond:
		conditions.append(match_cond.removeprefix(" and ").strip())


def get_project_filter_values(project):
	projects = [project]
	meta = frappe.get_meta("Project")
	if meta.has_field("lft") and meta.has_field("rgt"):
		bounds = frappe.db.get_value("Project", project, ["lft", "rgt"], as_dict=True)
		if bounds and bounds.lft and bounds.rgt:
			projects = frappe.get_all(
				"Project",
				filters={"lft": [">=", bounds.lft], "rgt": ["<=", bounds.rgt]},
				pluck="name",
			)
	return tuple(projects or [project])


def rows_by_item(rows):
	result = defaultdict(dict)
	for row in rows:
		result[row.item_code] = {
			"previous_qty": flt(row.previous_qty),
			"current_qty": flt(row.current_qty),
		}
	return result


def get_item_rows(filters, period, received, consumed, returned):
	purchase_item_codes, purchase_invoice_item_details = get_purchase_invoice_item_details(filters, period)
	consumption_item_codes, consumption_item_details = get_site_material_consumption_item_details(filters, period)
	item_details = {**consumption_item_details, **purchase_invoice_item_details}
	item_rows = []
	item_codes = sorted(purchase_item_codes | consumption_item_codes)

	for item_code in item_codes:
		details = item_details[item_code]
		item_description = details.get("description") or details.get("item_name") or item_code
		uom = details.get("uom") or ""

		item_rows.append(
			{
				"item_code": item_code,
				"item_description": item_description,
				"uom": uom,
			}
		)

	return item_rows


def get_purchase_invoice_item_details(filters, period):
	if not frappe.has_permission("Purchase Invoice", "read"):
		return set(), {}

	conditions, values = get_purchase_invoice_conditions(filters, period)
	add_match_condition(conditions, "Purchase Invoice")
	item_join = ""
	if filters.get("item_group"):
		item_join = """
		inner join `tabItem`
			on `tabItem`.name = `tabPurchase Invoice Item`.item_code
		"""
	conditions.append("`tabPurchase Invoice Item`.parent = `tabPurchase Invoice`.name")

	rows = frappe.db.sql(
		f"""
		select distinct
			`tabPurchase Invoice Item`.item_code as item_code,
			`tabPurchase Invoice Item`.item_name as item_name,
			`tabPurchase Invoice Item`.description as description,
			coalesce(`tabPurchase Invoice Item`.stock_uom, `tabPurchase Invoice Item`.uom) as uom
		from `tabPurchase Invoice`
		left join `tabSite Material Consumption`
			on `tabPurchase Invoice`.site_material_consumption = `tabSite Material Consumption`.name
		inner join `tabPurchase Invoice Item`
			on `tabPurchase Invoice Item`.parent = `tabPurchase Invoice`.name
		{item_join}
		where {" and ".join(conditions)}
		""",
		values,
		as_dict=True,
	)
	return item_details_by_item(rows)


def get_site_material_consumption_item_details(filters, period):
	conditions, values = get_material_issued_conditions(filters, period)
	add_match_condition(conditions, "Site Material Consumption")
	item_join = ""
	if filters.get("item_group"):
		item_join = """
		inner join `tabItem`
			on `tabItem`.name = `tabSite Material Consumption Item`.item_code
		"""

	rows = frappe.db.sql(
		f"""
		select distinct
			`tabSite Material Consumption Item`.item_code as item_code,
			`tabSite Material Consumption Item`.item_name as item_name,
			`tabSite Material Consumption Item`.description as description,
			coalesce(`tabSite Material Consumption Item`.stock_uom, `tabSite Material Consumption Item`.uom) as uom
		from `tabSite Material Consumption`
		inner join `tabSite Material Consumption Item`
			on `tabSite Material Consumption Item`.parent = `tabSite Material Consumption`.name
		{item_join}
		where {" and ".join(conditions)}
		""",
		values,
		as_dict=True,
	)
	return item_details_by_item(rows)


def item_details_by_item(rows):
	details_by_item = defaultdict(set)
	for row in rows:
		details_by_item[row.item_code].add(
			(
				row.get("item_name") or "",
				row.get("description") or "",
				row.get("uom") or "",
			)
		)

	item_details = {}
	for item_code, details in details_by_item.items():
		if len(details) == 1:
			values = next(iter(details))
			item_details[item_code] = {
				"item_name": values[0],
				"description": values[1],
				"uom": values[2],
			}
			continue

		# Keep the eligible item, but never choose an arbitrary invoice description.
		uoms = {values[2] for values in details if values[2]}
		item_details[item_code] = {
			"item_name": "",
			"description": "",
			"uom": next(iter(uoms)) if len(uoms) == 1 else "",
		}

	return set(details_by_item), item_details
