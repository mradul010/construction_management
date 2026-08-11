import frappe
from frappe import _

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
	return get_columns(), get_data(filters)


def ensure_access():
	if frappe.session.user == "Administrator":
		return
	if set(frappe.get_roles()) & REPORT_ROLES:
		return
	frappe.throw(_("Not permitted"), frappe.PermissionError)


def get_columns():
	return [
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{
			"label": _("Consumption No"),
			"fieldname": "consumption_no",
			"fieldtype": "Link",
			"options": "Site Material Consumption",
			"width": 170,
		},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 150},
		{"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 180},
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{"label": _("Consumed Qty"), "fieldname": "consumed_qty", "fieldtype": "Float", "width": 120},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 90},
		{"label": _("Valuation Rate"), "fieldname": "valuation_rate", "fieldtype": "Currency", "width": 130},
		{"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 120},
		{
			"label": _("Expense Account"),
			"fieldname": "expense_account",
			"fieldtype": "Link",
			"options": "Account",
			"width": 180,
		},
		{"label": _("Cost Center"), "fieldname": "cost_center", "fieldtype": "Link", "options": "Cost Center", "width": 150},
		{"label": _("Stock Entry"), "fieldname": "stock_entry", "fieldtype": "Link", "options": "Stock Entry", "width": 170},
	]


def get_data(filters):
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
			smc.posting_date,
			smc.name as consumption_no,
			smc.project,
			smc.source_warehouse as warehouse,
			item.item_code,
			item.item_name,
			item.qty as consumed_qty,
			item.uom,
			item.valuation_rate,
			item.amount,
			item.expense_account,
			coalesce(item.cost_center, smc.cost_center) as cost_center,
			smc.stock_entry
		from `tabSite Material Consumption` smc
		inner join `tabSite Material Consumption Item` item on item.parent = smc.name
		where {" and ".join(conditions)}
		order by smc.posting_date desc, smc.name desc, item.idx asc
		""",
		values,
		as_dict=True,
	)
