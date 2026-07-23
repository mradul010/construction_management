import frappe
from frappe import _
from frappe.utils import flt

from construction_management.construction_management.utils.accounting import (
	apply_construction_accounts_to_payment_entry,
	ensure_retention_receivable_account as ensure_retention_account,
	get_construction_account,
	get_or_create_retention_receivable_account as get_or_create_retention_account,
)


RETENTION_ACCOUNT_NAME = "Retention Receivable"
RETENTION_COMPANY = "Qatra Building Contracting"
RETENTION_PARENT_ACCOUNT = "Current Assets - QBC"
RETENTION_PARENT_ACCOUNT_FALLBACK = "Current Assets"
AMOUNT_TOLERANCE = 0.0001


@frappe.whitelist()
def get_payment_entry(
	dt,
	dn,
	party_amount=None,
	bank_account=None,
	bank_amount=None,
	party_type=None,
	payment_type=None,
	reference_date=None,
	created_from_payment_request=False,
):
	from erpnext.accounts.doctype.payment_entry.payment_entry import (
		get_payment_entry as erpnext_get_payment_entry,
	)

	payment_entry = erpnext_get_payment_entry(
		dt,
		dn,
		party_amount=party_amount,
		bank_account=bank_account,
		bank_amount=bank_amount,
		party_type=party_type,
		payment_type=payment_type,
		reference_date=reference_date,
		created_from_payment_request=created_from_payment_request,
	)
	apply_trade_receivable_allocation(payment_entry)
	apply_trade_payable_allocation(payment_entry)
	apply_construction_accounts_to_payment_entry(payment_entry)
	return payment_entry


def apply_trade_receivable_allocation(payment_entry):
	if not payment_entry or payment_entry.payment_type != "Receive":
		return payment_entry

	retention_context = _get_payment_entry_retention_context(payment_entry)
	if not retention_context:
		return payment_entry

	remove_retention_deductions(payment_entry, {retention_context.retention_receivable_account})
	trade_outstanding = get_trade_receivable_outstanding(
		retention_context.sales_invoice,
		retention_context.trade_receivable_account,
		retention_context.customer,
	)

	for reference in payment_entry.get("references") or []:
		if (
			reference.reference_doctype == "Sales Invoice"
			and reference.reference_name == retention_context.sales_invoice
		):
			reference.outstanding_amount = trade_outstanding
			reference.allocated_amount = min(flt(reference.allocated_amount), trade_outstanding)

	_set_received_amount(payment_entry, trade_outstanding)
	if hasattr(payment_entry, "set_amounts"):
		payment_entry.set_amounts()

	return payment_entry


def remove_retention_deductions(payment_entry, retention_accounts):
	if not retention_accounts:
		return

	payment_entry.set(
		"deductions",
		[
			row
			for row in payment_entry.get("deductions") or []
			if row.account not in retention_accounts
		],
	)


def get_or_create_retention_receivable_account(company=None):
	return get_or_create_retention_account(company)


def ensure_retention_receivable_account():
	return ensure_retention_account()


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


def _get_payment_entry_retention_context(payment_entry):
	for reference in payment_entry.get("references") or []:
		if reference.reference_doctype != "Sales Invoice" or not reference.reference_name:
			continue

		invoice_values = frappe.db.get_value(
			"Sales Invoice",
			reference.reference_name,
			["name", "company", "customer", "project", "ra_bill", "retention_record", "debit_to"],
			as_dict=True,
		)
		if not invoice_values or not _is_initial_ra_bill_invoice(invoice_values):
			continue

		ra_bill_values = frappe.db.get_value(
			"RA Bill",
			invoice_values.ra_bill,
			["name", "retention_amount"],
			as_dict=True,
		)
		if not ra_bill_values or flt(ra_bill_values.retention_amount) <= AMOUNT_TOLERANCE:
			continue

		return frappe._dict(
			{
				"company": invoice_values.company,
				"project": invoice_values.project or frappe.db.get_value("RA Bill", invoice_values.ra_bill, "project"),
				"ra_bill": ra_bill_values.name,
				"sales_invoice": invoice_values.name,
				"customer": invoice_values.customer,
				"trade_receivable_account": invoice_values.debit_to,
				"retention_receivable_account": get_construction_account(
					invoice_values.company,
					"retention_receivable",
					project=invoice_values.project,
					transaction=payment_entry,
				),
				"retention_amount": ra_bill_values.retention_amount,
				"allocated_amount": reference.allocated_amount,
			}
		)

	return None


