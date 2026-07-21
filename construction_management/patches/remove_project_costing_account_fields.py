import frappe


PROJECT_COSTING_ACCOUNT_FIELDS = (
	"project_costing_accounts_section",
	"default_material_cost_account",
	"default_labour_cost_account",
	"default_equipment_cost_account",
	"default_subcontract_cost_account",
	"default_site_overhead_account",
	"default_project_wip_account",
	"project_accounting_settings_column",
)


def execute():
	for fieldname in PROJECT_COSTING_ACCOUNT_FIELDS:
		custom_field = f"Company-{fieldname}"
		if frappe.db.exists("Custom Field", custom_field):
			frappe.delete_doc("Custom Field", custom_field, ignore_permissions=True)

	frappe.clear_cache(doctype="Company")
