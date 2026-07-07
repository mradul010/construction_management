from frappe import _

from construction_management.construction_management.report.report_utils import (
	ensure_report_access,
	first_currency,
	parse_filters,
	sum_field,
	summary_metric,
)
from frappe.utils import flt
import frappe


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
		{"label": _("BOQ"), "fieldname": "boq", "fieldtype": "Link", "options": "BOQ", "width": 160},
		{"label": _("RA Bill"), "fieldname": "ra_bill", "fieldtype": "Link", "options": "RA Bill", "width": 160},
		{
			"label": _("Sales Invoice"),
			"fieldname": "sales_invoice",
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 160,
		},
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
			"label": _("Released Amount"),
			"fieldname": "released_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
		{
			"label": _("Balance Amount"),
			"fieldname": "balance_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
		{"label": _("Release Date"), "fieldname": "release_date", "fieldtype": "Date", "width": 120},
	]


def get_data(filters):
	conditions = []
	params = {}

	for fieldname in ("project", "customer", "boq", "ra_bill", "sales_invoice", "status"):
		if filters.get(fieldname):
			conditions.append(f"rr.`{fieldname}` = %({fieldname})s")
			params[fieldname] = filters.get(fieldname)

	if filters.get("from_date"):
		conditions.append("DATE(COALESCE(rr.`release_date`, rr.`creation`)) >= %(from_date)s")
		params["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("DATE(COALESCE(rr.`release_date`, rr.`creation`)) <= %(to_date)s")
		params["to_date"] = filters.to_date

	where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
	rows = frappe.db.sql(
		f"""
		SELECT
			rr.`name` AS retention_record,
			rr.`project`,
			rr.`customer`,
			rr.`boq`,
			rr.`ra_bill`,
			rr.`sales_invoice`,
			rr.`retention_percent`,
			rr.`gross_amount`,
			rr.`retention_amount`,
			rr.`released_amount`,
			rr.`balance_amount`,
			rr.`status`,
			rr.`release_date`
		FROM `tabRetention Record` rr
		{where_clause}
		ORDER BY rr.`creation` DESC
		""",
		params,
		as_dict=True,
	)

	for row in rows:
		row.currency = None
		row.retention_amount = flt(row.retention_amount)
		row.released_amount = flt(row.released_amount)
		row.balance_amount = flt(row.balance_amount)

	return rows


def get_report_summary(data):
	currency = first_currency(data)
	active_rows = [row for row in data if row.get("status") != "Cancelled"]
	return [
		summary_metric("Total Retention Held", sum_field(active_rows, "retention_amount"), currency=currency),
		summary_metric("Total Released", sum_field(active_rows, "released_amount"), currency=currency),
		summary_metric("Total Balance", sum_field(active_rows, "balance_amount"), currency=currency),
	]
