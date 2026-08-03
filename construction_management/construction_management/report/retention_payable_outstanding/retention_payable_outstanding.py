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
	data = get_data(filters)
	return get_columns(), data, None, None, get_report_summary(data)


def get_columns():
	return [
		{"label": _("Retention Payable"), "fieldname": "retention_payable", "fieldtype": "Link", "options": "Retention Payable", "width": 170},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 160},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 160},
		{"label": _("SC Bill"), "fieldname": "sc_bill", "fieldtype": "Link", "options": "SC Bill", "width": 160},
		{"label": _("Purchase Invoice"), "fieldname": "purchase_invoice", "fieldtype": "Link", "options": "Purchase Invoice", "width": 170},
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 115},
		{"label": _("Retention %"), "fieldname": "retention_percent", "fieldtype": "Percent", "width": 110},
		{"label": _("Gross Amount"), "fieldname": "gross_amount", "fieldtype": "Currency", "options": "currency", "width": 140},
		{"label": _("Retention Amount"), "fieldname": "retention_amount", "fieldtype": "Currency", "options": "currency", "width": 150},
		{"label": _("Released Amount"), "fieldname": "released_amount", "fieldtype": "Currency", "options": "currency", "width": 145},
		{"label": _("Outstanding Amount"), "fieldname": "outstanding_amount", "fieldtype": "Currency", "options": "currency", "width": 165},
		{"label": _("Balance Amount"), "fieldname": "balance_amount", "fieldtype": "Currency", "options": "currency", "width": 145},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
		{"label": _("Last Payment Entry"), "fieldname": "last_payment_entry", "fieldtype": "Link", "options": "Payment Entry", "width": 180},
	]


def get_data(filters):
	conditions = []
	params = {}

	for fieldname in ("company", "project", "supplier", "sc_bill", "purchase_invoice", "status"):
		if filters.get(fieldname):
			conditions.append(f"rp.`{fieldname}` = %({fieldname})s")
			params[fieldname] = filters.get(fieldname)

	if filters.get("from_date"):
		conditions.append("DATE(COALESCE(rp.`posting_date`, rp.`creation`)) >= %(from_date)s")
		params["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("DATE(COALESCE(rp.`posting_date`, rp.`creation`)) <= %(to_date)s")
		params["to_date"] = filters.to_date

	where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
	rows = frappe.db.sql(
		f"""
		SELECT
			rp.`name` AS retention_payable,
			rp.`company`,
			rp.`project`,
			rp.`supplier`,
			rp.`sc_bill`,
			rp.`purchase_invoice`,
			rp.`posting_date`,
			rp.`company_currency` AS currency,
			rp.`retention_percent`,
			rp.`gross_amount`,
			rp.`retention_amount`,
			rp.`released_amount`,
			rp.`outstanding_amount`,
			rp.`balance_amount`,
			rp.`status`,
			rp.`last_payment_entry`
		FROM `tabRetention Payable` rp
		{where_clause}
		ORDER BY COALESCE(rp.`posting_date`, rp.`creation`) DESC, rp.`creation` DESC
		""",
		params,
		as_dict=True,
	)

	for row in rows:
		row.gross_amount = flt(row.gross_amount)
		row.retention_amount = flt(row.retention_amount)
		row.released_amount = flt(row.released_amount)
		row.outstanding_amount = flt(row.outstanding_amount)
		row.balance_amount = flt(row.balance_amount)

	return rows


def get_report_summary(data):
	currency = first_currency(data)
	active_rows = [row for row in data if row.get("status") != "Cancelled"]
	return [
		summary_metric("Total Retention Payable", sum_field(active_rows, "retention_amount"), currency=currency),
		summary_metric("Released", sum_field(active_rows, "released_amount"), currency=currency),
		summary_metric("Outstanding Retention", sum_field(active_rows, "outstanding_amount"), currency=currency),
		summary_metric("Pending Release", sum_field(active_rows, "balance_amount"), currency=currency),
	]
