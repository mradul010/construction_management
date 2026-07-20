import frappe
from frappe import _


CONSTRUCTION_ACCOUNT_FIELDS = {
	"ra_bill_receivable": {
		"company_field": "default_ra_bill_receivable_account",
		"fallback_company_field": "default_receivable_account",
		"account_type": "Receivable",
	},
	"ra_bill_income": {
		"company_field": "default_ra_bill_income_account",
		"fallback_company_field": "default_income_account",
		"root_type": "Income",
	},
	"retention_receivable": {
		"company_field": "default_retention_receivable_account",
		"fallback_creator": "retention_receivable",
		"account_type": "Receivable",
	},
	"customer_advance": {
		"company_field": "default_customer_advance_account",
		"fallback_company_field": "default_receivable_account",
		"account_type": "Receivable",
	},
	"advance_recovery": {
		"company_field": "default_advance_recovery_account",
		"fallback_company_field": "default_receivable_account",
		"account_type": "Receivable",
	},
	"construction_receipt": {
		"company_field": "default_construction_receipt_account",
		"fallback_getter": "default_company_bank_account",
		"root_type": "Asset",
	},
	"subcontractor_payable": {
		"company_field": "default_subcontractor_payable_account",
		"fallback_company_field": "default_payable_account",
		"account_type": "Payable",
	},
	"subcontractor_retention_payable": {
		"company_field": "default_subcontractor_retention_payable_account",
		"fallback_company_field": "default_payable_account",
		"account_type": "Payable",
	},
	"subcontractor_advance": {
		"company_field": "default_subcontractor_advance_account",
		"fallback_company_field": "default_payable_account",
		"account_type": "Payable",
	},
	"subcontract_expense": {
		"company_field": "default_subcontract_expense_account",
		"fallback_company_field": "default_expense_account",
		"root_type": "Expense",
	},
	"material_cost": {
		"company_field": "default_material_cost_account",
		"fallback_company_field": "default_expense_account",
		"root_type": "Expense",
	},
	"labour_cost": {
		"company_field": "default_labour_cost_account",
		"fallback_company_field": "default_expense_account",
		"root_type": "Expense",
	},
	"equipment_cost": {
		"company_field": "default_equipment_cost_account",
		"fallback_company_field": "default_expense_account",
		"root_type": "Expense",
	},
	"subcontract_cost": {
		"company_field": "default_subcontract_cost_account",
		"fallback_company_field": "default_expense_account",
		"root_type": "Expense",
	},
	"site_overhead": {
		"company_field": "default_site_overhead_account",
		"fallback_company_field": "default_expense_account",
		"root_type": "Expense",
	},
	"project_wip": {
		"company_field": "default_project_wip_account",
		"root_type": "Asset",
	},
}


RETENTION_ACCOUNT_NAME = "Retention Receivable"
RETENTION_PARENT_ACCOUNT = "Current Assets - QBC"
RETENTION_PARENT_ACCOUNT_FALLBACK = "Current Assets"


@frappe.whitelist()
def get_construction_account(company, account_type, project=None, transaction=None):
	"""
	Return a construction account using transaction, project, company settings,
	then ERPNext company defaults.
	"""
	if not company:
		return None

	account_type = (account_type or "").strip()
	config = CONSTRUCTION_ACCOUNT_FIELDS.get(account_type)
	if not config:
		frappe.throw(_("Unknown construction account type {0}.").format(account_type))

	for account in _candidate_accounts(company, account_type, config, project, transaction):
		if _is_valid_account(account, company, config):
			return account

	if config.get("fallback_creator") == "retention_receivable":
		return get_or_create_retention_receivable_account(company)
	if config.get("fallback_getter") == "default_company_bank_account":
		return get_default_company_bank_account(company)

	return None


def apply_construction_accounts_to_sales_order(sales_order, method=None):
	if not sales_order or not sales_order.get("company"):
		return

	project = sales_order.get("project")
	income_account = get_construction_account(
		sales_order.company,
		"ra_bill_income",
		project=project,
		transaction=sales_order,
	)
	cost_center = _get_construction_cost_center(project, sales_order.company)

	for row in sales_order.get("items") or []:
		_set_if_empty(row, "income_account", income_account)
		_set_if_empty(row, "cost_center", cost_center)


