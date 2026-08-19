import frappe


def execute():
	if not frappe.db.exists("DocType", "Construction Company Settings"):
		return

	from construction_management.construction_management.setup import (
		ensure_construction_company_settings,
	)

	ensure_construction_company_settings()
