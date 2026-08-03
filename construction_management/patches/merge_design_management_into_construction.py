import frappe


OLD_MODULE = "Design Management"
NEW_MODULE = "Construction Management"
LEGACY_WORKSPACE = "Design Management"


def execute():
	update_module_references()
	hide_legacy_workspace()
	remove_legacy_module_def()
	frappe.clear_cache()


def update_module_references():
	for doctype in ("DocType", "Report", "Custom Field", "Workspace"):
		if not frappe.db.table_exists(doctype):
			continue
		frappe.db.sql(
			f"""
			UPDATE `tab{doctype}`
			SET `module` = %s
			WHERE `module` = %s
			""",
			(NEW_MODULE, OLD_MODULE),
		)


def hide_legacy_workspace():
	if not frappe.db.exists("Workspace", LEGACY_WORKSPACE):
		return

	values = {"is_hidden": 1, "public": 0, "parent_page": "Construction Management"}
	meta = frappe.get_meta("Workspace")
	if meta.has_field("label"):
		values["label"] = LEGACY_WORKSPACE

	frappe.db.set_value("Workspace", LEGACY_WORKSPACE, values, update_modified=False)


def remove_legacy_module_def():
	if not frappe.db.exists("Module Def", OLD_MODULE):
		return

	linked_doctypes = [
		("DocType", "module"),
		("Report", "module"),
		("Custom Field", "module"),
		("Workspace", "module"),
	]
	for doctype, fieldname in linked_doctypes:
		if frappe.db.exists(doctype, {fieldname: OLD_MODULE}):
			return

	frappe.delete_doc("Module Def", OLD_MODULE, ignore_permissions=True, force=True)
