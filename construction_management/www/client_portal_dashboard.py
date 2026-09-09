import frappe

from construction_management.portal_utils import get_client_dashboard_data, setup_client_portal_context


no_cache = 1


def get_context(context):
	setup_client_portal_context(context, "dashboard")
	context.dashboard = get_client_dashboard_data(
		project_name=frappe.form_dict.get("project"),
		customers=context.customers,
	)
