from frappe import _

from construction_management.construction_management.report.report_utils import (
	ensure_report_access,
	first_currency,
	format_period,
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
		{"label": _("Bill No"), "fieldname": "bill_no", "fieldtype": "Int", "width": 90},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 160},
		{"label": _("BOQ"), "fieldname": "boq", "fieldtype": "Link", "options": "BOQ", "width": 160},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 160},
		{"label": _("Billing Period"), "fieldname": "billing_period", "fieldtype": "Data", "width": 170},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": _("Gross Amount"), "fieldname": "gross_amount", "fieldtype": "Currency", "options": "currency", "width": 140},
		{"label": _("Retention %"), "fieldname": "retention_percent", "fieldtype": "Percent", "width": 110},
		{
			"label": _("Retention Amount"),
			"fieldname": "retention_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
		{"label": _("Net Payable"), "fieldname": "net_payable", "fieldtype": "Currency", "options": "currency", "width": 140},
		{
			"label": _("Sales Invoice"),
			"fieldname": "sales_invoice",
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 160,
		},
	]


def get_data(filters):
	data = []
	for row in get_ra_bill_rows(filters):
		data.append(
			{
				"ra_bill": row.name,
				"bill_no": row.get("bill_no"),
				"project": row.get("project"),
				"boq": row.get("boq"),
				"customer": row.get("customer"),
				"currency": row.get("currency"),
				"billing_period": format_period(row.get("billing_period_from"), row.get("billing_period_to")),
				"status": row.get("status"),
				"gross_amount": row.get("gross_amount"),
				"retention_percent": row.get("retention_percent"),
				"retention_amount": row.get("retention_amount"),
				"net_payable": row.get("net_payable"),
				"sales_invoice": row.get("sales_invoice"),
			}
		)
	return data


def get_report_summary(data):
	currency = first_currency(data)
	return [
		summary_metric("Total RA Billed", sum_field(data, "gross_amount"), currency=currency),
		summary_metric("Total Retention", sum_field(data, "retention_amount"), currency=currency),
		summary_metric("Total Net Payable", sum_field(data, "net_payable"), currency=currency),
	]
