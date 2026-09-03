from frappe import _

from construction_management.construction_management.report.report_utils import (
	average_field,
	ensure_report_access,
	first_currency,
	get_ra_bill_item_rows,
	get_ra_bill_rows,
	parse_filters,
	sum_field,
	summary_metric,
)


def execute(filters=None):
	filters = parse_filters(filters)
	ensure_report_access()
	columns = get_columns(filters)
	data = get_data(filters)
	report_summary = get_report_summary(data)
	return columns, data, None, None, report_summary


def get_columns(filters=None):
	return [
		{"label": _("RA Bill"), "fieldname": "ra_bill", "fieldtype": "Link", "options": "RA Bill", "width": 160},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 160},
		{"label": _("BOQ"), "fieldname": "boq", "fieldtype": "Link", "options": "BOQ", "width": 160},
		{"label": _("Category"), "fieldname": "category", "fieldtype": "Link", "options": "BOQ Category", "width": 140},
		{
			"label": _("Sub Category"),
			"fieldname": "sub_category",
			"fieldtype": "Link",
			"options": "BOQ Category",
			"width": 150,
		},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 220},
		{"label": _("BOQ Qty"), "fieldname": "boq_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Previous Qty"), "fieldname": "previous_qty", "fieldtype": "Float", "width": 110},
		{"label": _("Current Qty"), "fieldname": "current_qty", "fieldtype": "Float", "width": 110},
		{
			"label": _("Cumulative Quantity"),
			"fieldname": "cumulative_qty",
			"fieldtype": "Float",
			"width": 145,
		},
		{"label": _("Remaining Quantity"), "fieldname": "remaining_qty", "fieldtype": "Float", "width": 145},
		{"label": _("Current Work %"), "fieldname": "current_work_percent", "fieldtype": "Percent", "width": 125},
		{
			"label": _("Current Amount"),
			"fieldname": "current_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		},
	]


def get_data(filters):
	ra_bills = get_ra_bill_rows(filters)
	return get_ra_bill_item_rows(ra_bills, filters)


def get_report_summary(data):
	currency = first_currency(data)
	return [
		summary_metric("Total Current Amount", sum_field(data, "current_amount"), currency=currency),
		summary_metric("Average Current Work %", average_field(data, "current_work_percent"), datatype="Percent"),
	]
