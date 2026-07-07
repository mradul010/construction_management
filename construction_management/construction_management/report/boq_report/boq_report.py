from frappe import _
from frappe.utils import cint, flt

from construction_management.construction_management.report.report_utils import (
	ensure_report_access,
	first_currency,
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
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 160},
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 90},
		{"label": _("Revision No"), "fieldname": "revision_no", "fieldtype": "Int", "width": 95},
		{"label": _("Revision Status"), "fieldname": "revision_status", "fieldtype": "Data", "width": 130},
		{"label": _("Active Revision"), "fieldname": "active_revision", "fieldtype": "Check", "width": 110},
		{
			"label": _("Total Cost Amount"),
			"fieldname": "total_cost_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
		{
			"label": _("Amount After Margin"),
			"fieldname": "amount_after_margin",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 160,
		},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": _("Created Date"), "fieldname": "created_date", "fieldtype": "Datetime", "width": 160},
	]


def get_data(filters):
	rows = get_boq_rows(filters)
	data = []
	for row in rows:
		data.append(
			{
				"boq": row.name,
				"project": row.get("project"),
				"customer": row.get("client"),
				"currency": row.get("currency"),
				"revision_no": cint(row.get("revision_no")),
				"revision_status": row.get("revision_status"),
				"active_revision": cint(row.get("is_active_revision")),
				"total_cost_amount": flt(row.get("total_cost")),
				"amount_after_margin": flt(row.get("grand_total")),
				"status": row.get("status"),
				"created_date": row.get("creation"),
			}
		)
	return data


def get_report_summary(data):
	currency = first_currency(data)
	return [
		summary_metric("Total BOQ Amount", sum_field(data, "total_cost_amount"), currency=currency),
		summary_metric("Total Amount After Margin", sum_field(data, "amount_after_margin"), currency=currency),
	]
