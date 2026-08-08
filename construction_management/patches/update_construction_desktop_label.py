import json

import frappe


WORKSPACE_NAME = "Construction Management"
DESKTOP_LABEL = "Construction"
APP_NAME = "construction_management"
CANONICAL_DESKTOP_ICON = "Construction"
LEGACY_DESKTOP_ICON = "Construction Management"
DESKTOP_LINK = "/app/construction-management"
LOGO_URL = "/assets/construction_management/techsolvo_logo.jpeg"


def execute():
	update_workspace_label()
	update_workspace_sidebar_label()
	update_desktop_icon_label()
	frappe.clear_cache()


def update_workspace_label():
	if not frappe.db.exists("Workspace", WORKSPACE_NAME):
		return

	values = {"title": DESKTOP_LABEL}
	meta = frappe.get_meta("Workspace")
	if meta.has_field("label"):
		values["label"] = DESKTOP_LABEL

	content = frappe.db.get_value("Workspace", WORKSPACE_NAME, "content")
	if content:
		try:
			content_rows = json.loads(content)
		except Exception:
			content_rows = []
		for row in content_rows:
			if row.get("id") == "cm_header":
				row.setdefault("data", {})["text"] = f'<span class="h4"><b>{DESKTOP_LABEL}</b></span>'
		values["content"] = json.dumps(content_rows, separators=(",", ":"))

	frappe.db.set_value("Workspace", WORKSPACE_NAME, values, update_modified=False)


def update_workspace_sidebar_label():
	if not frappe.db.exists("Workspace Sidebar", WORKSPACE_NAME):
		return
	frappe.db.set_value("Workspace Sidebar", WORKSPACE_NAME, "title", DESKTOP_LABEL, update_modified=False)


def update_desktop_icon_label():
	canonical_name = get_canonical_desktop_icon_name()
	if not canonical_name:
		canonical_name = create_or_rename_canonical_desktop_icon()

	ensure_canonical_desktop_icon(canonical_name)
	hide_legacy_desktop_icon(canonical_name)


def get_canonical_desktop_icon_name():
	label_owner = frappe.db.exists("Desktop Icon", {"label": DESKTOP_LABEL})
	if label_owner:
		return normalize_canonical_desktop_icon_name(label_owner)

	if frappe.db.exists("Desktop Icon", CANONICAL_DESKTOP_ICON):
		return CANONICAL_DESKTOP_ICON

	app_icon = frappe.db.exists("Desktop Icon", {"icon_type": "App", "app": APP_NAME})
	if app_icon:
		return normalize_canonical_desktop_icon_name(app_icon)

	return None


def normalize_canonical_desktop_icon_name(icon_name):
	if icon_name == CANONICAL_DESKTOP_ICON:
		return icon_name

	if not frappe.db.exists("Desktop Icon", CANONICAL_DESKTOP_ICON):
		frappe.rename_doc(
			"Desktop Icon",
			icon_name,
			CANONICAL_DESKTOP_ICON,
			force=True,
			ignore_permissions=True,
		)
		return CANONICAL_DESKTOP_ICON

	return icon_name


def create_or_rename_canonical_desktop_icon():
	if frappe.db.exists("Desktop Icon", LEGACY_DESKTOP_ICON):
		return normalize_canonical_desktop_icon_name(LEGACY_DESKTOP_ICON)

	doc = frappe.new_doc("Desktop Icon")
	doc.name = CANONICAL_DESKTOP_ICON
	doc.insert(ignore_permissions=True)
	return doc.name


def ensure_canonical_desktop_icon(icon_name):
	label_owner = frappe.db.exists("Desktop Icon", {"label": DESKTOP_LABEL})
	if label_owner and label_owner != icon_name:
		icon_name = label_owner

	icon = frappe.get_doc("Desktop Icon", icon_name)
	icon.update(
		{
			"label": DESKTOP_LABEL,
			"app": APP_NAME,
			"icon_type": "App",
			"link_type": "External",
			"link": DESKTOP_LINK,
			"link_to": None,
			"logo_url": LOGO_URL,
			"hidden": 0,
			"standard": 1,
			"parent_icon": "",
		}
	)
	icon.save(ignore_permissions=True)
	hide_duplicate_app_icons(icon.name)


def hide_duplicate_app_icons(canonical_name):
	for row in frappe.get_all(
		"Desktop Icon",
		filters={"app": APP_NAME, "name": ["!=", canonical_name]},
		fields=["name"],
	):
		if row.name == LEGACY_DESKTOP_ICON:
			continue
		frappe.db.set_value(
			"Desktop Icon",
			row.name,
			"hidden",
			1,
			update_modified=False,
		)


def hide_legacy_desktop_icon(canonical_name):
	if not frappe.db.exists("Desktop Icon", LEGACY_DESKTOP_ICON):
		return
	if LEGACY_DESKTOP_ICON == canonical_name:
		return

	frappe.db.set_value(
		"Desktop Icon",
		LEGACY_DESKTOP_ICON,
		{
			"label": WORKSPACE_NAME,
			"app": APP_NAME,
			"icon_type": "Link",
			"link_type": "Workspace Sidebar",
			"link": None,
			"link_to": WORKSPACE_NAME,
			"logo_url": LOGO_URL,
			"hidden": 1,
			"standard": 1,
			"parent_icon": "",
		},
		update_modified=False,
	)
