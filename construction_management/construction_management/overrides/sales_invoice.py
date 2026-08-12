import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from erpnext.accounts.utils import get_account_currency
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from erpnext.controllers.accounts_controller import get_taxes_and_charges

from construction_management.construction_management.accounting_dimensions import (
	get_ra_bill_project_cost_center,
)
from construction_management.construction_management.utils.accounting import get_construction_account


AMOUNT_TOLERANCE = 0.0001
BREAKDOWN_TYPES = {
	"retention": "Retention Deduction",
}
LEGACY_RETENTION_BREAKDOWN_TYPE = "Retention Receivable"
RA_BILL_ADVANCE_TAX_DESCRIPTION = "Advance Recovery"
RA_BILL_RETENTION_TAX_DESCRIPTION = BREAKDOWN_TYPES["retention"]
VAT_KEYWORD = "vat"
NON_TAXABLE_CATEGORY_KEYWORDS = ("zero", "exempt")


class ConstructionSalesInvoice(SalesInvoice):
	def set_advances(self):
		if self.is_ra_bill_invoice():
			self.set("advances", [])
			if self.meta.has_field("total_advance"):
				self.total_advance = 0
			return

		return super().set_advances()

	def validate(self):
		self.normalize_payment_schedule_date_types()
		if self.is_ra_bill_invoice():
			clear_ra_bill_item_tax_overrides(self)
			self.set("advances", [])
		super().validate()
		if self.is_ra_bill_invoice():
			clear_ra_bill_item_tax_overrides(self)
		self.validate_retention_account_for_submit()
		self.set_payment_breakdown()

	def on_cancel(self):
		super().on_cancel()
		if self.is_ra_bill_invoice():
			self.ignore_linked_doctypes = tuple(
				set(list(self.ignore_linked_doctypes or []) + ["Advance Payment Ledger Entry", "RA Bill"])
			)

	def make_customer_gl_entry(self, gl_entries):
		super().make_customer_gl_entry(gl_entries)

	def make_tax_gl_entries(self, gl_entries):
		if not self.is_ra_bill_invoice():
			return super().make_tax_gl_entries(gl_entries)

		enable_discount_accounting = cint(
			frappe.get_single_value("Selling Settings", "enable_discount_accounting")
		)
		retention_tax_row = get_ra_bill_retention_tax_row(self)
		advance_tax_row = get_ra_bill_advance_tax_row(self)
		advance_recovery_validated = False

		for tax in self.get("taxes"):
			amount, base_amount = self.get_tax_amounts(tax, enable_discount_accounting)
			if not flt(tax.base_tax_amount_after_discount_amount):
				continue

			if is_same_child_row(tax, retention_tax_row):
				validate_ra_bill_retention_tax_account(tax.account_head, self.company)

			if is_same_child_row(tax, advance_tax_row):
				if not advance_recovery_validated:
					validate_ra_bill_advance_recovery_balance(
						self,
						abs(flt(base_amount, tax.precision("base_tax_amount_after_discount_amount"))),
					)
					advance_recovery_validated = True
				self.make_ra_bill_advance_tax_gl_entries(
					gl_entries,
					tax,
					amount,
					base_amount,
				)
				continue

			append_tax_gl_entry(self, gl_entries, tax, amount, base_amount)

	def make_ra_bill_advance_tax_gl_entries(
		self,
		gl_entries,
		tax,
		amount,
		base_amount,
	):
		account_type = frappe.get_cached_value("Account", tax.account_head, "account_type")
		if account_type != "Receivable":
			frappe.throw(
				_(
					"Customer advance deduction account {0} must remain a Receivable account "
					"so ERPNext can maintain the customer payment ledger."
				).format(frappe.bold(tax.account_head))
			)

		append_tax_gl_entry(
			self,
			gl_entries,
			tax,
			amount,
			base_amount,
			{
				"party_type": "Customer",
				"party": self.customer,
				"voucher_detail_no": tax.get("name"),
			},
		)

	def is_ra_bill_invoice(self):
		if not (self.meta.has_field("ra_bill") and self.get("ra_bill")):
			return False

		if self.meta.has_field("retention_record") and self.get("retention_record"):
			return False

		return True

	def has_ra_bill_deduction_tax_rows(self):
		if not self.is_ra_bill_invoice():
			return False

		return bool(get_ra_bill_retention_tax_row(self) or get_ra_bill_advance_tax_row(self))

	def validate_retention_account_for_submit(self):
		if getattr(self, "_action", None) != "submit":
			return

		if self.is_ra_bill_invoice():
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

		if self.has_ra_bill_deduction_tax_rows():
			self.set("payment_breakdown", [])
			retention_row = get_ra_bill_retention_tax_row(self)
			if retention_row:
				retention_amount = abs(flt(retention_row.tax_amount))
				self.append_payment_breakdown_row(
					RA_BILL_RETENTION_TAX_DESCRIPTION,
					retention_row.account_head,
					retention_amount,
					retention_amount,
					flt(self.net_total) or retention_amount,
				)
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


