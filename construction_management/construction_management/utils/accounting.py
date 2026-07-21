import frappe
from frappe import _


CONSTRUCTION_ACCOUNT_FIELDS = {
	"ra_bill_receivable": {
		"company_field": "default_ra_bill_receivable_account",
		"account_type": "Receivable",
	},
	"ra_bill_income": {
		"company_field": "default_ra_bill_income_account",
		"root_type": "Income",
	},
	"retention_receivable": {
		"company_field": "default_retention_receivable_account",
		"account_type": "Receivable",
	},
	"customer_advance": {
		"company_field": "default_customer_advance_account",
		"account_type": "Receivable",
	},
	"advance_recovery": {
		"company_field": "default_advance_recovery_account",
		"account_type": "Receivable",
	},
	"construction_receipt": {
		"company_field": "default_construction_receipt_account",
		"root_type": "Asset",
	},
	"subcontractor_payable": {
		"company_field": "default_subcontractor_payable_account",
		"account_type": "Payable",
	},
	"subcontractor_retention_payable": {
		"company_field": "default_subcontractor_retention_payable_account",
		"account_type": "Payable",
	},
	"subcontractor_advance": {
		"company_field": "default_subcontractor_advance_account",
		"account_type": "Payable",
	},
	"subcontract_expense": {
		"company_field": "default_subcontract_expense_account",
		"root_type": "Expense",
	},
}


PARTY_TYPE_BY_ACCOUNT_TYPE = {
	"Receivable": "Customer",
	"Payable": "Supplier",
}

RETENTION_ACCOUNT_NAME = "Retention Receivable"
RETENTION_PARENT_ACCOUNT = "Current Assets - QBC"
RETENTION_PARENT_ACCOUNT_FALLBACK = "Current Assets"


@frappe.whitelist()
def get_construction_account(company, account_type, project=None, transaction=None):
	"""
	Return the construction account configured on Company.
	"""
	return get_default_construction_account(company, account_type)


def get_construction_company_settings(company):
	if not company:
		frappe.throw(_("Company is required to fetch Construction Accounting Settings."))

	if not frappe.db.exists("Company", company):
		frappe.throw(_("Company {0} does not exist.").format(company))

	return frappe.get_cached_doc("Company", company)


def get_default_construction_account(company, account_key):
	if not company:
		frappe.throw(_("Company is required to fetch construction accounts."))

	account_type = (account_key or "").strip()
	config = CONSTRUCTION_ACCOUNT_FIELDS.get(account_type)
	if not config:
		frappe.throw(_("Unknown construction account type {0}.").format(account_type))

	company_doc = get_construction_company_settings(company)
	company_field = config.get("company_field")
	if not company_doc.meta.has_field(company_field):
		frappe.throw(
			_("Company is missing Construction Accounting Settings field {0}.").format(
				frappe.bold(company_field)
			)
		)

	account = company_doc.get(company_field)
	if not account:
		frappe.throw(
			_("Please set {0} in Company {1} Construction Accounting Settings.").format(
				frappe.bold(company_doc.meta.get_label(company_field) or company_field),
				frappe.bold(company),
			)
		)

	if not _is_valid_account(account, company, config):
		frappe.throw(
			_("{0} configured in Company {1} is not a valid construction account for {2}.").format(
				frappe.bold(account),
				frappe.bold(company),
				frappe.bold(account_type),
			)
		)

	return account


def get_project_cost_center(project, company):
	return _get_construction_cost_center(project, company)


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


def apply_construction_accounts_to_purchase_invoice(invoice, method=None):
	if not invoice or not invoice.get("company") or not _is_construction_purchase_invoice(invoice):
		return

	project = invoice.get("project")
	payable_account = get_construction_account(
		invoice.company,
		"subcontractor_payable",
		project=project,
		transaction=invoice,
	)
	expense_account = get_construction_account(
		invoice.company,
		"subcontract_expense",
		project=project,
		transaction=invoice,
	)
	cost_center = _get_construction_cost_center(project, invoice.company)

	if invoice.meta.has_field("credit_to"):
		invoice.credit_to = payable_account
		invoice.party_account_currency = frappe.get_cached_value(
			"Account", payable_account, "account_currency"
		)

	for row in invoice.get("items") or []:
		_set_if_empty(row, "expense_account", expense_account)
		_set_if_empty(row, "cost_center", cost_center)
		if row.meta.has_field("project") and project and not row.get("project"):
			row.project = project


