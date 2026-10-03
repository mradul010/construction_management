import frappe

from construction_management.portal_utils import (
	get_client_approval_types,
	get_client_portal_approvals,
	get_authorized_customer_project,
	get_customer_projects,
	normalize_client_approval_status_filter,
	setup_client_portal_context,
)


no_cache = 1


def get_context(context):
	setup_client_portal_context(context, "approvals")
	context.projects = get_customer_projects(context.customers)
	requested_project = frappe.form_dict.get("project")
	context.selected_project = (
		get_authorized_customer_project(requested_project, context.customers) if requested_project else None
	)
	context.selected_status = normalize_client_approval_status_filter(frappe.form_dict.get("status"))
	context.selected_type = frappe.form_dict.get("type") or ""
	context.approval_types = get_client_approval_types(
		context.customers,
		project_name=context.selected_project.name if context.selected_project else None,
	)
	context.approvals = get_client_portal_approvals(
		context.customers,
		project_name=context.selected_project.name if context.selected_project else None,
		status=context.selected_status,
		approval_type=context.selected_type or None,
	)
	context.pending_count = len(get_client_portal_approvals(context.customers, project_name=context.selected_project.name if context.selected_project else None, status="Pending", approval_type=context.selected_type or None))
	context.approved_count = len(get_client_portal_approvals(context.customers, project_name=context.selected_project.name if context.selected_project else None, status="Approved", approval_type=context.selected_type or None))
	context.rejected_count = len(get_client_portal_approvals(context.customers, project_name=context.selected_project.name if context.selected_project else None, status="Rejected", approval_type=context.selected_type or None))
	context.total_count = len(get_client_portal_approvals(context.customers, project_name=context.selected_project.name if context.selected_project else None, status="All", approval_type=context.selected_type or None))
	context.page_kicker = "Pending Reviews"
	context.page_title = "Approvals"
	context.page_subtitle = "Review requests that require your approval."
	context.title = "Approvals"
