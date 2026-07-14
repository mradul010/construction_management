import frappe

from construction_management.portal_utils import (
	get_boq_customer_field,
	log_portal_access,
	require_portal_customer,
	setup_portal_context,
	validate_project_customer,
)
from construction_management.www.dprs import get_dprs
from construction_management.www.work_progress import get_work_progress


no_cache = 1


def get_context(context):
	customer = require_portal_customer()
	log_portal_access(customer)
	name = frappe.form_dict.get("name")
	validate_project_customer(name, customer)
	project = frappe.get_doc("Project", name)
	setup_portal_context(
		context,
		project.project_name or project.name,
		description="Project hub with related BOQs, RA Bills, work progress and DPRs.",
		parents=[
			{"name": "Construction Portal", "route": "/construction-portal"},
			{"name": "Projects", "route": "/construction-projects"},
			{"name": project.project_name or project.name, "route": f"/construction-project-detail?name={project.name}"},
		],
	)
	context.customer = customer
	context.project = project
	context.boqs = get_project_boqs(customer, project.name)
	context.ra_bills = get_project_ra_bills(customer, project.name)
	context.dprs = [row for row in get_dprs(customer) if row.project == project.name][:5]
	context.work_progress = [row for row in get_work_progress(customer) if row.project == project.name][:5]


def get_project_boqs(customer, project):
	boq_customer_field = get_boq_customer_field()
	return frappe.get_all(
		"BOQ",
		filters={
			boq_customer_field: customer,
			"project": project,
			"is_active_revision": 1,
			"docstatus": ["!=", 2],
		},
		fields=["name", "revision_no", "revision_status", "status", "grand_total", "creation"],
		order_by="modified desc",
		limit_page_length=5,
		ignore_permissions=True,
	)


def get_project_ra_bills(customer, project):
	return frappe.get_all(
		"RA Bill",
		filters={"customer": customer, "project": project},
		fields=[
			"name",
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
