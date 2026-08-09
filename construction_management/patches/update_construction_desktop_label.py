import json

import frappe


WORKSPACE_NAME = "Construction Management"
DESKTOP_LABEL = "Construction"


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
	if not frappe.db.exists("Desktop Icon", WORKSPACE_NAME):
		return
	frappe.db.set_value("Desktop Icon", WORKSPACE_NAME, "label", DESKTOP_LABEL, update_modified=False)
