import frappe
from frappe import _
from frappe.core.doctype.user.user import reset_password
from frappe.rate_limiter import rate_limit
from frappe.utils.password import get_password_reset_limit

from construction_management.portal_utils import (
	QATRA_CLIENT_PORTAL_ASSET_VERSION,
	QATRA_CLIENT_PORTAL_FALLBACK_LOGO,
	get_client_portal_access,
	get_client_portal_company_name,
	get_client_portal_logo,
)


no_cache = 1


def get_context(context):
	context.no_header = True
	context.no_breadcrumbs = True
	context.show_sidebar = False
	context.hide_login = True
	context.full_width = True
	context.title = "QATRA Client Portal"
	context.body_class = "qatra-client-portal"
	context.qatra_logo = get_client_portal_logo()
	context.qatra_fallback_logo = QATRA_CLIENT_PORTAL_FALLBACK_LOGO
	context.qatra_company_name = get_client_portal_company_name()
	context.qatra_client_portal_asset_version = QATRA_CLIENT_PORTAL_ASSET_VERSION
	context.portal_error = None
	context.is_logged_in = frappe.session.user != "Guest"

	if context.is_logged_in:
		access = get_client_portal_access()
		if access.allowed:
			frappe.local.flags.redirect_location = "/client-portal/dashboard"
			raise frappe.Redirect

		context.portal_error = access.reason


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=get_password_reset_limit, seconds=60 * 60)
def reset_client_portal_password(user=None):
	user = (user or "").strip()
	if not user:
		frappe.throw(_("Email Address is required."))

	if get_client_portal_access(user).allowed:
		reset_password(user=user)

	frappe.clear_messages()
	return {
		"message": _(
			"If this email is registered as a QATRA client portal user, password reset instructions have been sent."
		)
	}
