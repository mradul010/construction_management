import frappe

from construction_management.portal_utils import (
	build_like_filter,
	get_request_filters,
	log_portal_access,
	require_portal_customer,
	setup_portal_context,
)


no_cache = 1


def get_context(context):
	customer = require_portal_customer()
	log_portal_access(customer)
	setup_portal_context(
		context,
		"Daily Progress Reports",
		description="Track submitted daily progress updates, tasks, photos and notes.",
		parents=[
			{"name": "Construction Portal", "route": "/construction-portal"},
			{"name": "Daily Progress Reports", "route": "/dprs"},
		],
	)
	context.customer = customer
	context.filters = get_request_filters("search", "project", "date")
	context.dprs = get_dprs(customer, context.filters)
	context.projects = frappe.get_all(
		"Daily Progress Report",
		filters={
			"customer": customer,
			"docstatus": 1,
			"publish_to_portal": 1,
			"status": ["!=", "Cancelled"],
			"project": ["is", "set"],
		},
		pluck="project",
		distinct=True,
		ignore_permissions=True,
	)


def get_dprs(customer, request_filters=None):
	filters = {
		"customer": customer,
		"docstatus": 1,
		"publish_to_portal": 1,
		"status": ["!=", "Cancelled"],
	}
	if request_filters:
		if request_filters.project:
			filters["project"] = request_filters.project
		if request_filters.date:
			filters["dpr_date"] = request_filters.date

	or_filters = []
	search_filter = build_like_filter(request_filters.search if request_filters else "")
	if search_filter:
		or_filters = [
			["name", search_filter[0], search_filter[1]],
			["project", search_filter[0], search_filter[1]],
			["title", search_filter[0], search_filter[1]],
			["summary", search_filter[0], search_filter[1]],
		]

	rows = frappe.get_all(
		"Daily Progress Report",
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name",
			"dpr_date",
			"project",
			"title",
			"summary",
			"status",
			"prepared_by",
		],
		order_by="dpr_date desc, modified desc",
		ignore_permissions=True,
	)

	if not rows:
		return []

	counts = get_child_counts([row.name for row in rows])
	for row in rows:
		row.task_count = counts["tasks"].get(row.name, 0)
		row.photo_count = counts["photos"].get(row.name, 0)

	return rows


def get_child_counts(dpr_names):
	counts = {"tasks": {}, "photos": {}}
	for key, doctype, parentfield in (
		("tasks", "DPR Task Completed", "tasks_completed"),
		("photos", "DPR Photo", "photos"),
	):
		for row in frappe.db.sql(
			f"""
			SELECT parent, COUNT(*) AS total
			FROM `tab{doctype}`
			WHERE parent IN %(parents)s
			  AND parenttype = 'Daily Progress Report'
			  AND parentfield = %(parentfield)s
			GROUP BY parent
			""",
			{"parents": tuple(dpr_names), "parentfield": parentfield},
			as_dict=True,
		):
			counts[key][row.parent] = row.total
	return counts
