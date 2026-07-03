import frappe

from construction_management.portal_utils import (
	log_portal_access,
	require_portal_customer,
	validate_boq_customer,
)


no_cache = 1


def get_context(context):
	customer = require_portal_customer()
	log_portal_access(customer)
	name = frappe.form_dict.get("name")
	validate_boq_customer(name, customer)

	boq = frappe.get_doc("BOQ", name)
	context.title = boq.name
	context.customer = customer
	context.boq = boq
	context.items = sorted(
		boq.get("items") or [],
		key=lambda row: (
			row.get("boq_parent_category") or "",
			row.get("boq_category") or "",
			row.idx or 0,
		),
	)
