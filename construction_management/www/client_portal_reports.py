from construction_management.portal_utils import (
	get_client_portal_report_types,
	get_client_portal_reports,
	get_client_report_summary,
	get_dashboard_projects,
	get_request_filters,
	setup_client_portal_context,
)


no_cache = 1


def get_context(context):
	setup_client_portal_context(context, "reports")
	context.filters = get_request_filters("search", "project", "type", "date")
	context.projects = get_dashboard_projects(context.customers)
	context.report_types = get_client_portal_report_types()
	context.reports = get_client_portal_reports(context.customers, context.filters)
	context.report_summary = get_client_report_summary(context.reports, context.projects)
