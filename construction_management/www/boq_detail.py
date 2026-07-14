import frappe

from construction_management.portal_utils import (
	log_portal_access,
	require_portal_customer,
	setup_portal_context,
	validate_boq_customer,
)


no_cache = 1


def get_context(context):
	customer = require_portal_customer()
	log_portal_access(customer)
	name = frappe.form_dict.get("name")
	validate_boq_customer(name, customer)

	boq = frappe.get_doc("BOQ", name)
	if not boq.get("is_active_revision") or boq.docstatus == 2:
		frappe.throw(
			"Only the active BOQ revision is available in the portal.",
			frappe.PermissionError,
		)
	setup_portal_context(
		context,
		boq.name,
		description="BOQ details, values and item breakdown.",
		parents=[
			{"name": "Construction Portal", "route": "/construction-portal"},
			{"name": "BOQ", "route": "/boq"},
			{"name": boq.name, "route": f"/boq-detail?name={boq.name}"},
		],
	)
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
