import frappe
from frappe import _

from construction_management.portal_utils import get_authorized_client_approval, setup_client_portal_context


no_cache = 1


def get_context(context):
	setup_client_portal_context(context, "approvals")
	approval_name = frappe.form_dict.get("name") or get_approval_name_from_path()
	if not approval_name:
		frappe.throw(_("Approval request not specified."), frappe.DoesNotExistError)
	context.approval = get_authorized_client_approval(approval_name, context.customers)
	context.page_kicker = context.approval.approval_type or "Approval Request"
	context.page_title = context.approval.subject
	context.page_subtitle = "Review approval request details and respond."
	context.title = context.approval.subject


def get_approval_name_from_path():
	path = getattr(frappe.local, "path", "") or getattr(getattr(frappe.local, "request", None), "path", "") or ""
	path = path.strip("/")
	parts = path.split("/")
	if len(parts) >= 3 and parts[-2] == "approval":
		return parts[-1]
	return None
