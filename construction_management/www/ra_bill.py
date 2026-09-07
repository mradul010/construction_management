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
		"RA Bills",
		description="Review running account bills and billing status for your projects.",
		parents=[
			{"name": "Construction Portal", "route": "/construction-portal"},
			{"name": "RA Bills", "route": "/ra-bill"},
		],
	)
	context.customer = customer
	context.filters = get_request_filters("search", "project", "status")
	filters = {"customer": customer}
	if context.filters.project:
		filters["project"] = context.filters.project
	if context.filters.status:
		filters["status"] = context.filters.status

	or_filters = []
	search_filter = build_like_filter(context.filters.search)
	if search_filter:
		or_filters = [
			["name", search_filter[0], search_filter[1]],
			["project", search_filter[0], search_filter[1]],
			["boq", search_filter[0], search_filter[1]],
		]

	context.ra_bills = frappe.get_all(
		"RA Bill",
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name",
			"bill_no",
			"ra_bill_no",
			"project",
			"boq",
			"status",
			"billing_period_from",
			"billing_period_to",
			"gross_amount",
			"net_payable",
		],
		order_by="modified desc",
		ignore_permissions=True,
	)
	context.projects = frappe.get_all(
		"RA Bill",
		filters={"customer": customer, "project": ["is", "set"]},
		pluck="project",
		distinct=True,
		ignore_permissions=True,
	)
