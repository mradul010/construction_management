import frappe
from frappe import _
from frappe.utils import cint


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)
	return columns, data, None, None, get_report_summary(data)


def get_columns():
	return [
		{"label": _("DPR"), "fieldname": "name", "fieldtype": "Link", "options": "Daily Progress Report", "width": 170},
		{"label": _("DPR Date"), "fieldname": "dpr_date", "fieldtype": "Date", "width": 110},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 170},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 170},
		{"label": _("Title"), "fieldname": "title", "fieldtype": "Data", "width": 220},
		{"label": _("Tasks Completed Count"), "fieldname": "tasks_completed_count", "fieldtype": "Int", "width": 160},
		{"label": _("Photos Count"), "fieldname": "photos_count", "fieldtype": "Int", "width": 110},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
		{"label": _("Show on Client Portal"), "fieldname": "publish_to_portal", "fieldtype": "Check", "width": 160},
		{"label": _("Prepared By"), "fieldname": "prepared_by", "fieldtype": "Link", "options": "User", "width": 160},
		{"label": _("Modified"), "fieldname": "modified", "fieldtype": "Datetime", "width": 160},
	]


def get_data(filters):
	conditions = []
	values = {}

	if filters.get("project"):
		conditions.append("dpr.project = %(project)s")
		values["project"] = filters.project
	if filters.get("customer"):
		conditions.append("dpr.customer = %(customer)s")
		values["customer"] = filters.customer
	if filters.get("from_date"):
		conditions.append("dpr.dpr_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("dpr.dpr_date <= %(to_date)s")
		values["to_date"] = filters.to_date
	if filters.get("status"):
		conditions.append("dpr.status = %(status)s")
		values["status"] = filters.status
	if filters.get("publish_to_portal") not in (None, ""):
		conditions.append("dpr.publish_to_portal = %(publish_to_portal)s")
		values["publish_to_portal"] = cint(filters.publish_to_portal)

	where_clause = " AND ".join(conditions) if conditions else "1 = 1"

	return frappe.db.sql(
		f"""
		SELECT
			dpr.name,
			dpr.dpr_date,
			dpr.project,
			dpr.customer,
			dpr.title,
			COALESCE(tasks.total, 0) AS tasks_completed_count,
			COALESCE(photos.total, 0) AS photos_count,
			dpr.status,
			dpr.publish_to_portal,
			dpr.prepared_by,
			dpr.modified
		FROM `tabDaily Progress Report` dpr
		LEFT JOIN (
			SELECT parent, COUNT(*) AS total
			FROM `tabDPR Task Completed`
			WHERE parenttype = 'Daily Progress Report'
			  AND parentfield = 'tasks_completed'
			GROUP BY parent
		) tasks ON tasks.parent = dpr.name
		LEFT JOIN (
			SELECT parent, COUNT(*) AS total
			FROM `tabDPR Photo`
			WHERE parenttype = 'Daily Progress Report'
			  AND parentfield = 'photos'
			GROUP BY parent
		) photos ON photos.parent = dpr.name
		WHERE {where_clause}
		ORDER BY dpr.dpr_date DESC, dpr.modified DESC
		""",
		values,
		as_dict=True,
	)


def get_report_summary(data):
	return [
		{"value": len(data), "label": _("Total DPRs"), "datatype": "Int", "indicator": "Blue"},
		{
			"value": sum(
				1
				for row in data
				if row.status in ("Submitted", "Published") and cint(row.publish_to_portal)
			),
			"label": _("Published DPRs"),
			"datatype": "Int",
			"indicator": "Green",
		},
		{
			"value": sum(1 for row in data if row.status == "Draft"),
			"label": _("Draft DPRs"),
			"datatype": "Int",
			"indicator": "Gray",
		},
		{
			"value": sum(cint(row.tasks_completed_count) for row in data),
			"label": _("Total Task Entries"),
			"datatype": "Int",
			"indicator": "Blue",
		},
		{
			"value": sum(cint(row.photos_count) for row in data),
			"label": _("Total Photos"),
			"datatype": "Int",
			"indicator": "Orange",
		},
		{
			"value": len({row.project for row in data if row.project}),
			"label": _("Projects with DPRs"),
			"datatype": "Int",
			"indicator": "Green",
		},
	]
