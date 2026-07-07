from frappe import _
from frappe.utils import cint, flt

from construction_management.construction_management.report.report_utils import (
	ensure_report_access,
	first_currency,
	get_boq_revision_differences,
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
		{"label": _("Original BOQ"), "fieldname": "original_boq", "fieldtype": "Link", "options": "BOQ", "width": 160},
		{"label": _("Revision BOQ"), "fieldname": "revision_boq", "fieldtype": "Link", "options": "BOQ", "width": 160},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 160},
		{"label": _("Revision No"), "fieldname": "revision_no", "fieldtype": "Int", "width": 100},
		{"label": _("Revision Reason"), "fieldname": "revision_reason", "fieldtype": "Small Text", "width": 220},
		{"label": _("Revision Status"), "fieldname": "revision_status", "fieldtype": "Data", "width": 130},
		{"label": _("Active Revision"), "fieldname": "active_revision", "fieldtype": "Check", "width": 115},
		{"label": _("Parent BOQ"), "fieldname": "parent_boq", "fieldtype": "Link", "options": "BOQ", "width": 160},
		{"label": _("Superseded By"), "fieldname": "superseded_by", "fieldtype": "Link", "options": "BOQ", "width": 160},
		{
			"label": _("Total Difference"),
			"fieldname": "total_difference",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
	]


def get_data(filters):
	rows = get_boq_rows(filters)
	if filters.get("original_boq"):
		rows = [
			row
			for row in rows
			if (row.get("original_boq") or row.name) == filters.original_boq
		]

	differences = get_boq_revision_differences([row.name for row in rows])
	data = []
	for row in rows:
		is_revision = cint(row.get("revision_no")) > 0 or bool(row.get("parent_boq"))
		data.append(
			{
				"original_boq": row.get("original_boq") or row.name,
				"revision_boq": row.name,
				"project": row.get("project"),
				"currency": row.get("currency"),
				"revision_no": cint(row.get("revision_no")),
				"revision_reason": row.get("revision_reason"),
				"revision_status": row.get("revision_status"),
				"active_revision": cint(row.get("is_active_revision")),
				"parent_boq": row.get("parent_boq"),
				"superseded_by": row.get("superseded_by"),
				"total_difference": flt(differences.get(row.name)) if is_revision else 0,
			}
		)
	return data


def get_report_summary(data):
	currency = first_currency(data)
	return [
		summary_metric("Total Difference", sum_field(data, "total_difference"), currency=currency),
	]
