import frappe

from construction_management.portal_utils import (
	log_portal_access,
	require_portal_customer,
	setup_portal_context,
	validate_dpr_customer,
)


no_cache = 1


def get_context(context):
	customer = require_portal_customer()
	log_portal_access(customer)
	name = frappe.form_dict.get("name")
	validate_dpr_customer(name, customer)

	dpr = frappe.get_doc("Daily Progress Report", name)
	setup_portal_context(
		context,
		dpr.name,
		description="Daily progress report details, completed tasks, photos and attachments.",
		parents=[
			{"name": "Construction Portal", "route": "/construction-portal"},
			{"name": "Daily Progress Reports", "route": "/dprs"},
			{"name": dpr.name, "route": f"/dpr-detail?name={dpr.name}"},
		],
	)
	context.customer = customer
	context.dpr = dpr
	context.tasks = dpr.get("tasks_completed") or []
	context.photos = sorted(
		dpr.get("photos") or [],
		key=lambda row: (row.sequence or 0, row.idx or 0),
	)
	context.attachments = get_attachments(dpr.name)


def get_attachments(dpr_name):
	return frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "Daily Progress Report",
			"attached_to_name": dpr_name,
		},
		fields=["file_name", "file_url", "is_private"],
		order_by="creation asc",
		ignore_permissions=True,
	)
