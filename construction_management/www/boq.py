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
	context.boqs = frappe.get_all(
		"BOQ",
		filters={customer_field: customer},
		fields=[
			"name",
			"project",
			customer_field,
			"currency",
			"status",
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
	return frappe.get_doc("BOQ", name)