def apply_construction_accounts_to_payment_entry(payment_entry, method=None):
	if not payment_entry or not payment_entry.get("company"):
		return

	context = _get_payment_entry_construction_context(payment_entry)
	if not context:
		apply_party_to_payment_entry(payment_entry)
		apply_party_to_payment_entry_references(payment_entry)
		return

	paid_from = None
	paid_to = None
	if payment_entry.payment_type == "Receive":
		if not payment_entry.get("paid_from") and context.account_context == "retention":
			paid_from = get_construction_account(
				payment_entry.company,
				"retention_receivable",
				project=context.project,
				transaction=payment_entry,
			)
		elif not payment_entry.get("paid_from") and context.account_context == "advance":
			paid_from = get_construction_account(
				payment_entry.company,
				"customer_advance",
				project=context.project,
				transaction=payment_entry,
			)
		elif not payment_entry.get("paid_from") and context.account_context == "ra_bill":
			paid_from = get_or_create_ra_bill_receivable_account(
				payment_entry.company,
				payment_entry.get("paid_from_account_currency")
				or frappe.get_cached_value("Company", payment_entry.company, "default_currency"),
			)

		if not payment_entry.get("paid_to"):
			paid_to = get_construction_account(
				payment_entry.company,
				"construction_receipt",
				project=context.project,
				transaction=payment_entry,
			)
	elif (
		payment_entry.payment_type == "Pay"
		and context.account_context == "subcontract"
		and not payment_entry.get("paid_to")
	):
		paid_to = get_construction_account(
			payment_entry.company,
			"subcontractor_payable",
			project=context.project,
			transaction=payment_entry,
		)

	_set_payment_entry_account_if_empty(
		payment_entry,
		"paid_from",
		"paid_from_account_currency",
		paid_from,
	)
	_set_payment_entry_account_if_empty(
		payment_entry,
		"paid_to",
		"paid_to_account_currency",
		paid_to,
	)
	if context.project and payment_entry.meta.has_field("project") and not payment_entry.get("project"):
		payment_entry.project = context.project

	apply_party_to_payment_entry(payment_entry, context=context)
	apply_party_to_payment_entry_references(payment_entry, context=context)


def apply_party_to_payment_entry(payment_entry, context=None):
	if not payment_entry:
		return

	context = context or _get_payment_entry_construction_context(payment_entry)
	required_party_type = _get_required_party_type_for_payment_entry(payment_entry)
	if not required_party_type:
		return

	party_context = _get_payment_entry_party_context(
		payment_entry,
		context=context,
		required_party_type=required_party_type,
	)
	if not party_context:
		frappe.throw(
			_("{0} is required against {1} account {2}.").format(
				required_party_type,
				_get_account_type_label(required_party_type),
				frappe.bold(_get_first_party_account(payment_entry, required_party_type) or ""),
			)
		)

	if not payment_entry.get("party_type"):
		payment_entry.party_type = party_context.party_type
	if not payment_entry.get("party"):
		payment_entry.party = party_context.party

	_validate_payment_entry_party(payment_entry, party_context)


def apply_party_to_payment_entry_references(payment_entry, context=None):
	if not payment_entry:
		return

	context = context or _get_payment_entry_construction_context(payment_entry)
	cost_center = _get_construction_cost_center(
		context.project if context else payment_entry.get("project"),
		payment_entry.get("company"),
	)

	for reference in payment_entry.get("references") or []:
		if context and context.get("project"):
			_set_if_empty(reference, "project", context.project)
		if cost_center:
			_set_if_empty(reference, "cost_center", cost_center)
		if context and context.get("party_type") == "Customer":
			_set_if_empty(reference, "customer", context.party)
		elif context and context.get("party_type") == "Supplier":
			_set_if_empty(reference, "supplier", context.party)


def get_party_fields_for_account(account, transaction=None, party_type=None, party=None):
	account_type = frappe.get_cached_value("Account", account, "account_type") if account else None
	required_party_type = PARTY_TYPE_BY_ACCOUNT_TYPE.get(account_type)
	if not required_party_type:
		return {}

	party = party or _get_document_party(transaction, required_party_type)
	if not party:
		frappe.throw(
			_("{0} is required against {1} account {2}.").format(
				required_party_type,
				account_type,
				frappe.bold(account),
			)
		)

	if party_type and party_type != required_party_type:
		frappe.throw(
			_("{0} account {1} requires Party Type {2}, but Party Type is {3}.").format(
				account_type,
				frappe.bold(account),
				frappe.bold(required_party_type),
				frappe.bold(party_type),
			)
		)

	return {"party_type": required_party_type, "party": party}


