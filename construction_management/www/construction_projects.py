import frappe

from construction_management.portal_utils import (
	build_like_filter,
	get_project_customer_field,
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
		"Projects",
		description="View construction projects linked to your customer account.",
		parents=[
			{"name": "Construction Portal", "route": "/construction-portal"},
			{"name": "Projects", "route": "/construction-projects"},
		],
	)
	context.customer = customer
	context.filters = get_request_filters("search", "status")
	context.projects = get_projects(customer, context.filters)


def get_projects(customer, request_filters):
	customer_field = get_project_customer_field()
	if not customer_field:
		return []

	project_meta = frappe.get_meta("Project")
	fields = ["name", "project_name", "status", customer_field, "percent_complete", "expected_start_date", "expected_end_date"]
	if project_meta.has_field("project_code"):
		fields.append("project_code")

	filters = {customer_field: customer}
	if request_filters.status:
		filters["status"] = request_filters.status

	or_filters = []
	search_filter = build_like_filter(request_filters.search)
	if search_filter:
		or_filters = [
			["name", search_filter[0], search_filter[1]],
			["project_name", search_filter[0], search_filter[1]],
		]
		if project_meta.has_field("project_code"):
			or_filters.append(["project_code", search_filter[0], search_filter[1]])

	return frappe.get_all(
		"Project",
		filters=filters,
		or_filters=or_filters,
		fields=fields,
		order_by="modified desc",
		ignore_permissions=True,
	)
