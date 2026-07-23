import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today

from construction_management.construction_management.utils.accounting import get_construction_account


AMOUNT_TOLERANCE = 0.0001
CANCEL_REMARK = "Cancelled because Purchase Invoice was cancelled"


class RetentionPayable(Document):
	def validate(self):
		self._sync_and_validate_sc_bill_links()
		self._validate_amounts()
		self._set_balance_and_status()

	def _sync_and_validate_sc_bill_links(self):
		if not self.sc_bill:
			return

		expected = get_sc_bill_reference_values(self.sc_bill)
		if not expected:
			frappe.throw(_("SC Bill {0} does not exist.").format(self.sc_bill))

		for fieldname, label in (
			("company", _("Company")),
			("project", _("Project")),
			("supplier", _("Supplier")),
			("sc_work_order", _("SC Work Order")),
		):
			expected_value = expected.get(fieldname)
			if not expected_value:
				continue

			current_value = self.get(fieldname)
			if current_value and current_value != expected_value:
				frappe.throw(
					_("Retention Payable {0} must match the {0} linked to SC Bill {1}.").format(
						label,
						self.sc_bill,
					)
				)
			if not current_value:
				self.set(fieldname, expected_value)

		if not self.company_currency and self.company:
			self.company_currency = frappe.get_cached_value("Company", self.company, "default_currency")

	def _validate_amounts(self):
		for fieldname, label in (
			("gross_amount", _("Gross Amount")),
			("retention_amount", _("Retention Amount")),
			("released_amount", _("Released Amount")),
			("paid_amount", _("Paid Amount")),
			("outstanding_amount", _("Outstanding Amount")),
		):
			if flt(self.get(fieldname)) < 0:
				frappe.throw(_("{0} cannot be negative.").format(label))

		if flt(self.released_amount) > flt(self.retention_amount) + AMOUNT_TOLERANCE:
			frappe.throw(_("Released Amount cannot be greater than Retention Amount."))

	def _set_balance_and_status(self):
		retention_amount = flt(self.retention_amount)
		released_amount = flt(self.released_amount)
		paid_amount = flt(self.paid_amount)

		if paid_amount and not released_amount:
			released_amount = paid_amount

		self.gross_amount = flt(self.gross_amount)
		self.retention_amount = retention_amount
		self.released_amount = released_amount
		self.paid_amount = paid_amount
		self.outstanding_amount = flt(self.outstanding_amount)
		self.balance_amount = max(0, retention_amount - released_amount)

		if self.status == "Cancelled":
			return

		self.status = _get_retention_status(released_amount, retention_amount)

	@frappe.whitelist()
	def release_retention(self):
		return self.make_payment_entry()

	@frappe.whitelist()
	def make_payment_entry(self):
		if self.status == "Cancelled":
			frappe.throw(_("Cannot create a Payment Entry for a Cancelled Retention Payable."))

		release_amount = flt(self.balance_amount)
		if release_amount <= AMOUNT_TOLERANCE:
			frappe.throw(_("No remaining retention balance is available for payment."))

		if not self.supplier:
			frappe.throw(_("Supplier is required to release retention."))
		if not self.company:
			frappe.throw(_("Company is required to release retention."))

		retention_account = get_construction_account(
			self.company,
			"subcontractor_retention_payable",
			project=self.project,
			transaction=self,
		)
		existing_payment_entry = _get_open_retention_payable_payment_entry(self.name)
		if existing_payment_entry:
			frappe.msgprint(
				_("Draft Payment Entry {0} already exists for this Retention Payable.").format(
					frappe.bold(existing_payment_entry)
				)
			)
			return existing_payment_entry

		bank_account = _get_retention_payable_bank_account(self.company, self.supplier)
		retention_account_currency = frappe.get_cached_value("Account", retention_account, "account_currency")

		payment_entry = frappe.new_doc("Payment Entry")
		payment_entry.flags.ignore_permissions = True
		payment_entry.flags.ignore_mandatory = True
		payment_entry.payment_type = "Pay"
		payment_entry.company = self.company
		payment_entry.posting_date = today()
		payment_entry.party_type = "Supplier"
		payment_entry.party = self.supplier
		if bank_account:
			payment_entry.paid_from = bank_account
			payment_entry.paid_from_account_currency = frappe.get_cached_value(
				"Account",
				bank_account,
				"account_currency",
			)
		payment_entry.paid_to = retention_account
		payment_entry.paid_to_account_currency = retention_account_currency
		payment_entry.paid_amount = release_amount
		payment_entry.received_amount = release_amount
		payment_entry.target_exchange_rate = 1
		if self.project:
			payment_entry.project = self.project

		_set_if_meta_has_field(payment_entry, "custom_is_retention_payment", 1)
		_set_if_meta_has_field(payment_entry, "retention_payable", self.name)
		_set_if_meta_has_field(payment_entry, "custom_retention_payable", self.name)
		_set_if_meta_has_field(payment_entry, "custom_sc_bill", self.sc_bill)
		_set_if_meta_has_field(payment_entry, "custom_original_purchase_invoice", self.purchase_invoice)
		_set_if_meta_has_field(payment_entry, "custom_retention_release_amount", release_amount)
		_set_if_meta_has_field(payment_entry, "custom_retention_payable_account", retention_account)
		payment_entry.remarks = _("Retention Release against Retention Payable {0}").format(self.name)

		if hasattr(payment_entry, "setup_party_account_field"):
			payment_entry.setup_party_account_field()

		payment_entry.insert(ignore_permissions=True, ignore_mandatory=True)
		frappe.msgprint(
			_("Draft Payment Entry {0} has been created for retention release.").format(
				frappe.bold(payment_entry.name)
			)
		)
		return payment_entry.name

	@frappe.whitelist()
	def cancel_retention_payable(self):
		if self.status == "Cancelled":
			return self.name

		self.status = "Cancelled"
		self.remarks = _append_remark(self.remarks, "Cancelled from Retention Payable form")
		self.save(ignore_permissions=True)
		return self.name


