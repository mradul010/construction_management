import frappe
from frappe import _
from frappe.utils import flt

from erpnext.accounts.doctype.payment_entry.payment_entry import PaymentEntry
from erpnext.accounts.utils import get_account_currency

from construction_management.construction_management.accounting_dimensions import (
	apply_ra_bill_cost_center_to_payment_entry,
)
from construction_management.construction_management.retention_payment import (
	get_or_create_retention_receivable_account,
)


PARTY_TYPE_BY_ACCOUNT_TYPE = {
	"Receivable": "Customer",
	"Payable": "Supplier",
}


class ConstructionPaymentEntry(PaymentEntry):
	def validate(self):
		apply_ra_bill_cost_center_to_payment_entry(self)

		if self.is_retention_payment() and self.docstatus == 0 and getattr(self, "_action", None) != "submit":
			self.setup_party_account_field()
			self.validate_retention_payment(for_submit=False)
			self.set_title()
			return

		super().validate()
		if self.is_retention_payment():
			self.validate_retention_payment(for_submit=getattr(self, "_action", None) == "submit")

	def add_deductions_gl_entries(self, gl_entries):
		for d in self.get("deductions"):
			if not d.amount:
				continue

			account_currency = get_account_currency(d.account)
			if account_currency != self.company_currency:
				frappe.throw(_("Currency for {0} must be {1}").format(d.account, self.company_currency))

			gl_dict = {
				"account": d.account,
				"account_currency": account_currency,
				"against": self.party or self.paid_from,
				"debit_in_account_currency": d.amount,
				"debit_in_transaction_currency": d.amount / self.transaction_exchange_rate,
				"debit": d.amount,
				"cost_center": d.cost_center,
				"project": self.project,
			}
			gl_dict.update(self.get_deduction_party_fields(d))

			gl_entries.append(
				self.get_gl_dict(
					gl_dict,
					item=d,
				)
			)

	def get_deduction_party_fields(self, deduction):
		account_type = frappe.get_cached_value("Account", deduction.account, "account_type")
		required_party_type = PARTY_TYPE_BY_ACCOUNT_TYPE.get(account_type)
		if not required_party_type:
			return {}

		if self.party_type != required_party_type:
			frappe.throw(
				_(
					"Row {0}: {1} account {2} requires Party Type {3}, but Payment Entry has Party Type {4}."
				).format(
					deduction.idx,
					account_type,
					frappe.bold(deduction.account),
					frappe.bold(required_party_type),
					frappe.bold(self.party_type or _("Not Set")),
				)
			)

		if not self.party:
			frappe.throw(
				_("Row {0}: Party is required to post deduction against {1} account {2}.").format(
					deduction.idx,
					account_type,
					frappe.bold(deduction.account),
				)
			)

		return {
			"party_type": required_party_type,
			"party": self.party,
		}

	def is_retention_payment(self):
		if self.meta.has_field("custom_is_retention_payment") and self.get("custom_is_retention_payment"):
			return True

		return bool(self.get_retention_record_name())

	def validate_retention_payment(self, for_submit=False):
		record_name = self.get_retention_record_name()
		if not record_name:
			frappe.throw(_("Retention Record is required for a retention Payment Entry."))

		record = frappe.get_doc("Retention Record", record_name)
		if record.docstatus == 2 or record.status == "Cancelled":
			frappe.throw(_("Cannot receive retention against Cancelled Retention Record {0}.").format(record.name))

		if getattr(record.meta, "is_submittable", False) and record.docstatus != 1:
			frappe.throw(_("Retention Record {0} must be submitted before receiving retention.").format(record.name))

		if self.payment_type != "Receive":
			frappe.throw(_("Retention Payment Entry must be a Receive entry."))

		if self.party_type != "Customer":
			frappe.throw(_("Retention Payment Entry must use Party Type Customer."))

		if self.party != record.customer:
			frappe.throw(_("Retention Payment Entry Customer must match Retention Record {0}.").format(record.name))

		company = self.get_retention_record_company(record)
		if self.company != company:
			frappe.throw(_("Retention Payment Entry Company must match Retention Record company {0}.").format(company))

		retention_account = get_or_create_retention_receivable_account(company)
		if self.paid_from != retention_account:
			frappe.throw(
				_("Paid From must be the Retention Receivable account {0}.").format(
					frappe.bold(retention_account)
				)
			)

		if self.get("deductions"):
			frappe.throw(_("Retention release Payment Entry cannot have deduction rows."))

		release_amount = flt(self.paid_amount)
		if release_amount <= 0:
			frappe.throw(_("Retention release amount must be greater than zero."))

		remaining_amount = self.get_remaining_retention_amount(record)
		if release_amount > remaining_amount + 0.0001:
			frappe.throw(
				_("Retention release amount {0} cannot exceed remaining retention {1} for {2}.").format(
					release_amount,
					remaining_amount,
					record.name,
				)
			)

		if self.paid_to:
			self.validate_retention_paid_to_account()
			if self.paid_from == self.paid_to:
				frappe.throw(_("Paid From and Paid To cannot be the same account."))
		elif for_submit:
			frappe.throw(_("Paid To is required before submitting a retention Payment Entry."))

		self.set_retention_marker_values(record, retention_account, release_amount)

	def get_retention_record_name(self):
		for fieldname in ("custom_retention_record", "retention_record"):
			if self.meta.has_field(fieldname) and self.get(fieldname):
				return self.get(fieldname)

		return None

	def get_retention_record_company(self, record):
		for doctype, fieldname in (("Sales Invoice", "sales_invoice"), ("RA Bill", "ra_bill")):
			document_name = record.get(fieldname)
			if document_name:
				company = frappe.db.get_value(doctype, document_name, "company")
				if company:
					return company

		if record.project and frappe.get_meta("Project").has_field("company"):
			company = frappe.db.get_value("Project", record.project, "company")
			if company:
				return company

		return self.company

	def get_remaining_retention_amount(self, record):
		submitted_amount = 0
		seen_payment_entries = set()
		meta = frappe.get_meta("Payment Entry")
		for fieldname in ("custom_retention_record", "retention_record"):
			if not meta.has_field(fieldname):
				continue

			filters = {"docstatus": 1, fieldname: record.name}

			for row in frappe.get_all("Payment Entry", filters=filters, fields=["name", "paid_amount"]):
				if row.name == self.name or row.name in seen_payment_entries:
					continue

				seen_payment_entries.add(row.name)
				submitted_amount += flt(row.paid_amount)

		return max(0, flt(record.retention_amount) - submitted_amount)

	def validate_retention_paid_to_account(self):
		account = frappe.db.get_value(
			"Account",
			self.paid_to,
			["name", "is_group", "disabled", "account_type", "root_type", "company"],
			as_dict=True,
		)
		if not account:
			frappe.throw(_("Paid To account {0} does not exist.").format(self.paid_to))

		if account.is_group or account.disabled:
			frappe.throw(_("Paid To account must be an enabled non-group account."))

		if account.company != self.company:
			frappe.throw(_("Paid To account must belong to company {0}.").format(self.company))

		if account.account_type not in ("Bank", "Cash") and account.root_type != "Asset":
			frappe.throw(_("Paid To account must be a Bank, Cash, or Asset account."))

	def set_retention_marker_values(self, record, retention_account, release_amount):
		self.set_if_meta_has_field("custom_is_retention_payment", 1)
		self.set_if_meta_has_field("custom_retention_record", record.name)
		self.set_if_meta_has_field("custom_original_sales_invoice", record.sales_invoice)
		self.set_if_meta_has_field("custom_ra_bill", record.ra_bill)
		self.set_if_meta_has_field("custom_retention_release_amount", release_amount)
		self.set_if_meta_has_field("custom_retention_receivable_account", retention_account)
		self.set_if_meta_has_field("retention_record", record.name)

	def set_if_meta_has_field(self, fieldname, value):
		if self.meta.has_field(fieldname):
			self.set(fieldname, value)
