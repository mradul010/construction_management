import frappe
from frappe import _
from frappe.utils import flt

from construction_management.construction_management.accounting_dimensions import (
	apply_ra_bill_cost_center_to_payment_entry,
	get_ra_bill_project_cost_center,
)


RETENTION_ACCOUNT_NAME = "Retention Receivable"
RETENTION_COMPANY = "Qatra Building Contracting"
RETENTION_PARENT_ACCOUNT = "Current Assets - QBC"
RETENTION_PARENT_ACCOUNT_FALLBACK = "Current Assets"
RETENTION_DESCRIPTION_PREFIX = "Retention against RA Bill"
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
	apply_retention_deduction(payment_entry)
	return payment_entry


def apply_retention_deduction(payment_entry):
	if not payment_entry or payment_entry.payment_type != "Receive":
		return payment_entry

	retention_context = _get_payment_entry_retention_context(payment_entry)
	if not retention_context:
		return payment_entry

	account = get_or_create_retention_receivable_account(retention_context.company)
	if _has_retention_deduction(payment_entry, account):
		apply_ra_bill_cost_center_to_payment_entry(payment_entry, retention_account=account)
		return payment_entry

	retention_amount = flt(retention_context.retention_amount)
	if retention_amount <= AMOUNT_TOLERANCE:
		return payment_entry

	retention_amount = min(retention_amount, flt(retention_context.allocated_amount))
	if retention_amount <= AMOUNT_TOLERANCE:
		return payment_entry

	cost_center = get_ra_bill_project_cost_center(
		retention_context.ra_bill,
		project=retention_context.project,
		company=retention_context.company,
	)
	if payment_entry.meta.has_field("project") and retention_context.project and not payment_entry.get("project"):
		payment_entry.project = retention_context.project

	payment_entry.append(
		"deductions",
		{
			"account": account,
			"cost_center": cost_center,
			"amount": retention_amount,
			"description": _get_retention_deduction_description(retention_context.ra_bill),
		},
	)

	_set_received_amount_after_retention(payment_entry, retention_amount)
	if hasattr(payment_entry, "set_amounts"):
		payment_entry.set_amounts()

	return payment_entry


def get_or_create_retention_receivable_account(company=None):
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
			["name", "company", "project", "ra_bill", "retention_record"],
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


def _has_retention_deduction(payment_entry, account):
	for row in payment_entry.get("deductions") or []:
		if row.account == account and flt(row.amount) > AMOUNT_TOLERANCE:
			return True
	return False


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


def _get_retention_deduction_description(ra_bill):
	if ra_bill:
		return f"{RETENTION_DESCRIPTION_PREFIX} {ra_bill}"
	return "Retention Deduction"


def _set_received_amount_after_retention(payment_entry, retention_amount):
	if payment_entry.payment_type != "Receive":
		return

	retention_amount = flt(retention_amount)
	allocated_amount = sum(flt(row.allocated_amount) for row in payment_entry.get("references") or [])
	net_received_amount = max(0, allocated_amount - retention_amount)
	if flt(payment_entry.paid_amount) > net_received_amount + AMOUNT_TOLERANCE:
		payment_entry.paid_amount = net_received_amount
	if flt(payment_entry.received_amount) > net_received_amount + AMOUNT_TOLERANCE:
		payment_entry.received_amount = net_received_amount
