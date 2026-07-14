import frappe

from construction_management.portal_utils import (
	build_like_filter,
	get_request_filters,
	get_boq_customer_field,
	log_portal_access,
	require_portal_customer,
	setup_portal_context,
	validate_boq_customer,
)


no_cache = 1


def get_context(context):
	customer = require_portal_customer()
	log_portal_access(customer)
	customer_field = get_boq_customer_field()
	setup_portal_context(
		context,
		"BOQ",
		description="View approved Bills of Quantities for your projects.",
		parents=[
			{"name": "Construction Portal", "route": "/construction-portal"},
			{"name": "BOQ", "route": "/boq"},
		],
	)
	context.customer = customer
	context.filters = get_request_filters("search", "project", "status", "revision")
	filters = {
		customer_field: customer,
		"is_active_revision": 1,
		"docstatus": ["!=", 2],
	}
	if context.filters.project:
		filters["project"] = context.filters.project
	if context.filters.status:
		filters["status"] = context.filters.status
	if context.filters.revision:
		filters["revision_no"] = context.filters.revision

	or_filters = []
	search_filter = build_like_filter(context.filters.search)
	if search_filter:
		or_filters = [["name", search_filter[0], search_filter[1]], ["project", search_filter[0], search_filter[1]]]

	context.boqs = frappe.get_all(
		"BOQ",
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name",
			"project",
			customer_field,
			"currency",
			"status",
			"revision_no",
			"revision_status",
			"grand_total",
			"total_cost",
			"creation",
		],
		order_by="modified desc",
		ignore_permissions=True,
	)
	for boq in context.boqs:
		boq.client = boq.get(customer_field)

	context.projects = frappe.get_all(
		"BOQ",
		filters={
			customer_field: customer,
			"is_active_revision": 1,
			"docstatus": ["!=", 2],
			"project": ["is", "set"],
		},
		pluck="project",
		distinct=True,
		ignore_permissions=True,
	)


def get_boq(name):
	customer = require_portal_customer()
	validate_boq_customer(name, customer)
	boq = frappe.get_doc("BOQ", name)
	if not boq.get("is_active_revision") or boq.docstatus == 2:
		frappe.throw("Only the active BOQ revision is available in the portal.", frappe.PermissionError)
	return boq
