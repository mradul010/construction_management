import frappe

from construction_management.portal_utils import log_portal_access, require_portal_customer


no_cache = 1


def get_context(context):
	customer = require_portal_customer()
	log_portal_access(customer)
	context.title = "RA Bill"
	context.customer = customer
	context.ra_bills = frappe.get_all(
		"RA Bill",
		filters={"customer": customer},
		fields=[
			"name",
			"bill_no",
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
