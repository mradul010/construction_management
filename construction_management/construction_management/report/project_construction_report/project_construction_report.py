from frappe import _

from construction_management.construction_management.report.report_utils import (
	average_field,
	ensure_report_access,
	first_currency,
	get_project_construction_rows,
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
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 170},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 160},
		{
			"label": _("Current Active BOQ"),
			"fieldname": "current_active_boq",
			"fieldtype": "Link",
			"options": "BOQ",
			"width": 170,
		},
		{"label": _("BOQ Value"), "fieldname": "boq_value", "fieldtype": "Currency", "options": "currency", "width": 130},
		{
			"label": _("Total RA Billed"),
			"fieldname": "total_ra_billed",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
		{
			"label": _("Total Net Payable"),
			"fieldname": "total_net_payable",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 160,
		},
		{
			"label": _("Total Invoiced"),
			"fieldname": "total_invoiced",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		},
		{
			"label": _("Retention Held"),
			"fieldname": "total_retention_held",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		},
		{
			"label": _("Retention Release Invoiced"),
			"fieldname": "total_retention_invoiced",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 190,
		},
		{
			"label": _("Retention Paid"),
			"fieldname": "total_retention_paid",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		},
		{
			"label": _("Retention Outstanding"),
			"fieldname": "total_retention_outstanding",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 170,
		},
		{
			"label": _("Retention Balance"),
			"fieldname": "retention_balance",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
		{"label": _("Work Completion %"), "fieldname": "work_completion_percent", "fieldtype": "Percent", "width": 150},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
	]


def get_data(filters):
	return get_project_construction_rows(filters)


def get_report_summary(data):
	currency = first_currency(data)
	return [
		summary_metric("Total BOQ Amount", sum_field(data, "boq_value"), currency=currency),
		summary_metric("Total RA Billed", sum_field(data, "total_ra_billed"), currency=currency),
		summary_metric("Total Invoiced", sum_field(data, "total_invoiced"), currency=currency),
		summary_metric("Retention Held", sum_field(data, "total_retention_held"), currency=currency),
		summary_metric("Retention Release Invoiced", sum_field(data, "total_retention_invoiced"), currency=currency),
		summary_metric("Retention Paid", sum_field(data, "total_retention_paid"), currency=currency),
		summary_metric("Retention Outstanding", sum_field(data, "total_retention_outstanding"), currency=currency),
		summary_metric("Retention Balance", sum_field(data, "retention_balance"), currency=currency),
		summary_metric("Average Completion %", average_field(data, "work_completion_percent"), datatype="Percent"),
	]