def sync_from_sc_bill(sc_bill, purchase_invoice=None):
	if flt(sc_bill.retention_amount) <= AMOUNT_TOLERANCE:
		return None

	record_name = frappe.db.get_value("Retention Payable", {"sc_bill": sc_bill.name}, "name")
	if record_name:
		record = frappe.get_doc("Retention Payable", record_name)
	else:
		record = frappe.new_doc("Retention Payable")
		record.sc_bill = sc_bill.name
		record.released_amount = 0

	record.company = sc_bill.company
	record.project = sc_bill.project
	record.supplier = sc_bill.supplier
	record.sc_work_order = sc_bill.sc_work_order
	record.purchase_invoice = purchase_invoice or sc_bill.purchase_invoice
	record.posting_date = sc_bill.billing_period_to or today()
	record.company_currency = frappe.get_cached_value("Company", sc_bill.company, "default_currency")
	record.retention_percent = sc_bill.retention_percent
	record.gross_amount = sc_bill.gross_amount
	record.retention_amount = sc_bill.retention_amount

	if record_name:
		record.save(ignore_permissions=True)
	else:
		record.insert(ignore_permissions=True)

	if purchase_invoice and frappe.get_meta("Purchase Invoice").has_field("retention_payable"):
		frappe.db.set_value("Purchase Invoice", purchase_invoice, "retention_payable", record.name, update_modified=False)

	return record.name


def set_purchase_invoice_for_sc_bill(sc_bill, purchase_invoice):
	record_name = frappe.db.get_value("Retention Payable", {"sc_bill": sc_bill.name}, "name")
	if not record_name:
		return sync_from_sc_bill(sc_bill, purchase_invoice=purchase_invoice)

	frappe.db.set_value(
		"Retention Payable",
		record_name,
		{"purchase_invoice": purchase_invoice},
		update_modified=True,
	)
	if frappe.get_meta("Purchase Invoice").has_field("retention_payable"):
		frappe.db.set_value("Purchase Invoice", purchase_invoice, "retention_payable", record_name, update_modified=False)
	return record_name


def validate_purchase_invoice_references(invoice, method=None):
	if not invoice or not invoice.meta.has_field("sc_bill") or not invoice.get("sc_bill"):
		return

	expected = get_sc_bill_reference_values(invoice.sc_bill)
	if not expected:
		frappe.throw(_("SC Bill {0} does not exist.").format(invoice.sc_bill))

	_validate_invoice_field(invoice, "supplier", expected.supplier, _("Supplier"))
	_validate_invoice_field(invoice, "company", expected.company, _("Company"))
	_validate_invoice_field(invoice, "project", expected.project, _("Project"))
	_validate_invoice_field(invoice, "sc_work_order", expected.sc_work_order, _("SC Work Order"))


def on_purchase_invoice_submit(doc, method=None):
	sync_from_purchase_invoice(doc)


def on_purchase_invoice_cancel(doc, method=None):
	sync_from_purchase_invoice(doc)


def on_purchase_invoice_update_after_submit(doc, method=None):
	sync_from_purchase_invoice(doc)


def sync_from_purchase_invoice(invoice):
	if not invoice or not invoice.meta.has_field("sc_bill") or not invoice.get("sc_bill"):
		return None

	if invoice.docstatus == 2:
		return mark_cancelled_from_purchase_invoice(invoice)

	sc_bill = frappe.get_doc("SC Bill", invoice.sc_bill)
	return sync_from_sc_bill(sc_bill, purchase_invoice=invoice.name)


def mark_cancelled_from_purchase_invoice(invoice):
	record_name = None
	if invoice.meta.has_field("retention_payable") and invoice.get("retention_payable"):
		record_name = invoice.retention_payable
	if not record_name and invoice.meta.has_field("sc_bill") and invoice.get("sc_bill"):
		record_name = frappe.db.get_value("Retention Payable", {"sc_bill": invoice.sc_bill}, "name")
	if not record_name:
		return None

	record = frappe.get_doc("Retention Payable", record_name)
	record.status = "Cancelled"
	record.remarks = _append_remark(record.remarks, CANCEL_REMARK)
	record.save(ignore_permissions=True)
	return record.name


