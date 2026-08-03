import frappe


APP_NAME = "construction_management"
WORKSPACE_NAME = "Construction Management"
WORKSPACE_LINK_LABEL = "Construction Management"


def execute():
	if not frappe.db.exists("Desktop Icon", WORKSPACE_NAME):
		return

	frappe.db.set_value(
		"Desktop Icon",
		WORKSPACE_NAME,
		{
			"label": WORKSPACE_LINK_LABEL,
			"app": APP_NAME,
			"hidden": 1,
		},
		update_modified=False,
	)
