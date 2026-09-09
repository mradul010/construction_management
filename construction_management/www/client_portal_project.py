import frappe

from construction_management.portal_utils import (
	get_authorized_customer_project,
	get_dashboard_recent_activity,
	get_client_portal_project_counts,
	get_next_project_milestone,
	get_project_current_stage,
	get_project_financial_summary,
	get_project_journey,
	setup_client_portal_context,
)


no_cache = 1


def get_context(context):
	setup_client_portal_context(context, "projects")
	project_name = frappe.form_dict.get("name")
	context.project = get_authorized_customer_project(project_name, context.customers)
	context.project_counts = get_client_portal_project_counts(context.project.name, context.customers)
	context.financial_summary = get_project_financial_summary(
		context.project.name,
		context.customers,
		project=context.project,
	)
	context.current_stage = get_project_current_stage(context.project)
	context.journey = get_project_journey(context.project)
	context.next_milestone = get_next_project_milestone(context.project.name, context.customers)
	context.recent_activity = get_dashboard_recent_activity(
		context.project.name,
		context.customers,
		context.financial_summary,
		limit=6,
	)
	context.page_kicker = "Project Details"
	context.page_title = context.project.display_name
	context.page_subtitle = f"{context.project.name} - {context.project.display_status}"
	context.title = context.project.display_name
