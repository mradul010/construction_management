import frappe

from construction_management.portal_utils import (
	get_boq_customer_field,
	log_portal_access,
	require_portal_customer,
	validate_boq_customer,
)


no_cache = 1


def get_context(context):
	customer = require_portal_customer()
	log_portal_access(customer)
	customer_field = get_boq_customer_field()
	context.title = "BOQ"
	context.customer = customer
	filters = {
		customer_field: customer,
		"is_active_revision": 1,
		"docstatus": ["!=", 2],
	}
	context.boqs = frappe.get_all(
		"BOQ",
		filters=filters,
		fields=[
			"name",
			"project",
			customer_field,
			"currency",
			"status",
			"revision_no",
			"revision_status",
			"grand_total",
		],
		order_by="modified desc",
		ignore_permissions=True,
	)
	for boq in context.boqs:
		boq.client = boq.get(customer_field)


def get_boq(name):
	customer = require_portal_customer()
	validate_boq_customer(name, customer)
	boq = frappe.get_doc("BOQ", name)
	if not boq.get("is_active_revision") or boq.docstatus == 2:
		frappe.throw("Only the active BOQ revision is available in the portal.", frappe.PermissionError)
	return boq