def apply_construction_accounts_to_sales_invoice(invoice, method=None):
	if not invoice or not invoice.get("company"):
		return

	project = invoice.get("project")
	ra_bill = invoice.get("ra_bill") if invoice.meta.has_field("ra_bill") else None
	if ra_bill:
		ra_bill_values = frappe.db.get_value("RA Bill", ra_bill, ["project", "currency"], as_dict=True)
		if ra_bill_values:
			project = project or ra_bill_values.project

	is_construction_invoice = bool(
		ra_bill
		or (invoice.meta.has_field("retention_record") and invoice.get("retention_record"))
		or _has_construction_sales_order(invoice)
	)
	if not is_construction_invoice:
		return

	currency = invoice.get("currency") or frappe.get_cached_value("Company", invoice.company, "default_currency")
	receivable_account = get_or_create_ra_bill_receivable_account(invoice.company, currency)
	income_account = get_construction_account(
		invoice.company,
		"ra_bill_income",
		project=project,
		transaction=invoice,
	)
	cost_center = _get_construction_cost_center(project, invoice.company)

	_set_if_empty(invoice, "debit_to", receivable_account)
	if invoice.get("debit_to") != receivable_account:
		invoice.debit_to = receivable_account
	if invoice.get("debit_to"):
		invoice.party_account_currency = (
			frappe.db.get_value("Account", invoice.debit_to, "account_currency")
			or currency
		)

	for row in invoice.get("items") or []:
		_set_if_empty(row, "income_account", income_account)
		_set_if_empty(row, "cost_center", cost_center)


def apply_construction_accounts_to_payment_entry(payment_entry, method=None):
	if not payment_entry or not payment_entry.get("company"):
		return

	context = _get_payment_entry_construction_context(payment_entry)
	if not context:
		return

	paid_from = None
	paid_to = None
	if payment_entry.payment_type == "Receive":
		if context.account_context == "retention":
			paid_from = get_construction_account(
				payment_entry.company,
				"retention_receivable",
				project=context.project,
				transaction=payment_entry,
			)
		elif context.account_context == "advance":
			paid_from = get_construction_account(
				payment_entry.company,
				"customer_advance",
				project=context.project,
				transaction=payment_entry,
			)
		elif context.account_context == "ra_bill":
			paid_from = get_or_create_ra_bill_receivable_account(
				payment_entry.company,
				payment_entry.get("paid_from_account_currency")
				or frappe.get_cached_value("Company", payment_entry.company, "default_currency"),
			)

		paid_to = get_construction_account(
			payment_entry.company,
			"construction_receipt",
			project=context.project,
			transaction=payment_entry,
		)
	elif payment_entry.payment_type == "Pay" and context.account_context == "subcontract":
		paid_to = get_construction_account(
			payment_entry.company,
			"subcontractor_payable",
			project=context.project,
			transaction=payment_entry,
		)

	if paid_from:
		payment_entry.paid_from = paid_from
		payment_entry.paid_from_account_currency = frappe.get_cached_value(
			"Account", paid_from, "account_currency"
		)
	if paid_to:
		payment_entry.paid_to = paid_to
		payment_entry.paid_to_account_currency = frappe.get_cached_value(
			"Account", paid_to, "account_currency"
		)
	if context.project and payment_entry.meta.has_field("project") and not payment_entry.get("project"):
		payment_entry.project = context.project


def get_default_company_bank_account(company):
	if not company:
		return None

	try:
		from erpnext.accounts.doctype.bank_account.bank_account import get_default_company_bank_account

		bank_account_name = get_default_company_bank_account(company)
		if isinstance(bank_account_name, dict):
			bank_account_name = bank_account_name.get("name")
		if bank_account_name:
			account = frappe.db.get_value("Bank Account", bank_account_name, "account")
			if account:
				return account
	except Exception:
		pass

	return frappe.get_cached_value("Company", company, "default_bank_account")


def get_or_create_ra_bill_receivable_account(company, currency=None):
	if not company:
		return None

	company_currency = frappe.get_cached_value("Company", company, "default_currency")
	if not currency or currency == company_currency:
		return get_construction_account(company, "ra_bill_receivable")

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
		frappe.throw(_("Please create an Accounts Receivable group before creating RA Bill invoices."))

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
	return account_doc.name


def get_or_create_retention_receivable_account(company=None):
	if company:
		account = frappe.db.get_value(
			"Account",
			{
				"account_name": RETENTION_ACCOUNT_NAME,
				"company": company,
				"is_group": 0,
			},
			"name",
		)
		if account:
			return account

	parent_account = _get_retention_parent_account(company)
	parent_company = frappe.db.get_value("Account", parent_account, "company")

	company = company or parent_company
	if company != parent_company:
		frappe.throw(
			_("Parent Account {0} belongs to company {1}, not {2}.").format(
				parent_account,
				parent_company,
				company,
			)
		)

	account = frappe.db.get_value(
		"Account",
		{
			"account_name": RETENTION_ACCOUNT_NAME,
			"company": company,
			"is_group": 0,
		},
		"name",
	)
	if account:
		return account

	account_doc = frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": RETENTION_ACCOUNT_NAME,
			"parent_account": parent_account,
			"account_type": "Receivable",
			"is_group": 0,
			"company": company,
		}
	)
	account_doc.insert(ignore_permissions=True)
	return account_doc.name


