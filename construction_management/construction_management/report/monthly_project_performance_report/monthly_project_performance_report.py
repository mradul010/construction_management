import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate, today

from construction_management.construction_management.report.report_utils import (
	ensure_report_access,
	format_currency_with_code,
	get_project_rows,
	parse_filters,
	sum_field,
	summary_metric,
)
from construction_management.portal_utils import get_project_monthly_performance_data


def execute(filters=None):
	filters = parse_filters(filters)
	ensure_report_access()
	columns = get_columns()
	data = get_data(filters)
	return columns, data, None, None, get_report_summary(data)


def get_columns():
	return [
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 170},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 170},
		{"label": _("Period"), "fieldname": "period", "fieldtype": "Data", "width": 210},
		{"label": _("Work Completion %"), "fieldname": "work_completion_percent", "fieldtype": "Percent", "width": 150},
		{"label": _("Billing Progress %"), "fieldname": "billing_progress_percent", "fieldtype": "Percent", "width": 150},
		{"label": _("Collection Progress %"), "fieldname": "collection_progress_percent", "fieldtype": "Percent", "width": 160},
		{"label": _("Monthly RA Bills"), "fieldname": "monthly_ra_bills", "fieldtype": "Int", "width": 130},
		{
			"label": _("Monthly RA Billed"),
			"fieldname": "monthly_ra_billed",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 160,
		},
		{"label": _("Monthly Invoices"), "fieldname": "monthly_invoices", "fieldtype": "Int", "width": 130},
		{
			"label": _("Monthly Invoiced"),
			"fieldname": "monthly_invoiced",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 160,
		},
		{
			"label": _("Monthly Receipts"),
			"fieldname": "monthly_receipts",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 160,
		},
		{
			"label": _("Outstanding Receivable"),
			"fieldname": "outstanding_receivable",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 180,
		},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
	]


def get_data(filters):
	to_date = getdate(filters.get("to_date") or today())
	from_date = getdate(filters.get("from_date") or to_date.replace(day=1))
	rows = []
	for project in get_project_rows(filters):
		if not project.get("customer"):
			continue

		performance = get_project_monthly_performance_data(project, [project.customer], to_date)
		monthly_ra_bills = [
			row
			for row in performance.financials.ra_bills
			if row.posting_date and from_date <= getdate(row.posting_date) <= to_date
		]
		monthly_invoices = [
			row
			for row in performance.financials.invoices
			if row.posting_date and from_date <= getdate(row.posting_date) <= to_date
		]
		monthly_receipts = [
			row
			for row in performance.monthly_statement
			if row.type in ("Invoice Payment", "Advance Receipt") and from_date <= getdate(row.posting_date) <= to_date
		]
		financials = performance.financials
		rows.append(
			frappe._dict(
				{
					"project": project.name,
					"customer": project.customer,
					"currency": financials.currency,
					"period": _("{0} to {1}").format(formatdate(from_date), formatdate(to_date)),
					"work_completion_percent": financials.physical_progress,
					"billing_progress_percent": financials.billing_progress,
					"collection_progress_percent": financials.collection_progress,
					"monthly_ra_bills": len(monthly_ra_bills),
					"monthly_ra_billed": sum_field(monthly_ra_bills, "gross_amount"),
					"monthly_invoices": len(monthly_invoices),
					"monthly_invoiced": sum(flt(row.invoice_amount) for row in monthly_invoices),
					"monthly_receipts": sum_field(monthly_receipts, "amount"),
					"outstanding_receivable": financials.invoice_outstanding,
					"status": project.status,
				}
			)
		)
	return rows


def get_report_summary(data):
	currency = data[0].currency if data else None
	return [
		{"value": len(data), "label": _("Projects"), "datatype": "Int", "indicator": "Blue"},
		summary_metric("Monthly RA Billed", sum_field(data, "monthly_ra_billed"), currency=currency),
		summary_metric("Monthly Invoiced", sum_field(data, "monthly_invoiced"), currency=currency),
		summary_metric("Monthly Receipts", sum_field(data, "monthly_receipts"), currency=currency),
		{
			"value": format_currency_with_code(sum_field(data, "outstanding_receivable"), currency),
			"label": _("Outstanding Receivable"),
			"datatype": "Data",
			"indicator": "Orange",
		},
	]
