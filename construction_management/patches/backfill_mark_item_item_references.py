import frappe


def execute():
	backfill_child_table("Construction Activity Item")
	backfill_child_table("Construction BOM Item")


def backfill_child_table(doctype):
	if not frappe.db.table_exists(doctype):
		return
	if not frappe.db.has_column(doctype, "mark_item_item_code"):
		return

	frappe.db.sql(
		f"""
		UPDATE `tab{doctype}` child
		INNER JOIN `tabItem` item ON item.`name` = child.`mark_item`
		SET child.`mark_item_item_code` = item.`name`
		WHERE COALESCE(child.`mark_item_item_code`, '') = ''
		  AND COALESCE(child.`mark_item`, '') != ''
		"""
	)