def apply_ra_bill_deduction_taxes_to_sales_invoice(si, ra_bill, advance_native=0):
	"""Build RA-bill Sales Invoice deductions as standard tax/charge rows."""
	if not si.meta.has_field("taxes"):
		return

	clear_ra_bill_item_tax_overrides(si)
	vat_config = get_ra_bill_vat_config(si, ra_bill)
	retention_amount = flt(ra_bill.get("retention_amount"))
	advance_amount = flt(advance_native)
	project = si.get("project") or ra_bill.get("project")
	cost_center = si.get("cost_center") or get_ra_bill_project_cost_center(
		ra_bill.get("name"),
		project=project,
		company=si.company,
	)

	si.set("taxes", [])
	last_deduction_idx = 0

	if retention_amount > AMOUNT_TOLERANCE:
		si.append(
			"taxes",
			{
				"charge_type": "Actual",
				"account_head": get_construction_account(
					si.company,
					"retention_receivable",
					project=project,
					transaction=si,
				),
				"description": RA_BILL_RETENTION_TAX_DESCRIPTION,
				"tax_amount": -retention_amount,
				"cost_center": cost_center,
				"project": project,
			},
		)
		last_deduction_idx = len(si.get("taxes"))

	if advance_amount > AMOUNT_TOLERANCE:
		si.append(
			"taxes",
			{
				"charge_type": "Actual",
				"account_head": get_construction_account(
					si.company,
					"customer_advance",
					project=project,
					transaction=si,
				),
				"description": RA_BILL_ADVANCE_TAX_DESCRIPTION,
				"tax_amount": -advance_amount,
				"cost_center": cost_center,
				"project": project,
			},
		)
		last_deduction_idx = len(si.get("taxes"))

	if vat_config:
		vat_row = {
			"charge_type": "On Previous Row Total" if last_deduction_idx else "On Net Total",
			"account_head": vat_config.account_head,
			"description": vat_config.description,
			"rate": vat_config.rate,
			"cost_center": vat_config.get("cost_center") or cost_center,
			"project": project,
		}
		if last_deduction_idx:
			vat_row["row_id"] = last_deduction_idx
		si.append("taxes", vat_row)

	si.set("advances", [])
	if si.meta.has_field("total_advance"):
		si.total_advance = 0


def clear_ra_bill_item_tax_overrides(si):
	for item in si.get("items") or []:
		if item.meta.has_field("item_tax_template"):
			item.item_tax_template = None
		if item.meta.has_field("item_tax_rate"):
			item.item_tax_rate = "{}"


def get_ra_bill_retention_tax_row(si):
	return get_ra_bill_deduction_tax_row(
		si,
		"retention_receivable",
		{RA_BILL_RETENTION_TAX_DESCRIPTION.lower()},
	)


def get_ra_bill_advance_tax_row(si):
	return get_ra_bill_deduction_tax_row(
		si,
		"customer_advance",
		{RA_BILL_ADVANCE_TAX_DESCRIPTION.lower()},
	)


def get_ra_bill_deduction_tax_row(si, account_key, descriptions):
	if not (si.meta.has_field("ra_bill") and si.get("ra_bill")):
		return None

	try:
		account = get_construction_account(
			si.company,
			account_key,
			project=si.get("project"),
			transaction=si,
		)
	except Exception:
		account = None

	for row in si.get("taxes") or []:
		description = (row.description or "").strip().lower()
		if (
			row.charge_type == "Actual"
			and flt(row.tax_amount) < -AMOUNT_TOLERANCE
			and (description in descriptions or (account and row.account_head == account))
		):
			return row
	return None


def append_tax_gl_entry(si, gl_entries, tax, amount, base_amount, extra_values=None):
	account_currency = get_account_currency(tax.account_head)
	gl_values = {
		"account": tax.account_head,
		"against": si.customer,
		"credit": flt(base_amount, tax.precision("tax_amount_after_discount_amount")),
		"credit_in_account_currency": (
			flt(base_amount, tax.precision("base_tax_amount_after_discount_amount"))
			if account_currency == si.company_currency
			else flt(amount, tax.precision("tax_amount_after_discount_amount"))
		),
		"credit_in_transaction_currency": flt(
			amount, tax.precision("tax_amount_after_discount_amount")
		),
		"cost_center": tax.cost_center,
	}
	if extra_values:
		gl_values.update(extra_values)

	gl_entries.append(si.get_gl_dict(gl_values, account_currency, item=tax))


def validate_ra_bill_retention_tax_account(account, company=None):
	account_values = frappe.get_cached_value(
		"Account",
		account,
		["company", "root_type", "account_type", "is_group", "disabled"],
		as_dict=True,
	)
	if not account_values:
		frappe.throw(_("Retention deduction account {0} does not exist.").format(frappe.bold(account)))

	if (
		(company and account_values.company != company)
		or account_values.root_type != "Asset"
		or account_values.account_type
		or cint(account_values.is_group)
		or cint(account_values.disabled)
	):
		frappe.throw(
			_(
				"Retention deduction account {0} must be an enabled posting Asset account "
				"with blank Account Type because "
				"Sales Taxes and Charges rows do not carry party details."
			).format(frappe.bold(account))
		)