def _is_initial_ra_bill_invoice(invoice_values):
	if not invoice_values.get("ra_bill"):
		return False
	if invoice_values.get("retention_record"):
		return False
	if frappe.get_meta("Sales Invoice").has_field("retention_records"):
		return not frappe.db.exists(
			"Sales Invoice Retention Reference",
			{"parent": invoice_values.name, "parenttype": "Sales Invoice"},
		)
	return True


def _get_retention_cost_center(company):
	cost_center = frappe.db.get_value("Company", company, "cost_center")
	if cost_center:
		return cost_center

	cost_center = frappe.db.get_value(
		"Cost Center",
		{"company": company, "is_group": 0, "disabled": 0},
		"name",
	)
	if cost_center:
		return cost_center

	frappe.throw(_("Please set a default Cost Center for company {0}.").format(company))


def _set_received_amount(payment_entry, amount):
	amount = flt(amount)
	payment_entry.paid_amount = amount
	payment_entry.received_amount = amount


def get_trade_receivable_outstanding(sales_invoice, account, customer):
	if not sales_invoice or not account or not customer:
		return 0

	breakdown_outstanding = get_trade_receivable_breakdown_outstanding(sales_invoice, account)
	if breakdown_outstanding is not None:
		return breakdown_outstanding

	outstanding = frappe.db.sql(
		"""
		SELECT SUM(amount_in_account_currency)
		FROM `tabPayment Ledger Entry`
		WHERE delinked = 0
			AND account = %s
			AND party_type = 'Customer'
			AND party = %s
			AND against_voucher_type = 'Sales Invoice'
			AND against_voucher_no = %s
		""",
		(account, customer, sales_invoice),
	)
	if outstanding and outstanding[0][0] is not None:
		return max(0, flt(outstanding[0][0]))

	outstanding = frappe.db.sql(
		"""
		SELECT SUM(debit_in_account_currency) - SUM(credit_in_account_currency)
		FROM `tabGL Entry`
		WHERE is_cancelled = 0
			AND account = %s
			AND party_type = 'Customer'
			AND party = %s
			AND against_voucher_type = 'Sales Invoice'
			AND against_voucher = %s
		""",
		(account, customer, sales_invoice),
	)
	return max(0, flt(outstanding[0][0] if outstanding else 0))


def get_trade_receivable_breakdown_outstanding(sales_invoice, account):
	if not frappe.get_meta("Sales Invoice").has_field("payment_breakdown"):
		return None

	row = frappe.db.get_value(
		"Sales Invoice Payment Breakdown",
		{
			"parent": sales_invoice,
			"parenttype": "Sales Invoice",
			"parentfield": "payment_breakdown",
			"type": "Trade Receivable",
			"account": account,
		},
		"outstanding_amount",
	)
	if row is None:
		return None

	return max(0, flt(row))


def apply_trade_payable_allocation(payment_entry):
	if not payment_entry or payment_entry.payment_type != "Pay":
		return payment_entry

	retention_context = _get_payment_entry_retention_payable_context(payment_entry)
	if not retention_context:
		return payment_entry

	trade_outstanding = get_trade_payable_outstanding(
		retention_context.purchase_invoice,
		retention_context.trade_payable_account,
		retention_context.supplier,
	)

	for reference in payment_entry.get("references") or []:
		if (
			reference.reference_doctype == "Purchase Invoice"
			and reference.reference_name == retention_context.purchase_invoice
		):
			reference.outstanding_amount = trade_outstanding
			reference.allocated_amount = min(flt(reference.allocated_amount), trade_outstanding)

	_set_paid_amount(payment_entry, trade_outstanding)
	if hasattr(payment_entry, "set_amounts"):
		payment_entry.set_amounts()

	return payment_entry