def ensure_retention_receivable_account():
	if _get_retention_parent_account():
		return get_or_create_retention_receivable_account()
	return None


def _candidate_accounts(company, account_type, config, project=None, transaction=None):
	for doc in (_as_doc(transaction), _as_doc(project, "Project")):
		account = _get_document_account(doc, account_type, config.get("company_field"))
		if account:
			yield account

	company_field = config.get("company_field")
	if company_field and frappe.get_meta("Company").has_field(company_field):
		yield frappe.db.get_value("Company", company, company_field)

	fallback_company_field = config.get("fallback_company_field")
	if fallback_company_field and frappe.get_meta("Company").has_field(fallback_company_field):
		yield frappe.get_cached_value("Company", company, fallback_company_field)


def _get_document_account(doc, account_type, company_field):
	if not doc:
		return None

	for fieldname in (company_field, account_type, f"{account_type}_account"):
		if fieldname and doc.meta.has_field(fieldname) and doc.get(fieldname):
			return doc.get(fieldname)

	return None


def _get_payment_entry_construction_context(payment_entry):
	record_name = None
	for fieldname in ("custom_retention_record", "retention_record"):
		if payment_entry.meta.has_field(fieldname) and payment_entry.get(fieldname):
			record_name = payment_entry.get(fieldname)
			break
	if record_name:
		project = frappe.db.get_value("Retention Record", record_name, "project")
		return frappe._dict({"account_context": "retention", "project": project})

	for reference in payment_entry.get("references") or []:
		if reference.reference_doctype == "Sales Order" and reference.reference_name:
			project = frappe.db.get_value("Sales Order", reference.reference_name, "project")
			return frappe._dict({"account_context": "advance", "project": project})
		if reference.reference_doctype == "Sales Invoice" and reference.reference_name:
			fields = ["project"]
			if frappe.get_meta("Sales Invoice").has_field("ra_bill"):
				fields.append("ra_bill")
			invoice = frappe.db.get_value("Sales Invoice", reference.reference_name, fields, as_dict=True)
			if invoice and invoice.get("ra_bill"):
				return frappe._dict({"account_context": "ra_bill", "project": invoice.get("project")})
		if reference.reference_doctype == "Purchase Invoice" and reference.reference_name:
			project = frappe.db.get_value("Purchase Invoice", reference.reference_name, "project")
			if project:
				return frappe._dict({"account_context": "subcontract", "project": project})

	return None


def _has_construction_sales_order(invoice):
	if invoice.meta.has_field("sales_order") and invoice.get("sales_order"):
		return True
	for row in invoice.get("items") or []:
		if row.get("sales_order"):
			return True
	return False


def _get_construction_cost_center(project, company):
	if not project and not company:
		return None

	try:
		from construction_management.construction_management.accounting_dimensions import (
			get_ra_bill_project_cost_center,
		)

		return get_ra_bill_project_cost_center(project=project, company=company)
	except Exception:
		return None


def _set_if_empty(doc, fieldname, value):
	if doc.meta.has_field(fieldname) and value and not doc.get(fieldname):
		doc.set(fieldname, value)


def _as_doc(value, default_doctype=None):
	if not value:
		return None
	if hasattr(value, "doctype") and hasattr(value, "meta"):
		return value
	if isinstance(value, str) and default_doctype and frappe.db.exists(default_doctype, value):
		return frappe.get_cached_doc(default_doctype, value)
	return None


def _is_valid_account(account, company, config):
	if not account:
		return False

	filters = {"name": account, "company": company, "is_group": 0, "disabled": 0}
	if config.get("account_type"):
		filters["account_type"] = config["account_type"]
	if config.get("root_type"):
		filters["root_type"] = config["root_type"]

	return bool(frappe.db.exists("Account", filters))


def _get_retention_parent_account(company=None):
	if frappe.db.exists("Account", RETENTION_PARENT_ACCOUNT):
		return RETENTION_PARENT_ACCOUNT

	filters = {
		"account_name": RETENTION_PARENT_ACCOUNT_FALLBACK,
		"is_group": 1,
		"root_type": "Asset",
	}
	if company:
		filters["company"] = company

	parent_account = frappe.db.get_value("Account", filters, "name")
	if parent_account:
		return parent_account

	frappe.throw(_("Parent Account {0} does not exist.").format(RETENTION_PARENT_ACCOUNT))
