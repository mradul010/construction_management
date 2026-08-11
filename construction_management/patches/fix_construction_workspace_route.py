import json

import frappe


APP_NAME = "construction_management"
APP_ICON_LABEL = "Construction"
APP_ROUTE = "/app/construction-management"
LOGO_URL = "/assets/construction_management/techsolvo_logo.jpeg"
WORKSPACE_NAME = "Construction Management"
WORKSPACE_TITLE = "Construction Management"


def execute():
	update_workspace()
	update_workspace_sidebar()
	ensure_app_icon_route()
	ensure_workspace_link_icon()
	frappe.cache.delete_key("desktop_icons")
	frappe.clear_cache()


def update_workspace():
	if not frappe.db.exists("Workspace", WORKSPACE_NAME):
		return

	values = {"title": WORKSPACE_TITLE}
	meta = frappe.get_meta("Workspace")
	if meta.has_field("label"):
		values["label"] = WORKSPACE_TITLE

	content = frappe.db.get_value("Workspace", WORKSPACE_NAME, "content")
	if content:
		try:
			content_rows = json.loads(content)
		except Exception:
			content_rows = []
		for row in content_rows:
			if row.get("id") == "cm_header":
				row.setdefault("data", {})["text"] = f'<span class="h4"><b>{WORKSPACE_TITLE}</b></span>'
		values["content"] = json.dumps(content_rows, separators=(",", ":"))

	frappe.db.set_value("Workspace", WORKSPACE_NAME, values, update_modified=False)


def update_workspace_sidebar():
	if not frappe.db.exists("Workspace Sidebar", WORKSPACE_NAME):
		return

	frappe.db.set_value(
		"Workspace Sidebar",
		WORKSPACE_NAME,
		"title",
		WORKSPACE_TITLE,
		update_modified=False,
	)


def ensure_app_icon_route():
	icon_name = (
		frappe.db.exists("Desktop Icon", {"icon_type": "App", "app": APP_NAME})
		or frappe.db.exists("Desktop Icon", APP_ICON_LABEL)
	)
	icon = frappe.get_doc("Desktop Icon", icon_name) if icon_name else frappe.new_doc("Desktop Icon")

	icon.update(
		{
			"label": APP_ICON_LABEL,
			"app": APP_NAME,
			"icon_type": "App",
			"link_type": "External",
			"link": APP_ROUTE,
			"logo_url": LOGO_URL,
			"hidden": 0,
			"standard": 1,
			"idx": 11,
			"parent_icon": "",
		}
	)

	if icon.is_new():
		icon.name = APP_ICON_LABEL
		icon.insert(ignore_permissions=True)
	else:
		icon.save(ignore_permissions=True)


def ensure_workspace_link_icon():
	if not frappe.db.exists("Desktop Icon", WORKSPACE_NAME):
		return

	frappe.db.set_value(
		"Desktop Icon",
		WORKSPACE_NAME,
		{
			"label": WORKSPACE_NAME,
			"app": APP_NAME,
			"icon_type": "Link",
			"link_type": "Workspace Sidebar",
			"link_to": WORKSPACE_NAME,
			"logo_url": LOGO_URL,
			"hidden": 1,
			"standard": 1,
			"parent_icon": "",
		},
		update_modified=False,
	)
