import frappe
from frappe import _
from frappe.utils import flt

from construction_management.construction_management.report.report_utils import parse_filters


REPORT_ROLES = {
	"System Manager",
	"Construction Manager",
	"Site Engineer",
	"Stock Manager",
	"Accounts Manager",
	"Projects Manager",
	"Projects User",
}


def execute(filters=None):
	filters = parse_filters(filters)
	ensure_access()
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def ensure_access():
	if frappe.session.user == "Administrator":
		return
	if set(frappe.get_roles()) & REPORT_ROLES:
		return
	frappe.throw(_("Not permitted"), frappe.PermissionError)


def get_columns():
	return [
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 150},
		{"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 180},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 90},
		{"label": _("Purchased / Received Qty"), "fieldname": "received_qty", "fieldtype": "Float", "width": 170},
		{"label": _("Consumed Qty"), "fieldname": "consumed_qty", "fieldtype": "Float", "width": 120},
		{"label": _("Current Stock Qty"), "fieldname": "current_stock_qty", "fieldtype": "Float", "width": 140},
		{"label": _("Stock Value"), "fieldname": "stock_value", "fieldtype": "Currency", "width": 130},
	]


def get_data(filters):
	rows = {}

	for row in get_received_rows(filters):
		key = get_key(row)
		rows.setdefault(key, base_row(row))
		rows[key]["received_qty"] += flt(row.received_qty)

	for row in get_consumed_rows(filters):
		key = get_key(row)
		rows.setdefault(key, base_row(row))
		rows[key]["project"] = row.project
		rows[key]["consumed_qty"] += flt(row.consumed_qty)

	for row in get_current_stock_rows(filters):
		key = get_key(row)
		rows.setdefault(key, base_row(row))
		rows[key]["current_stock_qty"] = flt(row.current_stock_qty)
		rows[key]["stock_value"] = flt(row.stock_value)

	return sorted(rows.values(), key=lambda d: (d.get("project") or "", d.get("warehouse") or "", d.get("item_code") or ""))


def base_row(row):
	return {
		"project": row.get("project"),
		"warehouse": row.get("warehouse"),
		"item_code": row.get("item_code"),
		"item_name": row.get("item_name"),
		"uom": row.get("uom"),
		"received_qty": 0,
		"consumed_qty": 0,
		"current_stock_qty": 0,
		"stock_value": 0,
	}


def get_key(row):
	return (row.get("project"), row.get("warehouse"), row.get("item_code"))


def get_conditions(filters, alias, warehouse_field="warehouse", item_field="item_code", date_field=None):
	conditions = []
	values = {}

	if filters.get("company"):
		conditions.append(f"{alias}.company = %(company)s")
		values["company"] = filters.company
	if filters.get("project") and frappe.get_meta("Stock Ledger Entry").has_field("project"):
		conditions.append(f"{alias}.project = %(project)s")
		values["project"] = filters.project
	if filters.get("warehouse"):
		conditions.append(f"{alias}.`{warehouse_field}` = %(warehouse)s")
		values["warehouse"] = filters.warehouse
	if filters.get("item"):
		conditions.append(f"{alias}.`{item_field}` = %(item)s")
		values["item"] = filters.item
	if date_field and filters.get("from_date"):
		conditions.append(f"{alias}.`{date_field}` >= %(from_date)s")
		values["from_date"] = filters.from_date
	if date_field and filters.get("to_date"):
		conditions.append(f"{alias}.`{date_field}` <= %(to_date)s")
		values["to_date"] = filters.to_date

	return conditions, values


def get_received_rows(filters):
	conditions, values = get_conditions(filters, "sle", date_field="posting_date")
	conditions.append("sle.is_cancelled = 0")
	conditions.append("sle.actual_qty > 0")
	where = " and ".join(conditions) if conditions else "1=1"

	return frappe.db.sql(
		f"""
		select
			sle.project,
			sle.warehouse,
			sle.item_code,
			item.item_name,
			sle.stock_uom as uom,
			sum(sle.actual_qty) as received_qty
		from `tabStock Ledger Entry` sle
		inner join `tabItem` item on item.name = sle.item_code
		where {where}
		group by sle.project, sle.warehouse, sle.item_code, item.item_name, sle.stock_uom
		""",
		values,
		as_dict=True,
	)


def get_consumed_rows(filters):
	conditions = ["smc.docstatus = 1"]
	values = {}

	if filters.get("company"):
		conditions.append("smc.company = %(company)s")
		values["company"] = filters.company
	if filters.get("project"):
		conditions.append("smc.project = %(project)s")
		values["project"] = filters.project
	if filters.get("warehouse"):
		conditions.append("smc.source_warehouse = %(warehouse)s")
		values["warehouse"] = filters.warehouse
	if filters.get("item"):
		conditions.append("item.item_code = %(item)s")
		values["item"] = filters.item
	if filters.get("from_date"):
		conditions.append("smc.posting_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("smc.posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	return frappe.db.sql(
		f"""
		select
			smc.project,
			smc.source_warehouse as warehouse,
			item.item_code,
			item.item_name,
			item.stock_uom as uom,
			sum(item.qty * ifnull(item.conversion_factor, 1)) as consumed_qty
		from `tabSite Material Consumption` smc
		inner join `tabSite Material Consumption Item` item on item.parent = smc.name
		where {" and ".join(conditions)}
		group by smc.project, smc.source_warehouse, item.item_code, item.item_name, item.stock_uom
		""",
		values,
		as_dict=True,
	)


def get_current_stock_rows(filters):
	conditions = ["item.is_stock_item = 1", "item.disabled = 0"]
	values = {}

	if filters.get("company"):
		conditions.append("wh.company = %(company)s")
		values["company"] = filters.company
	if filters.get("warehouse"):
		conditions.append("bin.warehouse = %(warehouse)s")
		values["warehouse"] = filters.warehouse
	if filters.get("item"):
		conditions.append("bin.item_code = %(item)s")
		values["item"] = filters.item

	return frappe.db.sql(
		f"""
		select
			%(project)s as project,
			bin.warehouse,
			bin.item_code,
			item.item_name,
			item.stock_uom as uom,
			bin.actual_qty as current_stock_qty,
			bin.stock_value
		from `tabBin` bin
		inner join `tabItem` item on item.name = bin.item_code
		inner join `tabWarehouse` wh on wh.name = bin.warehouse
		where {" and ".join(conditions)}
			and (bin.actual_qty != 0 or bin.stock_value != 0)
		""",
		{**values, "project": filters.get("project")},
		as_dict=True,
	)