def sync_from_payment_entry(payment_entry):
	if not _is_retention_payable_payment(payment_entry):
		return None

	record_name = _get_payment_entry_retention_payable(payment_entry)
	if not record_name:
		return None

	record = frappe.get_doc("Retention Payable", record_name)
	released_amount = min(
		_get_total_retention_payable_payments(payment_entry.company, record.name),
		flt(record.retention_amount),
	)
	_update_retention_payable_release_status(record, released_amount, payment_entry=payment_entry)
	return record.name


def _is_retention_payable_payment(payment_entry):
	if not payment_entry or payment_entry.payment_type != "Pay" or payment_entry.party_type != "Supplier":
		return False

	if _get_payment_entry_retention_payable(payment_entry):
		return True

	if payment_entry.meta.has_field("custom_retention_payable_account") and payment_entry.get("custom_retention_payable_account"):
		return payment_entry.paid_to == payment_entry.get("custom_retention_payable_account")

	return False


def _update_retention_payable_release_status(record, released_amount, payment_entry=None):
	retention_amount = flt(record.retention_amount)
	released_amount = min(flt(released_amount), retention_amount)
	record.paid_amount = released_amount
	record.released_amount = released_amount
	record.outstanding_amount = max(0, retention_amount - released_amount)
	record.balance_amount = max(0, retention_amount - released_amount)
	record.status = _get_retention_status(released_amount, retention_amount)
	if payment_entry and payment_entry.docstatus == 1:
		record.last_payment_entry = payment_entry.name
	if record.status == "Released" and not record.release_date:
		record.release_date = getattr(payment_entry, "posting_date", None) or today()
	elif record.status != "Released":
		record.release_date = None
	record.save(ignore_permissions=True)


def _get_total_retention_payable_payments(company, record_name):
	total = 0
	seen = set()
	base_filters = {
		"docstatus": 1,
		"payment_type": "Pay",
		"party_type": "Supplier",
		"company": company,
	}
	for fieldname in _get_payment_entry_retention_payable_fields():
		filters = base_filters.copy()
		filters[fieldname] = record_name
		for row in frappe.get_all("Payment Entry", filters=filters, fields=["name", "paid_amount"]):
			if row.name in seen:
				continue
			seen.add(row.name)
			total += flt(row.paid_amount)
	return total


def get_sc_bill_reference_values(sc_bill):
	if not sc_bill:
		return frappe._dict()

	return frappe.db.get_value(
		"SC Bill",
		sc_bill,
		["name", "company", "project", "supplier", "sc_work_order", "purchase_invoice"],
		as_dict=True,
	) or frappe._dict()


def _validate_invoice_field(invoice, fieldname, expected_value, label):
	if not expected_value or not invoice.meta.has_field(fieldname):
		return

	current_value = invoice.get(fieldname)
	if current_value and current_value != expected_value:
		frappe.throw(_("Purchase Invoice {0} must match the source document {0}.").format(label))
	if not current_value:
		invoice.set(fieldname, expected_value)


def _get_open_retention_payable_payment_entry(record_name):
	field = _get_payment_entry_retention_payable_field()
	if not field:
		return None
	return frappe.db.get_value("Payment Entry", {field: record_name, "docstatus": 0}, "name", order_by="modified desc")


def _get_payment_entry_retention_payable(payment_entry):
	if not payment_entry:
		return None

	for fieldname in ("custom_retention_payable", "retention_payable"):
		if payment_entry.meta.has_field(fieldname) and payment_entry.get(fieldname):
			return payment_entry.get(fieldname)
	return None


def _get_payment_entry_retention_payable_field():
	fields = _get_payment_entry_retention_payable_fields()
	return fields[0] if fields else None


def _get_payment_entry_retention_payable_fields():
	meta = frappe.get_meta("Payment Entry")
	return [
		fieldname
		for fieldname in ("custom_retention_payable", "retention_payable")
		if meta.has_field(fieldname)
	]


def _get_retention_payable_bank_account(company, supplier):
	from construction_management.construction_management.utils.accounting import get_default_company_bank_account

	return get_default_company_bank_account(company)


def _set_if_meta_has_field(doc, fieldname, value):
	if doc.meta.has_field(fieldname) and value not in (None, ""):
		doc.set(fieldname, value)


def _get_retention_status(released_amount, retention_amount):
	released_amount = flt(released_amount)
	retention_amount = flt(retention_amount)
	if released_amount <= 0:
		return "Held"
	if released_amount < retention_amount:
		return "Partially Released"
	return "Released"


def _append_remark(existing, message):
	if not existing:
		return message
	return f"{existing}\n{message}"