def get_gl_party_fields(account, transaction=None, party_type=None, party=None):
	return get_party_fields_for_account(
		account,
		transaction=transaction,
		party_type=party_type,
		party=party,
	)


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

	account = get_construction_account(company, "ra_bill_receivable")
	if currency:
		account_currency = frappe.get_cached_value("Account", account, "account_currency")
		company_currency = frappe.get_cached_value("Company", company, "default_currency")
		if account_currency not in (currency, company_currency):
			frappe.throw(
				_("RA Bill Receivable account {0} currency must be {1} for this invoice.").format(
					frappe.bold(account),
					frappe.bold(currency),
				)
			)
	return account


def get_or_create_retention_receivable_account(company=None):
	return get_construction_account(company, "retention_receivable")


def ensure_retention_receivable_account():
	company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
	return get_or_create_retention_receivable_account(company) if company else None


def _candidate_accounts(company, account_type, config, project=None, transaction=None):
	company_field = config.get("company_field")
	if company_field and frappe.get_meta("Company").has_field(company_field):
		yield frappe.db.get_value("Company", company, company_field)


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
		record = frappe.db.get_value(
			"Retention Record",
			record_name,
			["project", "customer"],
			as_dict=True,
		)
		return frappe._dict(
			{
				"account_context": "retention",
				"project": record.project if record else None,
				"party_type": "Customer",
				"party": record.customer if record else None,
			}
		)

	for reference in payment_entry.get("references") or []:
		if reference.reference_doctype == "Sales Order" and reference.reference_name:
			values = frappe.db.get_value(
				"Sales Order",
				reference.reference_name,
				["project", "customer"],
				as_dict=True,
			)
			return frappe._dict(
				{
					"account_context": "advance",
					"project": values.project if values else None,
					"party_type": "Customer",
					"party": values.customer if values else None,
				}
			)
		if reference.reference_doctype == "Sales Invoice" and reference.reference_name:
			fields = ["project", "customer"]
			if frappe.get_meta("Sales Invoice").has_field("ra_bill"):
				fields.append("ra_bill")
			invoice = frappe.db.get_value("Sales Invoice", reference.reference_name, fields, as_dict=True)
			if invoice and invoice.get("ra_bill"):
				return frappe._dict(
					{
						"account_context": "ra_bill",
						"project": invoice.get("project"),
						"party_type": "Customer",
						"party": invoice.get("customer"),
					}
				)
		if reference.reference_doctype == "Purchase Invoice" and reference.reference_name:
			values = frappe.db.get_value(
				"Purchase Invoice",
				reference.reference_name,
				["project", "supplier"],
				as_dict=True,
			)
			if values and values.project:
				return frappe._dict(
					{
						"account_context": "subcontract",
						"project": values.project,
						"party_type": "Supplier",
						"party": values.supplier,
					}
				)

	return None


def _get_payment_entry_party_context(payment_entry, context=None, required_party_type=None):
	if (
		context
		and context.get("party_type") == required_party_type
		and context.get("party")
	):
		return frappe._dict({"party_type": context.party_type, "party": context.party})

	if payment_entry.get("party") and (
		not payment_entry.get("party_type") or payment_entry.get("party_type") == required_party_type
	):
		return frappe._dict({"party_type": required_party_type, "party": payment_entry.party})

	document_party = _get_document_party(payment_entry, required_party_type)
	if document_party:
		return frappe._dict({"party_type": required_party_type, "party": document_party})

	reference_party = _get_payment_entry_reference_party(payment_entry, required_party_type)
	if reference_party:
		return frappe._dict({"party_type": required_party_type, "party": reference_party})

	if payment_entry.get("party_type") and payment_entry.get("party"):
		return frappe._dict({"party_type": payment_entry.party_type, "party": payment_entry.party})

	for account in (payment_entry.get("paid_from"), payment_entry.get("paid_to")):
		if _get_required_party_type_for_account(account) != required_party_type:
			continue

		party_fields = get_party_fields_for_account(
			account,
			transaction=payment_entry,
			party_type=required_party_type,
			party=payment_entry.get("party"),
		)
		return frappe._dict(party_fields)

	return None


