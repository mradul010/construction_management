import frappe


def execute():
	from construction_management.construction_management.setup import (
		ensure_sales_invoice_payment_breakdown_field,
	)

	ensure_sales_invoice_payment_breakdown_field()
	frappe.clear_cache(doctype="Sales Invoice")
