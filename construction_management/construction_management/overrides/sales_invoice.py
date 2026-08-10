import frappe
from frappe import _
from frappe.utils import flt, getdate

from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from erpnext.accounts.utils import get_account_currency

from construction_management.construction_management.accounting_dimensions import (
	get_ra_bill_project_cost_center,
)
from construction_management.construction_management.utils.accounting import get_construction_account


AMOUNT_TOLERANCE = 0.0001
BREAKDOWN_TYPES = {
	"retention": "Retention Deduction",
}
LEGACY_RETENTION_BREAKDOWN_TYPE = "Retention Receivable"


class ConstructionSalesInvoice(SalesInvoice):
	def validate(self):
		self.normalize_payment_schedule_date_types()
		super().validate()
		self.validate_retention_account_for_submit()
		self.set_payment_breakdown()

	def make_customer_gl_entry(self, gl_entries):
		retention_context = self.get_retention_accounting_context()
		if not retention_context:
			super().make_customer_gl_entry(gl_entries)
			return

		against_voucher = self.name
		if self.is_return and self.return_against and not self.update_outstanding_for_self:
			against_voucher = self.return_against

		for row in self.get_retention_receivable_gl_rows(retention_context, against_voucher):
			gl_entries.append(row)

	def validate_retention_account_for_submit(self):
		if getattr(self, "_action", None) != "submit":
			return

		if not self.get_retention_accounting_context(validate_account=False):
			return

		company = self.company
		if not self.debit_to:
			frappe.throw(_("Trade Receivable Account is required before submitting Sales Invoice."))

		if not frappe.get_cached_value("Company", company, "default_retention_receivable_account"):
			frappe.throw(
				_(
					"Default Retention Receivable Account is not configured in Company -> "
					"Construction Accounting Settings."
				)
			)

		get_construction_account(
			company,
			"retention_receivable",
			project=self.project,
			transaction=self,
		)

	def get_retention_accounting_context(self, validate_account=True):
		if self.is_internal_transfer() or self.is_return:
			return None

		ra_bill = self.get("ra_bill") if self.meta.has_field("ra_bill") else None
		if not ra_bill:
			return None

		if self.meta.has_field("retention_record") and self.get("retention_record"):
			return None

		ra_bill_values = frappe.db.get_value(
			"RA Bill",
			ra_bill,
			["name", "retention_amount", "project"],
			as_dict=True,
		)
		if not ra_bill_values:
			return None

		retention_amount = flt(ra_bill_values.retention_amount)
		total = self.get_customer_gl_total()
		if retention_amount <= AMOUNT_TOLERANCE or total <= AMOUNT_TOLERANCE:
			return None

		retention_amount = min(retention_amount, total)
		context = frappe._dict(
			{
				"ra_bill": ra_bill_values.name,
				"project": self.project or ra_bill_values.project,
				"trade_receivable_account": self.debit_to,
				"retention_amount": retention_amount,
				"trade_amount": max(0, total - retention_amount),
				"advance_amount": self.get_total_advance_recovery_amount(),
				"base_retention_amount": min(
					self.get_customer_gl_base_total(),
					flt(retention_amount * flt(self.conversion_rate or 1)),
				),
			}
		)
		context.base_trade_amount = max(
			0,
			self.get_customer_gl_base_total() - context.base_retention_amount,
		)
		context.retention_account = self.get_retention_receivable_account(
			context.project,
			validate_account=validate_account,
		)
		context.trade_receivable_label = self.get_account_schedule_label(
			context.trade_receivable_account
		)
		context.retention_receivable_label = self.get_account_schedule_label(
			context.retention_account
		)
		context.advance_recovery_account = self.get_advance_recovery_account(
			context.project,
			context.advance_amount,
		)

		return context

	def get_retention_receivable_account(self, project, validate_account=True):
		if validate_account:
			return get_construction_account(
				self.company,
				"retention_receivable",
				project=project,
				transaction=self,
			)

		return frappe.get_cached_value(
			"Company",
			self.company,
			"default_retention_receivable_account",
		)

	def get_account_schedule_label(self, account):
		if not account:
			return ""

		return account

	def get_retention_receivable_gl_rows(self, context, against_voucher):
		return [
			self.get_receivable_gl_row(
				account=self.debit_to,
				account_currency=self.party_account_currency,
				amount=context.trade_amount,
				base_amount=context.base_trade_amount,
				against_voucher=against_voucher,
				cost_center=self.cost_center,
				project=context.project,
			),
			self.get_receivable_gl_row(
				account=context.retention_account,
				account_currency=get_account_currency(context.retention_account),
				amount=context.retention_amount,
				base_amount=context.base_retention_amount,
				against_voucher=against_voucher,
				cost_center=get_ra_bill_project_cost_center(
					context.ra_bill,
					project=context.project,
					company=self.company,
				),
				project=context.project,
			),
		]

	def get_receivable_gl_row(
		self,
		account,
		account_currency,
		amount,
		base_amount,
		against_voucher,
		cost_center=None,
		project=None,
	):
		debit_in_account_currency = (
			base_amount if account_currency == self.company_currency else amount
		)
		return self.get_gl_dict(
			{
				"account": account,
				"party_type": "Customer",
				"party": self.customer,
				"due_date": self.due_date,
				"against": self.against_income_account,
				"debit": base_amount,
				"debit_in_account_currency": debit_in_account_currency,
				"debit_in_transaction_currency": amount,
				"against_voucher": against_voucher,
				"against_voucher_type": self.doctype,
				"cost_center": cost_center,
				"project": project,
			},
			account_currency,
			item=self,
		)

	def get_customer_gl_total(self):
		total_field = "rounded_total" if self.rounding_adjustment and self.rounded_total else "grand_total"
		return flt(self.get(total_field), self.precision(total_field))

	def get_customer_gl_base_total(self):
		total_field = (
			"base_rounded_total"
			if self.base_rounding_adjustment and self.base_rounded_total
			else "base_grand_total"
		)
		return flt(self.get(total_field), self.precision(total_field))

	def set_payment_breakdown(self):
		if not self.meta.has_field("payment_breakdown"):
			return

		context = self.get_retention_accounting_context(validate_account=False)
		if not context:
			return

		total = context.trade_amount + context.retention_amount
		if total <= AMOUNT_TOLERANCE:
			return

		self.set("payment_breakdown", [])
		self.append_payment_breakdown_row(
			BREAKDOWN_TYPES["retention"],
			context.retention_account,
			context.retention_amount,
			context.retention_amount,
			total,
		)

	def append_payment_breakdown_row(
		self,
		breakdown_type,
		account,
		amount,
		outstanding_amount,
		total,
		status="Pending",
	):
		if amount <= AMOUNT_TOLERANCE:
			return

		self.append(
			"payment_breakdown",
			{
				"type": breakdown_type,
				"description": account,
				"account": account,
				"amount": amount,
				"percentage": flt((amount / total) * 100),
				"outstanding_amount": outstanding_amount,
				"status": status,
			},
		)

	def normalize_payment_schedule_date_types(self):
		for row in self.get("payment_schedule") or []:
			if row.due_date:
				row.due_date = getdate(row.due_date)
			if row.discount_date:
				row.discount_date = getdate(row.discount_date)

	def get_total_advance_recovery_amount(self):
		return sum(flt(row.allocated_amount) for row in self.get("advances") or [])

	def get_advance_recovery_account(self, project, advance_amount):
		if advance_amount <= AMOUNT_TOLERANCE:
			return None

		return get_construction_account(
			self.company,
			"advance_recovery",
			project=project,
			transaction=self,
		)


