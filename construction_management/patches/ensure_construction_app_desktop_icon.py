import frappe


APP_NAME = "construction_management"
DESKTOP_LABEL = "Construction"
WORKSPACE_LINK_LABEL = "Construction Management"
WORKSPACE_NAME = "Construction Management"
APP_ROUTE = "/app/construction-management"
LOGO_URL = "/assets/construction_management/techsolvo_logo.jpeg"


def execute():
	ensure_workspace_link_icon()
	ensure_app_icon()
	frappe.clear_cache()


def ensure_workspace_link_icon():
	if not frappe.db.exists("Desktop Icon", WORKSPACE_NAME):
		return

	frappe.db.set_value(
		"Desktop Icon",
		WORKSPACE_NAME,
		{
			"label": WORKSPACE_LINK_LABEL,
			"app": APP_NAME,
			"icon_type": "Link",
			"link_type": "Workspace Sidebar",
			"link_to": WORKSPACE_NAME,
			"hidden": 1,
			"standard": 1,
		},
		update_modified=False,
	)


def ensure_app_icon():
	icon_name = (
		frappe.db.exists("Desktop Icon", {"label": DESKTOP_LABEL})
		or frappe.db.exists("Desktop Icon", {"icon_type": "App", "app": APP_NAME})
	)
	icon = frappe.get_doc("Desktop Icon", icon_name) if icon_name else frappe.new_doc("Desktop Icon")

	icon.update(
		{
			"label": DESKTOP_LABEL,
			"app": APP_NAME,
			"icon_type": "App",
			"link_type": "External",
			"link": APP_ROUTE,
			"logo_url": LOGO_URL,
			"hidden": 0,
			"standard": 1,
			"idx": 11,
		}
	)

	if icon.is_new():
		icon.name = DESKTOP_LABEL
		icon.insert(ignore_permissions=True)
	else:
		icon.save(ignore_permissions=True)

	hide_duplicate_app_icons(icon.name)


def hide_duplicate_app_icons(canonical_name):
	for row in frappe.get_all(
		"Desktop Icon",
		filters={"app": APP_NAME, "name": ["!=", canonical_name]},
		fields=["name"],
	):
		if row.name == WORKSPACE_NAME:
			continue
		frappe.db.set_value(
			"Desktop Icon",
			row.name,
			"hidden",
			1,
			update_modified=False,
		)
