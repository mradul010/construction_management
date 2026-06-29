import frappe
import os


def after_install():
	create_boq_client_script()
	ensure_ra_bill_items()


def after_migrate():
	create_boq_client_script()
	ensure_ra_bill_items()


def create_boq_client_script():
	script_path = os.path.join(
		os.path.dirname(__file__),
		"client_script",
		"boq_client_script.js"
	)
	with open(script_path, "r") as f:
		script_content = f.read()

	if frappe.db.exists("Client Script", "BOQ-client-script"):
		doc = frappe.get_doc("Client Script", "BOQ-client-script")
		doc.script = script_content
		doc.enabled = 1
		doc.save()
	else:
		doc = frappe.get_doc({
			"doctype": "Client Script",
			"name": "BOQ-client-script",
			"dt": "BOQ",
			"script": script_content,
			"enabled": 1,
			"view": "Form"
		})
		doc.insert()
	frappe.db.commit()
	print("BOQ client script created/updated successfully")


def get_or_create_ra_bill_receivable_account(company, currency):
	"""
	Return a receivable account whose currency matches the RA Bill invoice currency.
	ERPNext requires Sales Invoice debit_to currency to match document currency.
	"""
	import frappe

	if not company:
		return None

	company_currency = frappe.get_cached_value("Company", company, "default_currency")
	if not currency or currency == company_currency:
		return frappe.get_cached_value("Company", company, "default_receivable_account")

	account = frappe.db.get_value(
		"Account",
		{
			"company": company,
			"account_type": "Receivable",
			"account_currency": currency,
			"is_group": 0,
			"disabled": 0,
		},
		"name",
	)
	if account:
		return account

	account_name = f"RA Bill Receivable {currency}"
	account = frappe.db.get_value(
		"Account",
		{
			"company": company,
			"account_name": account_name,
			"is_group": 0,
		},
		"name",
	)
	if account:
		return account

	parent_account = frappe.db.get_value(
		"Account",
		{
			"company": company,
			"account_name": "Accounts Receivable",
			"root_type": "Asset",
			"is_group": 1,
		},
		"name",
	)
	if not parent_account:
		frappe.throw("Please create an Accounts Receivable group before creating RA Bill invoices.")

	account_doc = frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": account_name,
			"parent_account": parent_account,
			"company": company,
			"root_type": "Asset",
			"report_type": "Balance Sheet",
			"account_type": "Receivable",
			"account_currency": currency,
			"is_group": 0,
		}
	)
	account_doc.insert(ignore_permissions=True)
	frappe.db.commit()
	print(f"Created receivable account: {account_doc.name}")
	return account_doc.name


def ensure_ra_bill_items():
	"""
	Ensure the two service items used in RA Bill Sales Invoices exist.
	Safe to run multiple times - skips if already exists.
	"""
	import frappe

	company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
	income_account = frappe.db.get_value("Company", company, "default_income_account") if company else None

	items = [
		{
			"item_code": "RA Bill Services",
			"item_name": "RA Bill Services",
			"description": "Construction progress billing services",
			"item_group": "Services",
			"stock_uom": "Nos",
			"is_stock_item": 0,
			"is_purchase_item": 0,
			"is_sales_item": 1,
		},
		{
			"item_code": "Retention Deduction",
			"item_name": "Retention Deduction",
			"description": "Retention amount held per contract terms",
			"item_group": "Services",
			"stock_uom": "Nos",
			"is_stock_item": 0,
			"is_purchase_item": 0,
			"is_sales_item": 1,
		},
	]

	for item_data in items:
		if not frappe.db.exists("Item", item_data["item_code"]):
			doc = frappe.get_doc({"doctype": "Item", **item_data})
			if company:
				doc.append(
					"item_defaults",
					{
						"company": company,
						"income_account": income_account,
					},
				)
			doc.insert(ignore_permissions=True)
			print(f"Created item: {item_data['item_code']}")
		else:
			doc = frappe.get_doc("Item", item_data["item_code"])
			changed = False
			for field, value in item_data.items():
				if doc.get(field) != value:
					doc.set(field, value)
					changed = True

			if company:
				default_row = None
				for row in doc.item_defaults:
					if row.company == company:
						default_row = row
						break

				if not default_row:
					doc.append(
						"item_defaults",
						{
							"company": company,
							"income_account": income_account,
						},
					)
					changed = True
				elif income_account and default_row.income_account != income_account:
					default_row.income_account = income_account
					changed = True

			if changed:
				doc.save(ignore_permissions=True)
				print(f"Updated item: {item_data['item_code']}")
			else:
				print(f"Item already exists: {item_data['item_code']}")

	frappe.db.commit()
