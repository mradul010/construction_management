import frappe


def execute():
	if not frappe.db.table_exists("Construction BOM Item"):
		return

	frappe.db.sql(
		"""
		update `tabConstruction BOM Item`
		set
			total_weight = round(coalesce(qty, 0) * coalesce(unit_weight, 0), 2),
			total_wt_mt = round((coalesce(qty, 0) * coalesce(unit_weight, 0)) / 1000, 4)
		"""
	)
