import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def configure_report():
	"""Rebind the existing report identity after all standard reports are synced."""
	create_custom_fields({"Account": [{
		"fieldname": "custom_profitability_classification",
		"label": "Project Profitability Classification",
		"fieldtype": "Select",
		"options": "\nDirect\nIndirect",
		"insert_after": "account_type",
		"module": "Construction Management",
		"description": "Inherited by descendants. Blank inherits; Cost of Goods Sold is Direct; other expenses remain unclassified.",
	}]})
	if frappe.db.exists("Report", "Project Profitability"):
		# Keep the existing report, its roles, and saved links.
		frappe.db.set_value("Report", "Project Profitability", {
			"module": "Construction Management", "ref_doctype": "GL Entry",
			"is_standard": "Yes", "report_type": "Script Report", "add_total_row": 0,
		})
		frappe.clear_cache(doctype="Report")
