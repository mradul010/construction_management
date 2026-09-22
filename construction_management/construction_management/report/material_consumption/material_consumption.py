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
	items = get_item_rows(filters, received, consumed, returned)

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
	month = filters.get("month") or calendar.month_name[getdate(nowdate()).month]
	month_number = MONTHS.get(month)
	if not month_number:
		frappe.throw(_("Invalid month {0}.").format(month))

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
	for doctype in ("Purchase Order", "Site Material Consumption", "Item"):
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
				format_returned_qty(returned_current),
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
	conditions, values = get_purchase_order_conditions(filters, period)
	add_match_condition(conditions, "Purchase Order")

	rows = frappe.db.sql(
		f"""
		select
			`tabPurchase Order Item`.item_code as item_code,
			sum(
				case when `tabPurchase Order`.transaction_date < %(period_start)s
				then `tabPurchase Order Item`.qty else 0 end
			) as previous_qty,
			sum(
				case when `tabPurchase Order`.transaction_date between %(period_start)s and %(period_end)s
				then `tabPurchase Order Item`.qty else 0 end
			) as current_qty
		from `tabPurchase Order`
		inner join `tabPurchase Order Item`
			on `tabPurchase Order Item`.parent = `tabPurchase Order`.name
		inner join `tabItem`
			on `tabItem`.name = `tabPurchase Order Item`.item_code
		where {" and ".join(conditions)}
		group by `tabPurchase Order Item`.item_code
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
				then `tabSite Material Consumption Item`.qty
				else 0 end
			) as previous_qty,
			sum(
				case when `tabSite Material Consumption`.posting_date between %(period_start)s and %(period_end)s
				then `tabSite Material Consumption Item`.qty
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
				then return_item.qty else 0 end
			) as previous_qty,
			sum(
				case when return_se.posting_date between %(period_start)s and %(period_end)s
				then return_item.qty else 0 end
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
				then `tabSite Material Consumption Item`.qty
				else 0 end
			) as previous_qty,
			sum(
				case when `tabSite Material Consumption`.posting_date between %(period_start)s and %(period_end)s
				then `tabSite Material Consumption Item`.qty
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


def get_item_rows(filters, received, consumed, returned):
	items_by_code = get_item_master_lookup(filters)
	item_rows = []
	item_codes = list(items_by_code)
	item_codes.extend(sorted((set(received) | set(consumed) | set(returned)) - set(items_by_code)))

	for item_code in item_codes:
		item = items_by_code.get(item_code, {})
		item_rows.append(
			{
				"item_code": item_code,
				"item_description": item.get("item_name") or item.get("description") or item_code,
				"uom": item.get("stock_uom") or "",
			}
		)

	return item_rows


def get_item_master_lookup(filters):
	item_filters = {"disabled": 0, "is_stock_item": 1}
	if filters.get("item"):
		item_filters["name"] = filters.item
	if filters.get("item_group"):
		item_filters["item_group"] = filters.item_group

	items = frappe.get_all(
		"Item",
		filters=item_filters,
		fields=["name", "item_name", "description", "stock_uom", "creation"],
		order_by="creation asc, name asc",
	)
	return {item.name: item for item in items}
