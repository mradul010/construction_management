from frappe.utils import flt

from construction_management.portal_utils import get_customer_projects, setup_client_portal_context


no_cache = 1


def get_context(context):
	setup_client_portal_context(context, "projects")
	context.projects = get_customer_projects(context.customers)
	active_statuses = {"Open", "In Progress", "Active"}
	completed_statuses = {"Completed", "Closed"}
	on_hold_statuses = {"On Hold", "Hold"}
	total_progress = sum(flt(project.display_percent_complete) for project in context.projects)
	context.project_summary = {
		"total": len(context.projects),
		"active": len([project for project in context.projects if project.status in active_statuses]),
		"completed": len([project for project in context.projects if project.status in completed_statuses]),
		"on_hold": len([project for project in context.projects if project.status in on_hold_statuses]),
		"average_progress": flt(total_progress / len(context.projects), 1) if context.projects else 0,
	}
