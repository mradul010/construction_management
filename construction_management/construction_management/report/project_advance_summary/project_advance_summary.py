import frappe
from frappe import _
from frappe.utils import flt

from construction_management.construction_management.advance_management import (
	get_sales_order_advance_summary,
	get_sales_order_last_advance_receipt_date,
	get_sales_order_last_advance_recovery_date,
)
from construction_management.construction_management.report.report_utils import (
	ensure_report_access,
	first_currency,
	parse_filters,
	summary_metric,
)


def execute(filters=None):
	filters = parse_filters(filters)
	ensure_report_access()
	data = get_data(filters)
	return get_columns(), data, None, None, get_report_summary(data)


def get_columns():
	return [
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 160},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 160},
		{"label": _("Sales Order"), "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 170},
		{"label": _("Sales Order Value"), "fieldname": "sales_order_value", "fieldtype": "Currency", "options": "currency", "width": 170},
		{"label": _("Advance Received"), "fieldname": "advance_received", "fieldtype": "Currency", "options": "currency", "width": 160},
		{"label": _("Advance Recovered"), "fieldname": "advance_recovered", "fieldtype": "Currency", "options": "currency", "width": 160},
		{"label": _("Remaining Advance"), "fieldname": "remaining_advance", "fieldtype": "Currency", "options": "currency", "width": 170},
		{"label": _("Recovery %"), "fieldname": "recovery_percent", "fieldtype": "Percent", "width": 120},
		{"label": _("Last Receipt Date"), "fieldname": "last_receipt_date", "fieldtype": "Date", "width": 140},
		{"label": _("Last Recovery Date"), "fieldname": "last_recovery_date", "fieldtype": "Date", "width": 145},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
	]


def get_data(filters):
	conditions = ["so.`docstatus` = 1"]
	params = {}

	if filters.get("company"):
		conditions.append("so.`company` = %(company)s")
		params["company"] = filters.company
	if filters.get("project"):
		conditions.append("so.`project` = %(project)s")
		params["project"] = filters.project
	if filters.get("customer"):
		conditions.append("so.`customer` = %(customer)s")
		params["customer"] = filters.customer
	if filters.get("sales_order"):
		conditions.append("so.`name` = %(sales_order)s")
		params["sales_order"] = filters.sales_order
	if filters.get("project_status"):
		conditions.append("p.`status` = %(project_status)s")
		params["project_status"] = filters.project_status
	if filters.get("from_date"):
		conditions.append("so.`transaction_date` >= %(from_date)s")
		params["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("so.`transaction_date` <= %(to_date)s")
		params["to_date"] = filters.to_date

	sales_orders = frappe.db.sql(
		f"""
		SELECT
			so.`name`,
			so.`project`,
			so.`customer`,
			so.`grand_total`,
			so.`base_grand_total`,
			so.`currency`,
			so.`company`,
			so.`conversion_rate`,
			so.`status`
		FROM `tabSales Order` so
		LEFT JOIN `tabProject` p ON p.`name` = so.`project`
		WHERE {" AND ".join(conditions)}
			AND COALESCE(so.`project`, '') != ''
		ORDER BY so.`project` asc, so.`transaction_date` asc, so.`name` asc
		""",
		params,
		as_dict=True,
	)

	rows = []
	currencies = {row.currency for row in sales_orders if row.get("currency")}
	use_base_currency = len(currencies) > 1
	for sales_order in sales_orders:
		summary = get_sales_order_advance_summary(sales_order.name)
		received = flt(summary.total_advance_received)
		recovered = flt(summary.total_advance_recovered)
		currency = sales_order.currency
		sales_order_value = flt(sales_order.grand_total)
		if use_base_currency:
			conversion_rate = flt(sales_order.conversion_rate or 1)
			received *= conversion_rate
			recovered *= conversion_rate
			sales_order_value = flt(sales_order.base_grand_total)
			currency = frappe.get_cached_value("Company", sales_order.company, "default_currency")
		remaining = max(received - recovered, 0)
		rows.append(
			{
				"project": sales_order.project,
				"customer": sales_order.customer,
				"sales_order": sales_order.name,
				"currency": currency,
				"sales_order_value": sales_order_value,
				"advance_received": received,
				"advance_recovered": recovered,
				"remaining_advance": remaining,
				"recovery_percent": (recovered / received * 100) if received else 0,
				"last_receipt_date": get_sales_order_last_advance_receipt_date(sales_order.name),
				"last_recovery_date": get_sales_order_last_advance_recovery_date(sales_order.name),
				"status": sales_order.status,
			}
		)
	return rows


def get_report_summary(data):
	currency = first_currency(data)
	total_received = sum(flt(row.get("advance_received")) for row in data)
	total_recovered = sum(flt(row.get("advance_recovered")) for row in data)
	total_remaining = sum(flt(row.get("remaining_advance")) for row in data)
	return [
		summary_metric("Customer Advance Received", total_received, currency=currency),
		summary_metric("Advance Recovered", total_recovered, currency=currency),
		summary_metric("Remaining Advance", total_remaining, currency=currency),
		summary_metric(
			"Average Advance Recovery %",
			(total_recovered / total_received * 100) if total_received else 0,
			datatype="Percent",
		),
	]
