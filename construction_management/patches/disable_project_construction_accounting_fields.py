import frappe


PROJECT_CONSTRUCTION_ACCOUNTING_FIELDS = (
	"construction_accounting_settings_section",
	"default_ra_bill_receivable_account",
	"default_ra_bill_income_account",
	"default_retention_receivable_account",
	"default_customer_advance_account",
	"default_advance_recovery_account",
	"default_construction_receipt_account",
	"subcontract_accounting_column",
	"default_subcontractor_payable_account",
	"default_subcontractor_retention_payable_account",
	"default_subcontractor_advance_account",
	"default_subcontract_expense_account",
)


def execute():
	for fieldname in PROJECT_CONSTRUCTION_ACCOUNTING_FIELDS:
		custom_field = f"Project-{fieldname}"
		if not frappe.db.exists("Custom Field", custom_field):
			continue

		frappe.db.set_value(
			"Custom Field",
			custom_field,
			{
				"hidden": 1,
				"read_only": 1,
			},
			update_modified=False,
		)

	frappe.clear_cache(doctype="Project")
