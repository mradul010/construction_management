import frappe

from construction_management.portal_utils import (
	get_boq_customer_field,
	get_project_customer_field,
	log_portal_access,
	require_portal_customer,
	setup_portal_context,
)
from construction_management.www.dprs import get_dprs
from construction_management.www.work_progress import get_work_progress


no_cache = 1


def get_context(context):
	customer = require_portal_customer()
	log_portal_access(customer)
	setup_portal_context(
		context,
		"Construction Portal",
		description="A single place to review your construction projects, BOQs, RA Bills, work progress and DPRs.",
	)
	context.customer = customer
	work_progress = get_work_progress(customer)
	context.cards = get_dashboard_cards(customer, work_progress)
	context.recent_boqs = get_recent_boqs(customer)
	context.recent_ra_bills = get_recent_ra_bills(customer)
	context.recent_dprs = get_dprs(customer)[:5]
	context.recent_work_progress = work_progress[:5]


def get_dashboard_cards(customer, work_progress):
	boq_customer_field = get_boq_customer_field()
	project_customer_field = get_project_customer_field()
	project_count = 0
	if project_customer_field:
		project_count = frappe.db.count("Project", {project_customer_field: customer})

	return [
		{"label": "Projects", "value": project_count, "route": "/construction-projects"},
		{
			"label": "Approved BOQs",
			"value": frappe.db.count(
				"BOQ",
				{boq_customer_field: customer, "is_active_revision": 1, "docstatus": ["!=", 2]},
			),
			"route": "/boq",
		},
		{"label": "RA Bills", "value": frappe.db.count("RA Bill", {"customer": customer}), "route": "/ra-bill"},
		{
			"label": "Daily Progress Reports",
			"value": frappe.db.count(
				"Daily Progress Report",
				{
					"customer": customer,
					"docstatus": 1,
					"publish_to_portal": 1,
					"status": ["!=", "Cancelled"],
				},
			),
			"route": "/dprs",
		},
		{"label": "Work Progress Records", "value": len(work_progress), "route": "/work-progress"},
	]


def get_recent_boqs(customer):
	boq_customer_field = get_boq_customer_field()
	rows = frappe.get_all(
		"BOQ",
		filters={boq_customer_field: customer, "is_active_revision": 1, "docstatus": ["!=", 2]},
		fields=["name", "project", "revision_no", "status", "grand_total", "creation"],
		order_by="modified desc",
		limit_page_length=5,
		ignore_permissions=True,
	)
	return rows


def get_recent_ra_bills(customer):
	return frappe.get_all(
		"RA Bill",
		filters={"customer": customer},
		fields=[
			"name",
			"project",
			"billing_period_from",
			"billing_period_to",
			"gross_amount",
			"net_payable",
			"status",
		],
		order_by="modified desc",
		limit_page_length=5,
		ignore_permissions=True,
	)