def _validate_payment_entry_party(payment_entry, party_context):
	for account in (payment_entry.get("paid_from"), payment_entry.get("paid_to")):
		if not account:
			continue
		get_party_fields_for_account(
			account,
			transaction=payment_entry,
			party_type=payment_entry.get("party_type"),
			party=payment_entry.get("party"),
		)

	for row in payment_entry.get("deductions") or []:
		get_party_fields_for_account(
			row.account,
			transaction=payment_entry,
			party_type=party_context.party_type,
			party=party_context.party,
		)


def _get_document_party(doc, party_type):
	if not doc:
		return None

	fieldname = "customer" if party_type == "Customer" else "supplier"
	if hasattr(doc, "meta") and doc.meta.has_field(fieldname) and doc.get(fieldname):
		return doc.get(fieldname)

	if party_type == getattr(doc, "party_type", None) and getattr(doc, "party", None):
		return doc.party

	return None


def _set_payment_entry_account_if_empty(payment_entry, account_field, currency_field, default_account):
	account = payment_entry.get(account_field) or default_account
	if default_account and not payment_entry.get(account_field):
		payment_entry.set(account_field, default_account)
		account = default_account

	if account and payment_entry.meta.has_field(currency_field):
		payment_entry.set(currency_field, frappe.get_cached_value("Account", account, "account_currency"))


def _get_required_party_type_for_payment_entry(payment_entry):
	party_types = []
	for account in _get_payment_entry_accounts(payment_entry):
		party_type = _get_required_party_type_for_account(account)
		if party_type and party_type not in party_types:
			party_types.append(party_type)

	if not party_types:
		return None
	if len(party_types) > 1:
		frappe.throw(
			_("Payment Entry cannot infer one Party Type because it uses both Receivable and Payable accounts.")
		)
	return party_types[0]


def _get_payment_entry_accounts(payment_entry):
	for account in (payment_entry.get("paid_from"), payment_entry.get("paid_to")):
		if account:
			yield account
	for row in payment_entry.get("deductions") or []:
		if row.get("account"):
			yield row.account


def _get_required_party_type_for_account(account):
	if not account:
		return None

	account_type = frappe.get_cached_value("Account", account, "account_type")
	return PARTY_TYPE_BY_ACCOUNT_TYPE.get(account_type)


def _get_first_party_account(payment_entry, party_type):
	for account in _get_payment_entry_accounts(payment_entry):
		if _get_required_party_type_for_account(account) == party_type:
			return account
	return None


def _get_account_type_label(party_type):
	if party_type == "Customer":
		return "Receivable"
	if party_type == "Supplier":
		return "Payable"
	return "party"


def _get_payment_entry_reference_party(payment_entry, required_party_type):
	for reference in payment_entry.get("references") or []:
		party = _get_reference_party(
			reference.reference_doctype,
			reference.reference_name,
			required_party_type,
		)
		if party:
			return party

	return None


def _get_reference_party(reference_doctype, reference_name, required_party_type):
	if not reference_doctype or not reference_name:
		return None

	if required_party_type == "Customer":
		if reference_doctype in ("Sales Invoice", "Sales Order"):
			return frappe.db.get_value(reference_doctype, reference_name, "customer")
		if reference_doctype == "RA Bill":
			return frappe.db.get_value("RA Bill", reference_name, "customer")
		if reference_doctype == "Retention Record":
			return frappe.db.get_value("Retention Record", reference_name, "customer")

	if required_party_type == "Supplier":
		if reference_doctype in ("Purchase Invoice", "Purchase Order", "Purchase Receipt"):
			return frappe.db.get_value(reference_doctype, reference_name, "supplier")
		if reference_doctype in ("SC Bill", "SC Work Order"):
			return frappe.db.get_value(reference_doctype, reference_name, "supplier")

	return None


def _has_construction_sales_order(invoice):
	if invoice.meta.has_field("sales_order") and invoice.get("sales_order"):
		return True
	for row in invoice.get("items") or []:
		if row.get("sales_order"):
			return True
	return False


def _is_construction_purchase_invoice(invoice):
	if invoice.meta.has_field("sc_bill") and invoice.get("sc_bill"):
		return True
	if invoice.name and frappe.db.exists("SC Bill", {"purchase_invoice": invoice.name}):
		return True
	return bool(invoice.get("project"))


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