def apply_net_certified_vat_to_sales_invoice(si, ra_bill, advance_native=0):
	"""
	For RA Bill invoices, VAT must be charged on the net certified amount
	(gross work done - retention - native advance recovery), not on the full
	gross work done. Income (net_total / item amounts) is left untouched -
	only the VAT tax row's amount is reduced.

	Only called from RA Bill.create_sales_invoice, so ordinary Sales Invoices
	(not created from an RA Bill) are never affected.
	"""
	if not si.meta.has_field("taxes") or not si.get("taxes"):
		return None

	vat_row = None
	for row in si.get("taxes"):
		if row.charge_type == "On Net Total" and "vat" in (row.account_head or "").lower():
			vat_row = row
			break

	if not vat_row:
		return None

	retention_total = flt(ra_bill.get("retention_amount"))
	net_total = flt(si.net_total)
	vat_base = max(net_total - retention_total - flt(advance_native), 0)
	vat_amount = flt(
		vat_base * flt(vat_row.rate) / 100,
		si.precision("tax_amount", "taxes"),
	)

	vat_row.charge_type = "Actual"
	vat_row.tax_amount = vat_amount

	if hasattr(si, "calculate_taxes_and_totals"):
		si.calculate_taxes_and_totals()

	return vat_amount


def sync_sales_invoice_payment_breakdown(doc, method=None):
	invoice = doc if getattr(doc, "doctype", None) == "Sales Invoice" else frappe.get_doc("Sales Invoice", doc)
	if not invoice.meta.has_field("payment_breakdown") or not invoice.get("payment_breakdown"):
		return

	for row in invoice.get("payment_breakdown") or []:
		outstanding = get_payment_breakdown_outstanding(invoice, row)
		status = get_payment_breakdown_status(row.type, outstanding)
		frappe.db.set_value(
			row.doctype,
			row.name,
			{
				"outstanding_amount": outstanding,
				"status": status,
			},
			update_modified=False,
		)


