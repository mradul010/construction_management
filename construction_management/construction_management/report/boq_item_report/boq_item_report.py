from frappe import _

from construction_management.construction_management.report.report_utils import (
	ensure_report_access,
	first_currency,
	get_boq_item_rows,
	get_boq_rows,
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
		{"label": _("BOQ"), "fieldname": "boq", "fieldtype": "Link", "options": "BOQ", "width": 160},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 160},
		{"label": _("Category"), "fieldname": "category", "fieldtype": "Data", "width": 140},
		{
			"label": _("Sub Category"),
			"fieldname": "sub_category",
			"fieldtype": "Link",
			"options": "BOQ Category",
			"width": 150,
		},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 220},
		{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 90},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 90},
		{"label": _("Unit Cost"), "fieldname": "unit_cost", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Unit Rate"), "fieldname": "unit_rate", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "options": "currency", "width": 130},
		{
			"label": _("Amount After Margin"),
			"fieldname": "amount_after_margin",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 160,
		},
		{"label": _("Margin %"), "fieldname": "margin_percent", "fieldtype": "Percent", "width": 100},
	]


def get_data(filters):
	boq_rows = get_boq_rows(filters)
	return get_boq_item_rows(boq_rows, filters)


def get_report_summary(data):
	currency = first_currency(data)
	return [
		summary_metric("Total Amount", sum_field(data, "amount"), currency=currency),
		summary_metric("Total Amount After Margin", sum_field(data, "amount_after_margin"), currency=currency),
	]
