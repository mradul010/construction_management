import frappe

from construction_management.portal_utils import get_authorized_client_report, setup_client_portal_context


no_cache = 1


def get_context(context):
	setup_client_portal_context(context, "reports")
	report_data = get_authorized_client_report(
		frappe.form_dict.get("name"),
		context.customers,
		{"project": frappe.form_dict.get("project"), "date": frappe.form_dict.get("date")},
	)
	context.report = report_data.report
	context.project = report_data.project
	context.tasks = report_data.tasks
	context.photos = report_data.photos
	context.attachments = report_data.attachments
	context.page_kicker = "Project Report"
	context.page_title = context.report.display_title
	context.page_subtitle = f"{context.report.name} - {context.report.display_status}"
	context.title = context.report.display_title