def validate_ra_bill_advance_recovery_balance(si, target_amount):
	target_amount = flt(target_amount)
	if target_amount <= AMOUNT_TOLERANCE:
		return None

	ra_bill = None
	if si.meta.has_field("ra_bill") and si.get("ra_bill"):
		ra_bill = frappe.get_doc("RA Bill", si.ra_bill)

	sales_order = get_ra_bill_sales_order_for_invoice(si, ra_bill)
	if not sales_order:
		frappe.throw(_("RA Bill advance recovery requires a linked Sales Order."))

	from construction_management.construction_management.advance_management import (
		get_sales_order_advance_summary,
	)

	summary = get_sales_order_advance_summary(
		sales_order,
		exclude_invoice=si.name if not si.is_new() else None,
	)
	remaining = flt(summary.remaining_advance_balance)
	if target_amount > remaining + AMOUNT_TOLERANCE:
		frappe.throw(
			_(
				"RA Bill advance recovery {0} exceeds remaining advance balance {1} "
				"for Sales Order {2}."
			).format(
				frappe.format_value(target_amount, {"fieldtype": "Currency"}),
				frappe.format_value(remaining, {"fieldtype": "Currency"}),
				sales_order,
			)
		)

	return summary


def get_ra_bill_sales_order_for_invoice(si, ra_bill=None):
	if ra_bill:
		sales_order = ra_bill.get("sales_order")
		if sales_order:
			return sales_order

	if si.get("sales_order"):
		return si.get("sales_order")

	for item in si.get("items") or []:
		if item.get("sales_order"):
			return item.get("sales_order")

	if si.meta.has_field("ra_bill") and si.get("ra_bill"):
		from construction_management.construction_management.advance_management import (
			get_ra_bill_sales_order,
		)

		return get_ra_bill_sales_order(si.get("ra_bill"))

	return None


def is_same_child_row(row, other):
	if not row or not other:
		return False

	if row.get("name") and other.get("name"):
		return row.get("name") == other.get("name")

	return cint(row.get("idx")) == cint(other.get("idx"))


def get_ra_bill_vat_config(si, ra_bill):
	tax_rows = get_authoritative_ra_bill_tax_rows(si, ra_bill)
	vat_row = get_first_vat_row(tax_rows)
	if vat_row:
		return frappe._dict(
			{
				"account_head": vat_row.get("account_head"),
				"description": vat_row.get("description") or vat_row.get("account_head"),
				"rate": flt(vat_row.get("rate")),
				"cost_center": vat_row.get("cost_center"),
			}
		)

	if is_zero_rated_or_exempt(ra_bill):
		return None

	return None


def get_authoritative_ra_bill_tax_rows(si, ra_bill):
	template = get_ra_bill_sales_tax_template(si, ra_bill)
	if template:
		return get_taxes_and_charges("Sales Taxes and Charges Template", template) or []

	if si.get("taxes"):
		return [row.as_dict() for row in si.get("taxes")]

	return [row.as_dict() for row in ra_bill.get("taxes") or []]


def get_ra_bill_sales_tax_template(si, ra_bill):
	template = ra_bill.get("sales_taxes_and_charges_template") or si.get("taxes_and_charges")
	if template:
		return template

	if is_zero_rated_or_exempt(ra_bill):
		return None

	try:
		from erpnext.accounts.party import set_taxes

		return set_taxes(
			ra_bill.get("customer") or si.get("customer"),
			"Customer",
			si.get("posting_date"),
			si.get("company"),
			tax_category=ra_bill.get("tax_category") or si.get("tax_category"),
			billing_address=si.get("customer_address"),
			shipping_address=si.get("shipping_address_name"),
		)
	except Exception:
		pass

	if not si.get("company"):
		return None

	default_template = frappe.db.get_value(
		"Sales Taxes and Charges Template",
		{"is_default": 1, "company": si.company, "disabled": 0},
	)
	if default_template:
		return default_template

	return get_company_vat_5_template(si.company)


def get_company_vat_5_template(company):
	templates = frappe.get_all(
		"Sales Taxes and Charges Template",
		filters={"company": company, "disabled": 0},
		fields=["name"],
		order_by="name asc",
	)
	for template in templates:
		name = (template.name or "").lower()
		if (
			VAT_KEYWORD in name
			and "5" in name
			and not any(keyword in name for keyword in NON_TAXABLE_CATEGORY_KEYWORDS)
		):
			return template.name
	return None


def get_first_vat_row(tax_rows):
	for row in tax_rows or []:
		account = row.get("account_head") or ""
		description = row.get("description") or ""
		rate = flt(row.get("rate"))
		if rate > AMOUNT_TOLERANCE and (
			VAT_KEYWORD in account.lower() or VAT_KEYWORD in description.lower()
		):
			return row
	return None


def is_zero_rated_or_exempt(ra_bill):
	tax_category = (ra_bill.get("tax_category") or "").lower()
	return bool(tax_category) and any(
		keyword in tax_category for keyword in NON_TAXABLE_CATEGORY_KEYWORDS
	)


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
