from frappe import _

from construction_management.construction_management.report.report_utils import (
	average_field,
	ensure_report_access,
	first_currency,
	get_work_progress_rows,
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
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 160},
		{"label": _("BOQ"), "fieldname": "boq", "fieldtype": "Link", "options": "BOQ", "width": 160},
		{"label": _("Category"), "fieldname": "category", "fieldtype": "Data", "width": 140},
		{
			"label": _("Sub Category"),
			"fieldname": "sub_category",
			"fieldtype": "Link",
			"options": "BOQ Category",
			"width": 150,
		},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 220},
		{"label": _("BOQ Qty"), "fieldname": "boq_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Completed Qty"), "fieldname": "completed_qty", "fieldtype": "Float", "width": 120},
		{"label": _("Remaining Qty"), "fieldname": "remaining_qty", "fieldtype": "Float", "width": 120},
		{"label": _("Completion %"), "fieldname": "completion_percent", "fieldtype": "Percent", "width": 120},
		{"label": _("BOQ Amount"), "fieldname": "boq_amount", "fieldtype": "Currency", "options": "currency", "width": 130},
		{
			"label": _("Completed Amount"),
			"fieldname": "completed_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
		{
			"label": _("Remaining Amount"),
			"fieldname": "remaining_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
	]


def get_data(filters):
	return get_work_progress_rows(filters)


def get_report_summary(data):
	currency = first_currency(data)
	return [
		summary_metric("Total BOQ Amount", sum_field(data, "boq_amount"), currency=currency),
		summary_metric("Total Completed Amount", sum_field(data, "completed_amount"), currency=currency),
		summary_metric("Total Remaining Amount", sum_field(data, "remaining_amount"), currency=currency),
		summary_metric("Average Completion %", average_field(data, "completion_percent"), datatype="Percent"),
	]