def sync_sales_invoice_payment_breakdown_from_payment_entry(doc, method=None):
	for invoice_name in get_payment_entry_sales_invoices(doc):
		if frappe.db.exists("Sales Invoice", invoice_name):
			sync_sales_invoice_payment_breakdown(invoice_name)


def get_payment_entry_sales_invoices(payment_entry):
	invoices = set()

	for reference in payment_entry.get("references") or []:
		if reference.reference_doctype == "Sales Invoice" and reference.reference_name:
			invoices.add(reference.reference_name)

	for fieldname in ("custom_original_sales_invoice",):
		if payment_entry.meta.has_field(fieldname) and payment_entry.get(fieldname):
			invoices.add(payment_entry.get(fieldname))

	for fieldname in ("custom_retention_record", "retention_record"):
		if not payment_entry.meta.has_field(fieldname) or not payment_entry.get(fieldname):
			continue

		sales_invoice = frappe.db.get_value(
			"Retention Record",
			payment_entry.get(fieldname),
			"sales_invoice",
		)
		if sales_invoice:
			invoices.add(sales_invoice)

	return invoices


def get_payment_breakdown_outstanding(invoice, row):
	if row.type in (BREAKDOWN_TYPES["retention"], LEGACY_RETENTION_BREAKDOWN_TYPE):
		return max(0, flt(row.amount) - get_retention_released_amount(invoice, row.account))

	return flt(row.outstanding_amount)


def get_payment_breakdown_status(breakdown_type, outstanding):
	if flt(outstanding) > AMOUNT_TOLERANCE:
		return "Pending"

	if breakdown_type in (BREAKDOWN_TYPES["retention"], LEGACY_RETENTION_BREAKDOWN_TYPE):
		return "Released"

	return "Paid"


def get_account_outstanding(sales_invoice, account, customer):
	if not sales_invoice or not account or not customer:
		return 0

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


def get_retention_released_amount(invoice, retention_account):
	if not retention_account:
		return 0

	base_filters = {
		"docstatus": 1,
		"payment_type": "Receive",
		"party_type": "Customer",
		"customer": invoice.customer,
		"company": invoice.company,
		"paid_from": retention_account,
	}
	base_filters["party"] = base_filters.pop("customer")

	total = 0
	seen = set()
	retention_records = frappe.get_all(
		"Retention Record",
		filters={"sales_invoice": invoice.name},
		pluck="name",
	)
	for filters in get_retention_payment_filters(base_filters, invoice.name, retention_records):
		for row in frappe.get_all("Payment Entry", filters=filters, fields=["name", "paid_amount"]):
			if row.name in seen:
				continue

			seen.add(row.name)
			total += flt(row.paid_amount)

	return total


def get_retention_payment_filters(base_filters, sales_invoice, retention_records):
	meta = frappe.get_meta("Payment Entry")
	if meta.has_field("custom_original_sales_invoice"):
		filters = base_filters.copy()
		filters["custom_original_sales_invoice"] = sales_invoice
		yield filters

	if not retention_records:
		return

	for fieldname in ("custom_retention_record", "retention_record"):
		if not meta.has_field(fieldname):
			continue

		filters = base_filters.copy()
		filters[fieldname] = ["in", retention_records]
		yield filters
