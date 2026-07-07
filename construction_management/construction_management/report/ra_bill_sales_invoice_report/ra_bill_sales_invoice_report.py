from frappe import _

from construction_management.construction_management.report.report_utils import (
	ensure_report_access,
	first_currency,
	get_invoice_rows_for_ra_bills,
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
		{
			"label": _("Sales Invoice"),
			"fieldname": "sales_invoice",
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 170,
		},
		{"label": _("RA Bill"), "fieldname": "ra_bill", "fieldtype": "Link", "options": "RA Bill", "width": 160},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 160},
		{"label": _("BOQ"), "fieldname": "boq", "fieldtype": "Link", "options": "BOQ", "width": 160},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 160},
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 115},
		{"label": _("Grand Total"), "fieldname": "grand_total", "fieldtype": "Currency", "options": "currency", "width": 140},
		{
			"label": _("Outstanding Amount"),
			"fieldname": "outstanding_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 160,
		},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 120},
	]


def get_data(filters):
	if filters.get("ra_bill_status"):
		filters.status = filters.ra_bill_status

	ra_bills = get_ra_bill_rows(filters, require_invoice=True)
	rows = get_invoice_rows_for_ra_bills(ra_bills)

	if filters.get("invoice_status"):
		rows = [row for row in rows if row.get("status") == filters.invoice_status]

	return rows


def get_report_summary(data):
	currency = first_currency(data)
	return [
		summary_metric("Total Invoiced", sum_field(data, "grand_total"), currency=currency),
		summary_metric("Total Outstanding", sum_field(data, "outstanding_amount"), currency=currency),
	]
