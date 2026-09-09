import frappe
from frappe import _
from frappe.utils import cint

from construction_management.construction_management.report.report_utils import ensure_report_access, parse_filters


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
		{"label": _("From Date"), "fieldname": "from_date", "fieldtype": "Date", "width": 110},
		{"label": _("To Date"), "fieldname": "to_date", "fieldtype": "Date", "width": 110},
		{"label": _("Published DPRs"), "fieldname": "published_dprs", "fieldtype": "Int", "width": 130},
		{"label": _("Task Entries"), "fieldname": "task_entries", "fieldtype": "Int", "width": 120},
		{"label": _("Photos"), "fieldname": "photos", "fieldtype": "Int", "width": 100},
		{"label": _("Latest DPR"), "fieldname": "latest_dpr", "fieldtype": "Link", "options": "Daily Progress Report", "width": 170},
		{"label": _("Latest DPR Date"), "fieldname": "latest_dpr_date", "fieldtype": "Date", "width": 130},
		{"label": _("Latest Summary"), "fieldname": "latest_summary", "fieldtype": "Data", "width": 260},
	]


def get_data(filters):
	conditions = ["dpr.docstatus = 1", "dpr.status != 'Cancelled'"]
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
	if filters.get("publish_to_portal") not in (None, "") and cint(filters.publish_to_portal):
		conditions.append("dpr.publish_to_portal = 1")

	rows = frappe.db.sql(
		f"""
		SELECT
			dpr.project,
			dpr.customer,
			MIN(dpr.dpr_date) AS from_date,
			MAX(dpr.dpr_date) AS to_date,
			COUNT(dpr.name) AS published_dprs,
			COALESCE(SUM(tasks.total), 0) AS task_entries,
			COALESCE(SUM(photos.total), 0) AS photos
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
		WHERE {" AND ".join(conditions)}
		GROUP BY dpr.project, dpr.customer
		ORDER BY to_date DESC, dpr.project ASC
		""",
		values,
		as_dict=True,
	)
	latest_by_project = get_latest_dpr_map(filters)
	for row in rows:
		latest = latest_by_project.get((row.project, row.customer))
		if latest:
			row.latest_dpr = latest.name
			row.latest_dpr_date = latest.dpr_date
			row.latest_summary = frappe.utils.strip_html(latest.summary or latest.title or "")
	return rows


def get_latest_dpr_map(filters):
	conditions = ["docstatus = 1", "status != 'Cancelled'"]
	values = {}

	for fieldname in ("project", "customer", "from_date", "to_date"):
		if not filters.get(fieldname):
			continue
		if fieldname == "from_date":
			conditions.append("dpr_date >= %(from_date)s")
		elif fieldname == "to_date":
			conditions.append("dpr_date <= %(to_date)s")
		else:
			conditions.append(f"{fieldname} = %({fieldname})s")
		values[fieldname] = filters.get(fieldname)
	if filters.get("publish_to_portal") not in (None, "") and cint(filters.publish_to_portal):
		conditions.append("publish_to_portal = 1")

	latest = {}
	for row in frappe.db.sql(
		f"""
		SELECT name, project, customer, dpr_date, title, summary
		FROM `tabDaily Progress Report`
		WHERE {" AND ".join(conditions)}
		ORDER BY dpr_date DESC, modified DESC, name DESC
		""",
		values,
		as_dict=True,
	):
		latest.setdefault((row.project, row.customer), row)
	return latest


def get_report_summary(data):
	return [
		{"value": len(data), "label": _("Projects with Updates"), "datatype": "Int", "indicator": "Blue"},
		{"value": sum(cint(row.published_dprs) for row in data), "label": _("Published DPRs"), "datatype": "Int", "indicator": "Green"},
		{"value": sum(cint(row.task_entries) for row in data), "label": _("Task Entries"), "datatype": "Int", "indicator": "Blue"},
		{"value": sum(cint(row.photos) for row in data), "label": _("Photos"), "datatype": "Int", "indicator": "Orange"},
	]
