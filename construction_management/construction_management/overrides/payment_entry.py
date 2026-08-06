import frappe
from frappe import _
from frappe.utils import flt

from erpnext.accounts.party import get_party_account
from erpnext.accounts.utils import get_account_currency

from construction_management.construction_management.accounting_dimensions import (
	apply_ra_bill_cost_center_to_payment_entry,
)
from construction_management.construction_management.utils.accounting import (
	apply_construction_accounts_to_payment_entry,
	apply_party_to_payment_entry,
	get_gl_party_fields,
	get_construction_account,
)


class ConstructionPaymentEntryMixin:
	def validate(self):
		self.sync_subcontract_connection_fields()
		self.validate_project_company()
		apply_construction_accounts_to_payment_entry(self)
		apply_ra_bill_cost_center_to_payment_entry(self)
		self.validate_payment_accounts_exist()
		self.validate_advance_party_account_setup()

		if self.is_retention_payment() and self.docstatus == 0 and getattr(self, "_action", None) != "submit":
			self.setup_party_account_field()
			self.validate_retention_payment(for_submit=False)
			self.set_title()
			return

		super().validate()
		if self.is_retention_payment():
			self.validate_retention_payment(for_submit=getattr(self, "_action", None) == "submit")

	def validate_project_company(self):
		if not self.project or not self.company:
			return

		if not frappe.get_meta("Project").has_field("company"):
			return

		project_company = frappe.db.get_value("Project", self.project, "company")
		if project_company and project_company != self.company:
			frappe.throw(
				_("Payment Entry Company must match Project {0} Company {1}. Current Company is {2}.").format(
					frappe.bold(self.project),
					frappe.bold(project_company),
					frappe.bold(self.company),
				)
			)

	def validate_payment_accounts_exist(self):
		for fieldname in ("paid_from", "paid_to"):
			account = self.get(fieldname)
			if account:
				self.validate_payment_account(account, fieldname)

		for row in self.get("deductions") or []:
			if row.get("account"):
				self.validate_payment_account(row.account, "deductions")

		for row in self.get("taxes") or []:
			if row.get("account_head"):
				self.validate_payment_account(row.account_head, "taxes")

	def validate_payment_account(self, account, fieldname):
		account_values = frappe.db.get_value(
			"Account",
			account,
			["company", "is_group", "disabled", "root_type", "account_type"],
			as_dict=True,
		)
		if not account_values:
			frappe.throw(
				_("Payment Entry account {0} in {1} does not exist. Select an account from the current Project/Company.").format(
					frappe.bold(account),
					frappe.bold(fieldname),
				)
			)

		if account_values.company != self.company:
			frappe.throw(
				_("Payment Entry account {0} belongs to Company {1}, but this Payment Entry is for Company {2}.").format(
					frappe.bold(account),
					frappe.bold(account_values.company),
					frappe.bold(self.company),
				)
			)

		if account_values.is_group or account_values.disabled:
			frappe.throw(
				_("Payment Entry account {0} must be an active ledger account.").format(
					frappe.bold(account)
				)
			)

		if fieldname in ("paid_from", "paid_to") and not account_values.root_type:
			frappe.throw(
				_("Payment Entry account {0} is missing Root Type. Please repair the Account master.").format(
					frappe.bold(account)
				)
			)

	def validate_advance_party_account_setup(self):
		if (
			self.docstatus > 0
			or self.payment_type == "Internal Transfer"
			or self.party_type not in ("Customer", "Supplier")
			or not self.party
			or not self.company
			or not self.references
		):
			return

		allowed_reference_types = {"Sales Order"} if self.party_type == "Customer" else {"Purchase Order"}
		reference_types = {row.reference_doctype for row in self.references if row.reference_doctype}
		if reference_types - allowed_reference_types:
			return

		if not frappe.db.get_value(
			"Company", self.company, "book_advance_payments_in_separate_party_account"
		):
			return

		accounts = get_party_account(self.party_type, self.party, self.company, include_advance=True)
		party_account = accounts[0] if isinstance(accounts, list) and accounts else accounts
		advance_account = accounts[1] if isinstance(accounts, list) and len(accounts) > 1 else None

		if not advance_account:
			return

		if party_account and frappe.db.exists("Account", party_account):
			return

		company_field = (
			"default_receivable_account" if self.party_type == "Customer" else "default_payable_account"
		)
		party_field = "Receivable" if self.party_type == "Customer" else "Payable"
		frappe.throw(
			_(
				"Cannot save this advance Payment Entry because {0} has no valid {1} account for Company {2}. "
				"Set {3} on the {0}, its group, or set {4} in Company {2}."
			).format(
				frappe.bold(self.party),
				frappe.bold(party_field),
				frappe.bold(self.company),
				frappe.bold(party_field),
				frappe.bold(frappe.get_meta("Company").get_label(company_field) or company_field),
			)
		)

	def build_gl_map(self):
		apply_party_to_payment_entry(self)
		gl_entries = super().build_gl_map()
		self.apply_party_to_receivable_payable_gl_entries(gl_entries)
		return gl_entries

	def apply_party_to_receivable_payable_gl_entries(self, gl_entries):
		for gle in gl_entries:
			if not gle.get("account"):
				continue

			party_fields = get_gl_party_fields(
				gle.account,
				transaction=self,
				party_type=self.party_type,
				party=self.party,
			)
			if not party_fields:
				continue

			gle.update(party_fields)

	def add_deductions_gl_entries(self, gl_entries):
		apply_party_to_payment_entry(self)
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
		return get_gl_party_fields(
			deduction.account,
			transaction=self,
			party_type=self.party_type,
			party=self.party,
		)

	def is_retention_payment(self):
		if self.meta.has_field("custom_is_retention_payment") and self.get("custom_is_retention_payment"):
			return True

		return bool(self.get_retention_record_name() or self.get_retention_payable_name())

	def validate_retention_payment(self, for_submit=False):
		if self.get_retention_payable_name():
			return self.validate_retention_payable_payment(for_submit=for_submit)

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

		retention_account = get_construction_account(
			company,
			"retention_receivable",
			project=record.project,
			transaction=self,
		)
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

	def get_retention_payable_name(self):
		for fieldname in ("custom_retention_payable", "retention_payable"):
			if self.meta.has_field(fieldname) and self.get(fieldname):
				return self.get(fieldname)

		return None

	def validate_retention_payable_payment(self, for_submit=False):
		record_name = self.get_retention_payable_name()
		if not record_name:
			frappe.throw(_("Retention Payable is required for a retention Payment Entry."))

		record = frappe.get_doc("Retention Payable", record_name)
		if record.docstatus == 2 or record.status == "Cancelled":
			frappe.throw(_("Cannot release retention against Cancelled Retention Payable {0}.").format(record.name))

		if getattr(record.meta, "is_submittable", False) and record.docstatus != 1:
			frappe.throw(_("Retention Payable {0} must be submitted before releasing retention.").format(record.name))

		if self.payment_type != "Pay":
			frappe.throw(_("Retention Payable Payment Entry must be a Pay entry."))

		if self.party_type != "Supplier":
			frappe.throw(_("Retention Payable Payment Entry must use Party Type Supplier."))

		if self.party != record.supplier:
			frappe.throw(_("Retention Payable Payment Entry Supplier must match Retention Payable {0}.").format(record.name))

		if self.company != record.company:
			frappe.throw(_("Retention Payable Payment Entry Company must match Retention Payable company {0}.").format(record.company))

		retention_account = get_construction_account(
			record.company,
			"subcontractor_retention_payable",
			project=record.project,
			transaction=self,
		)
		if self.paid_to != retention_account:
			frappe.throw(
				_("Paid To must be the Retention Payable account {0}.").format(
					frappe.bold(retention_account)
				)
			)

		if self.get("deductions"):
			frappe.throw(_("Retention payable Payment Entry cannot have deduction rows."))

		release_amount = flt(self.paid_amount)
		if release_amount <= 0:
			frappe.throw(_("Retention release amount must be greater than zero."))

		remaining_amount = self.get_remaining_retention_payable_amount(record)
		if release_amount > remaining_amount + 0.0001:
			frappe.throw(
				_("Retention release amount {0} cannot exceed remaining retention {1} for {2}.").format(
					release_amount,
					remaining_amount,
					record.name,
				)
			)

		if self.paid_from:
			if self.paid_from == self.paid_to:
				frappe.throw(_("Paid From and Paid To cannot be the same account."))
		elif for_submit:
			frappe.throw(_("Paid From is required before submitting a retention payable Payment Entry."))

		self.set_retention_payable_marker_values(record, retention_account, release_amount)

	def get_remaining_retention_payable_amount(self, record):
		submitted_amount = 0
		seen_payment_entries = set()
		meta = frappe.get_meta("Payment Entry")
		for fieldname in ("custom_retention_payable", "retention_payable"):
			if not meta.has_field(fieldname):
				continue

			filters = {"docstatus": 1, fieldname: record.name}

			for row in frappe.get_all("Payment Entry", filters=filters, fields=["name", "paid_amount"]):
				if row.name == self.name or row.name in seen_payment_entries:
					continue

				seen_payment_entries.add(row.name)
				submitted_amount += flt(row.paid_amount)

		return max(0, flt(record.retention_amount) - submitted_amount)

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

	def set_retention_payable_marker_values(self, record, retention_account, release_amount):
		self.set_if_meta_has_field("custom_is_retention_payment", 1)
		self.set_if_meta_has_field("retention_payable", record.name)
		self.set_if_meta_has_field("custom_retention_payable", record.name)
		self.set_if_meta_has_field("purchase_invoice", record.purchase_invoice)
		self.set_if_meta_has_field("sc_bill", record.sc_bill)
		self.set_if_meta_has_field("sc_work_order", record.sc_work_order)
		self.set_if_meta_has_field("custom_original_purchase_invoice", record.purchase_invoice)
		self.set_if_meta_has_field("custom_sc_bill", record.sc_bill)
		self.set_if_meta_has_field("custom_retention_release_amount", release_amount)
		self.set_if_meta_has_field("custom_retention_payable_account", retention_account)
		if record.sc_bill and self.meta.has_field("purchase_order"):
			self.purchase_order = frappe.db.get_value("SC Bill", record.sc_bill, "purchase_order")

	def set_if_meta_has_field(self, fieldname, value):
		if self.meta.has_field(fieldname):
			self.set(fieldname, value)

	def sync_subcontract_connection_fields(self):
		from construction_management.construction_management.setup import (
			get_payment_entry_subcontract_link_values,
		)

		values = get_payment_entry_subcontract_link_values(self)
		for fieldname, value in values.items():
			if value and self.meta.has_field(fieldname):
				self.set(fieldname, value)