def _get_payment_entry_retention_payable_context(payment_entry):
	for reference in payment_entry.get("references") or []:
		if reference.reference_doctype != "Purchase Invoice" or not reference.reference_name:
			continue

		invoice_meta = frappe.get_meta("Purchase Invoice")
		fields = ["name", "company", "supplier", "project", "credit_to"]
		for fieldname in ("sc_bill", "retention_payable"):
			if invoice_meta.has_field(fieldname):
				fields.append(fieldname)

		invoice_values = frappe.db.get_value(
			"Purchase Invoice",
			reference.reference_name,
			fields,
			as_dict=True,
		)
		if not invoice_values or not invoice_values.get("sc_bill"):
			continue

		sc_bill_values = frappe.db.get_value(
			"SC Bill",
			invoice_values.sc_bill,
			["name", "retention_amount"],
			as_dict=True,
		)
		if not sc_bill_values or flt(sc_bill_values.retention_amount) <= AMOUNT_TOLERANCE:
			continue

		return frappe._dict(
			{
				"company": invoice_values.company,
				"project": invoice_values.project,
				"sc_bill": sc_bill_values.name,
				"purchase_invoice": invoice_values.name,
				"supplier": invoice_values.supplier,
				"trade_payable_account": invoice_values.credit_to,
				"retention_payable_account": get_construction_account(
					invoice_values.company,
					"subcontractor_retention_payable",
					project=invoice_values.project,
					transaction=payment_entry,
				),
				"retention_amount": sc_bill_values.retention_amount,
				"allocated_amount": reference.allocated_amount,
			}
		)

	return None


def get_trade_payable_outstanding(purchase_invoice, account, supplier):
	if not purchase_invoice or not account or not supplier:
		return 0

	breakdown_outstanding = get_trade_payable_breakdown_outstanding(purchase_invoice, account)
	if breakdown_outstanding is not None:
		return breakdown_outstanding

	outstanding = frappe.db.sql(
		"""
		SELECT ABS(SUM(amount_in_account_currency))
		FROM `tabPayment Ledger Entry`
		WHERE delinked = 0
			AND account = %s
			AND party_type = 'Supplier'
			AND party = %s
			AND against_voucher_type = 'Purchase Invoice'
			AND against_voucher_no = %s
		""",
		(account, supplier, purchase_invoice),
	)
	if outstanding and outstanding[0][0] is not None:
		return max(0, flt(outstanding[0][0]))

	outstanding = frappe.db.sql(
		"""
		SELECT SUM(credit_in_account_currency) - SUM(debit_in_account_currency)
		FROM `tabGL Entry`
		WHERE is_cancelled = 0
			AND account = %s
			AND party_type = 'Supplier'
			AND party = %s
			AND against_voucher_type = 'Purchase Invoice'
			AND against_voucher = %s
		""",
		(account, supplier, purchase_invoice),
	)
	return max(0, flt(outstanding[0][0] if outstanding else 0))


def get_trade_payable_breakdown_outstanding(purchase_invoice, account):
	if not frappe.get_meta("Purchase Invoice").has_field("payment_breakdown"):
		return None

	row = frappe.db.get_value(
		"Purchase Invoice Payment Breakdown",
		{
			"parent": purchase_invoice,
			"parenttype": "Purchase Invoice",
			"parentfield": "payment_breakdown",
			"type": "Trade Payable",
			"account": account,
		},
		"outstanding_amount",
	)
	if row is None:
		return None

	return max(0, flt(row))


def _set_paid_amount(payment_entry, amount):
	amount = flt(amount)
	payment_entry.paid_amount = amount
	payment_entry.received_amount = amount
