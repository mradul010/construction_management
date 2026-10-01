import frappe

from construction_management.portal_utils import (
	get_authorized_customer_project,
	get_customer_projects,
	get_project_documents,
	setup_client_portal_context,
)


no_cache = 1


def get_context(context):
	setup_client_portal_context(context, "documents")
	context.projects = get_customer_projects(context.customers)
	requested_project = frappe.form_dict.get("project")
	context.selected_project = (
		get_authorized_customer_project(requested_project, context.customers) if requested_project else None
	)
	context.documents = get_project_documents(
		context.customers,
		project_name=context.selected_project.name if context.selected_project else None,
	)
	context.document_count = len(context.documents)
	context.page_kicker = "Shared Files"
	context.page_title = "Documents"
	context.page_subtitle = "Project documents shared with you"
	context.title = "Documents"
