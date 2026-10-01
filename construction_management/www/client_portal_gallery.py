import frappe

from construction_management.portal_utils import (
	get_authorized_customer_project,
	get_customer_projects,
	get_project_gallery,
	setup_client_portal_context,
)


no_cache = 1


def get_context(context):
	setup_client_portal_context(context, "gallery")
	context.projects = get_customer_projects(context.customers)
	requested_project = frappe.form_dict.get("project")
	context.selected_project = (
		get_authorized_customer_project(requested_project, context.customers) if requested_project else None
	)
	context.gallery_items = get_project_gallery(
		context.customers,
		project_name=context.selected_project.name if context.selected_project else None,
	)
	context.gallery_count = len(context.gallery_items)
	context.page_kicker = "Progress Photos"
	context.page_title = "Gallery"
	context.page_subtitle = "Published project images and progress photos"
	context.title = "Gallery"
