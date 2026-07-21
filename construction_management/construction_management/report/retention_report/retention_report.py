import frappe
from frappe import _
from frappe.utils import flt

from construction_management.construction_management.report.report_utils import (
	ensure_report_access,
	first_currency,
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
			"label": _("Retention Record"),
			"fieldname": "retention_record",
			"fieldtype": "Link",
			"options": "Retention Record",
			"width": 170,
		},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 160},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 160},
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 90},
		{"label": _("BOQ"), "fieldname": "boq", "fieldtype": "Link", "options": "BOQ", "width": 160},
		{"label": _("Sales Order"), "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 160},
		{"label": _("RA Bill"), "fieldname": "ra_bill", "fieldtype": "Link", "options": "RA Bill", "width": 160},
		{
			"label": _("Original Sales Invoice"),
			"fieldname": "sales_invoice",
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 160,
		},
		{
			"label": _("Retention Release Sales Invoice"),
			"fieldname": "retention_release_invoice",
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 180,
		},
		{"label": _("Invoice Date"), "fieldname": "invoice_date", "fieldtype": "Date", "width": 115},
		{"label": _("Invoice Status"), "fieldname": "invoice_status", "fieldtype": "Data", "width": 130},
		{"label": _("Release Date"), "fieldname": "release_date", "fieldtype": "Date", "width": 115},
		{"label": _("Retention %"), "fieldname": "retention_percent", "fieldtype": "Percent", "width": 110},
		{"label": _("Gross Amount"), "fieldname": "gross_amount", "fieldtype": "Currency", "options": "currency", "width": 140},
		{
			"label": _("Retention Amount"),
			"fieldname": "retention_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
		{
			"label": _("Retention Release Invoiced"),
			"fieldname": "retention_invoiced_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 190,
		},
		{
			"label": _("Released Amount"),
			"fieldname": "released_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		},
		{
			"label": _("Paid Amount"),
			"fieldname": "paid_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		},
		{
			"label": _("Outstanding Amount"),
			"fieldname": "outstanding_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 160,
		},
		{
			"label": _("Balance Amount"),
			"fieldname": "balance_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
		{"label": _("Last Payment Entry"), "fieldname": "last_payment_entry", "fieldtype": "Link", "options": "Payment Entry", "width": 180},
	]


def get_data(filters):
	conditions = []
	params = {}

	for fieldname in (
		"project",
		"customer",
		"boq",
		"sales_order",
		"ra_bill",
		"sales_invoice",
		"retention_release_invoice",
		"invoice_status",
		"status",
	):
		if filters.get(fieldname):
			conditions.append(f"rr.`{fieldname}` = %({fieldname})s")
			params[fieldname] = filters.get(fieldname)

	if filters.get("from_date"):
		conditions.append("DATE(COALESCE(rr.`release_date`, rr.`invoice_date`, rr.`creation`)) >= %(from_date)s")
		params["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("DATE(COALESCE(rr.`release_date`, rr.`invoice_date`, rr.`creation`)) <= %(to_date)s")
		params["to_date"] = filters.to_date

	where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
	rows = frappe.db.sql(
		f"""
		SELECT
			rr.`name` AS retention_record,
			rr.`project`,
			rr.`customer`,
			rr.`boq`,
			rr.`sales_order`,
			rr.`ra_bill`,
			rr.`sales_invoice`,
			rr.`retention_release_invoice`,
			rr.`invoice_date`,
			rr.`invoice_status`,
			rr.`release_date`,
			rr.`retention_percent`,
			rr.`gross_amount`,
			COALESCE(sipb.`amount`, rr.`retention_amount`) AS retention_amount,
			CASE
				WHEN rsi.`name` IS NOT NULL
					AND COALESCE(rsi.`docstatus`, 0) != 2
					AND COALESCE(rr.`invoice_status`, '') != 'Cancelled'
				THEN COALESCE(sipb.`amount`, rr.`retention_amount`)
				ELSE 0
			END AS retention_invoiced_amount,
			CASE
				WHEN sipb.`name` IS NOT NULL
				THEN GREATEST(0, COALESCE(sipb.`amount`, 0) - COALESCE(sipb.`outstanding_amount`, 0))
				ELSE rr.`paid_amount`
			END AS paid_amount,
			COALESCE(sipb.`outstanding_amount`, rr.`outstanding_amount`) AS outstanding_amount,
			CASE
				WHEN sipb.`name` IS NOT NULL
				THEN GREATEST(0, COALESCE(sipb.`amount`, 0) - COALESCE(sipb.`outstanding_amount`, 0))
				ELSE rr.`released_amount`
			END AS released_amount,
			COALESCE(sipb.`outstanding_amount`, rr.`balance_amount`) AS balance_amount,
			rr.`status`,
			rr.`last_payment_entry`,
			COALESCE(rb.`currency`, rsi.`currency`, osi.`currency`, b.`currency`) AS currency
		FROM `tabRetention Record` rr
		LEFT JOIN `tabRA Bill` rb ON rb.`name` = rr.`ra_bill`
		LEFT JOIN `tabSales Invoice` rsi ON rsi.`name` = rr.`retention_release_invoice`
		LEFT JOIN `tabSales Invoice` osi ON osi.`name` = rr.`sales_invoice`
		LEFT JOIN `tabSales Invoice Payment Breakdown` sipb
			ON sipb.`parent` = rr.`sales_invoice`
			AND sipb.`parenttype` = 'Sales Invoice'
			AND sipb.`parentfield` = 'payment_breakdown'
			AND sipb.`type` IN ('Retention Deduction', 'Retention Receivable')
		LEFT JOIN `tabBOQ` b ON b.`name` = rr.`boq`
		{where_clause}
		ORDER BY COALESCE(rr.`release_date`, rr.`invoice_date`, rr.`creation`) DESC, rr.`creation` DESC
		""",
		params,
		as_dict=True,
	)

	for row in rows:
		row.gross_amount = flt(row.gross_amount)
		row.retention_amount = flt(row.retention_amount)
		row.retention_invoiced_amount = flt(row.retention_invoiced_amount)
		row.paid_amount = flt(row.paid_amount)
		row.outstanding_amount = flt(row.outstanding_amount)
		row.released_amount = flt(row.released_amount)
		row.balance_amount = flt(row.balance_amount)

	return rows


def get_report_summary(data):
	currency = first_currency(data)
	active_rows = [row for row in data if row.get("status") != "Cancelled"]
	return [
		summary_metric("Total Retention Held", sum_field(active_rows, "retention_amount"), currency=currency),
		summary_metric("Total Retention Invoiced", sum_field(active_rows, "retention_invoiced_amount"), currency=currency),
		summary_metric("Total Released", sum_field(active_rows, "released_amount"), currency=currency),
		summary_metric("Total Paid", sum_field(active_rows, "paid_amount"), currency=currency),
		summary_metric("Total Outstanding", sum_field(active_rows, "outstanding_amount"), currency=currency),
		summary_metric("Total Balance", sum_field(active_rows, "balance_amount"), currency=currency),
	]
