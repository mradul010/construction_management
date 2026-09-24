import frappe


def execute():
	backfill_activity_item_code()
	backfill_construction_bom_item_code()


def backfill_activity_item_code():
	if not frappe.db.table_exists("Construction Activity Item"):
		return

	if not _has_column("Construction Activity Item", "item_code"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabConstruction Activity Item` activity
		INNER JOIN `tabItem` item ON item.`name` = activity.`mark_item`
		SET activity.`item_code` = item.`name`
		WHERE COALESCE(activity.`item_code`, '') = ''
		  AND COALESCE(activity.`mark_item`, '') != ''
		"""
	)
	frappe.db.sql(
		"""
		UPDATE `tabConstruction Activity Item` activity
		INNER JOIN `tabItem` item ON item.`name` = activity.`mark_no`
		SET activity.`item_code` = item.`name`
		WHERE COALESCE(activity.`item_code`, '') = ''
		  AND COALESCE(activity.`mark_no`, '') != ''
		"""
	)


def backfill_construction_bom_item_code():
	if not frappe.db.table_exists("Construction BOM Item"):
		return

	if not _has_column("Construction BOM Item", "item_code"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabConstruction BOM Item` bom_item
		INNER JOIN `tabItem` item ON item.`name` = bom_item.`mark_no`
		SET bom_item.`item_code` = item.`name`
		WHERE COALESCE(bom_item.`item_code`, '') = ''
		  AND COALESCE(bom_item.`mark_no`, '') != ''
		"""
	)


def _has_column(doctype, fieldname):
	return frappe.db.has_column(doctype, fieldname)
