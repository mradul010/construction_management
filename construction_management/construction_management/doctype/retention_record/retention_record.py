import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, getdate, today

from construction_management.construction_management.utils.accounting import get_construction_account
from construction_management.construction_management.accounting_dimensions import (
	get_ra_bill_project_cost_center,
)


AMOUNT_TOLERANCE = 0.0001
CANCEL_REMARK = "Cancelled because RA Bill was cancelled"


class RetentionRecord(Document):
	def validate(self):
		self._sync_and_validate_ra_bill_links()
		self._validate_amounts()
		self._set_balance_and_status()

	def _sync_and_validate_ra_bill_links(self):
		if not self.ra_bill:
			return

		expected = get_ra_bill_reference_values(self.ra_bill)
		if not expected:
			frappe.throw(_("RA Bill {0} does not exist.").format(self.ra_bill))

		for fieldname, label in (
			("customer", _("Customer")),
			("project", _("Project")),
			("boq", _("BOQ")),
			("sales_order", _("Sales Order")),
		):
			expected_value = expected.get(fieldname)
			if not expected_value:
				continue

			current_value = self.get(fieldname)
			if current_value and current_value != expected_value:
				if fieldname == "sales_order":
					frappe.throw(
						_("Retention Record Sales Order must match the Sales Order linked to RA Bill {0}.").format(
							self.ra_bill
						)
					)
				frappe.throw(
					_("Retention Record {0} must match the {0} linked to RA Bill {1}.").format(
						label,
						self.ra_bill,
					)
				)
			if not current_value:
				self.set(fieldname, expected_value)

	def _validate_amounts(self):
		if flt(self.gross_amount) < 0:
			frappe.throw(_("Gross Amount cannot be negative."))

		if flt(self.retention_amount) < 0:
			frappe.throw(_("Retention Amount cannot be negative."))

		if flt(self.released_amount) < 0:
			frappe.throw(_("Released Amount cannot be negative."))

		if flt(self.paid_amount) < 0:
			frappe.throw(_("Paid Amount cannot be negative."))

		if flt(self.outstanding_amount) < 0:
			frappe.throw(_("Outstanding Amount cannot be negative."))

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

		if released_amount <= 0:
			self.status = "Held"
		elif released_amount < retention_amount:
			self.status = "Partially Released"
		else:
			self.status = "Released"

	@frappe.whitelist()
	def create_sales_invoice(self):
		frappe.throw(
			_(
				"Retention release is now recorded directly through a Payment Entry against Retention Receivable. "
				"Please use Create Payment Entry."
			)
		)

		if not flt(self.retention_amount):
			frappe.throw(_("Retention Amount must be greater than 0 to create a Sales Invoice."))

		if flt(self.balance_amount) <= 0:
			frappe.throw(_("No remaining retention balance is available to invoice."))

		if self.retention_release_invoice:
			existing_invoice = frappe.db.get_value(
				"Sales Invoice",
				self.retention_release_invoice,
				["name", "docstatus"],
				as_dict=True,
			)
			if existing_invoice and existing_invoice.docstatus != 2:
				frappe.throw(
					_("A retention release invoice already exists: {0}").format(
						existing_invoice.name
					)
				)

		if not self.project:
			frappe.throw(_("Project is required to create a Sales Invoice."))

		company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
		if not company:
			frappe.throw(_("Please set the default Company before creating a Sales Invoice."))

		customer = self.customer
		if not customer or not frappe.db.exists("Customer", customer):
			frappe.throw(_("Customer {0} does not exist.").format(customer or ""))

		item_code = _ensure_retention_release_item(company)
		income_account = get_construction_account(
			company,
			"ra_bill_income",
			project=self.project,
			transaction=self,
		)
		company_currency = frappe.get_cached_value("Company", company, "default_currency")
		ra_bill_doc = None
		if self.ra_bill and frappe.db.exists("RA Bill", self.ra_bill):
			ra_bill_doc = frappe.get_doc("RA Bill", self.ra_bill)
		self._sync_and_validate_ra_bill_links()
		sales_order = get_retention_record_sales_order(self)
		currency = (
			getattr(ra_bill_doc, "currency", None)
			or company_currency
			or frappe.defaults.get_global_default("currency")
		)
		remarks = f"Retention Release against RA Bill {self.ra_bill}"

		invoice = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"customer": customer,
				"company": company,
				"project": self.project,
				"currency": currency,
				"posting_date": today(),
				"due_date": add_days(today(), 15),
				"remarks": remarks,
				"items": [
					{
						"item_code": item_code,
						"item_name": "Retention Release",
						"description": remarks,
						"qty": 1,
						"rate": self.balance_amount,
						"amount": self.balance_amount,
						"uom": "Nos",
						"income_account": income_account,
					}
				],
			}
		)
		if invoice.meta.has_field("retention_record") and self.name:
			invoice.retention_record = self.name
		if invoice.meta.has_field("ra_bill") and self.ra_bill:
			invoice.ra_bill = self.ra_bill
		if invoice.meta.has_field("boq") and self.boq:
			invoice.boq = self.boq
		if invoice.meta.has_field("project") and self.project:
			invoice.project = self.project
		if invoice.meta.has_field("sales_order") and sales_order:
			invoice.sales_order = sales_order
		validate_sales_invoice_references(invoice)
		invoice.set_missing_values()
		if hasattr(invoice, "calculate_taxes_and_totals"):
			invoice.calculate_taxes_and_totals()
		invoice.insert(ignore_permissions=True)

		self.retention_release_invoice = invoice.name
		self.invoice_date = today()
		if self.meta.has_field("release_invoice_date"):
			self.release_invoice_date = today()
		self.invoice_status = "Draft"
		self.paid_amount = 0
		self.outstanding_amount = flt(invoice.grand_total)
		self.save(ignore_permissions=True)
		return invoice.name

	@frappe.whitelist()
	def create_retention_invoice(self):
		return self.create_sales_invoice()

	@frappe.whitelist()
	def sync_status_from_sales_invoice(self):
		if not self.retention_release_invoice:
			frappe.throw(_("No retention release invoice exists to sync from."))

		invoice = frappe.get_doc("Sales Invoice", self.retention_release_invoice)
		sync_from_sales_invoice(invoice)
		return self.name

	@frappe.whitelist()
	def cancel_retention_record(self):
		if self.status == "Cancelled":
			return self.name

		self.status = "Cancelled"
		self.remarks = _append_remark(self.remarks, "Cancelled from Retention Record form")
		self.save(ignore_permissions=True)
		return self.name

	@frappe.whitelist()
	def receive_retention(self):
		return self.make_payment_entry()

	@frappe.whitelist()
	def make_payment_entry(self):
		if self.status == "Cancelled":
			frappe.throw(_("Cannot create a Payment Entry for a Cancelled Retention Record."))

		release_amount = flt(self.balance_amount)
		if release_amount <= AMOUNT_TOLERANCE:
			frappe.throw(_("No remaining retention balance is available for payment."))

		if not self.customer:
			frappe.throw(_("Customer is required to receive retention."))

		company = _get_retention_payment_company(self)
		if not company:
			frappe.throw(_("Company is required to receive retention."))

		retention_account = get_construction_account(
			company,
			"retention_receivable",
			project=self.project,
			transaction=self,
		)
		existing_payment_entry = _get_open_retention_payment_entry(self.name)
		if existing_payment_entry:
			frappe.msgprint(
				_("Draft Payment Entry {0} already exists for this Retention Record.").format(
					frappe.bold(existing_payment_entry)
				)
			)
			return existing_payment_entry

		receipt_account = (
			get_construction_account(
				company,
				"construction_receipt",
				project=self.project,
				transaction=self,
			)
			or _get_retention_release_bank_account(company, self.customer)
		)
		retention_account_currency = frappe.get_cached_value(
			"Account",
			retention_account,
			"account_currency",
		)

		payment_entry = frappe.new_doc("Payment Entry")
		payment_entry.flags.ignore_permissions = True
		payment_entry.flags.ignore_mandatory = True
		payment_entry.payment_type = "Receive"
		payment_entry.company = company
		payment_entry.posting_date = today()
		payment_entry.party_type = "Customer"
		payment_entry.party = self.customer
		payment_entry.paid_from = retention_account
		payment_entry.paid_from_account_currency = retention_account_currency
		if receipt_account:
			payment_entry.paid_to = receipt_account
			payment_entry.paid_to_account_currency = frappe.get_cached_value(
				"Account",
				receipt_account,
				"account_currency",
			)
		payment_entry.paid_amount = release_amount
		payment_entry.received_amount = release_amount
		payment_entry.cost_center = get_ra_bill_project_cost_center(
			self.ra_bill,
			project=self.project,
			company=company,
		)
		if self.project:
			payment_entry.project = self.project
		_set_if_meta_has_field(payment_entry, "custom_is_retention_payment", 1)
		_set_if_meta_has_field(payment_entry, "custom_retention_record", self.name)
		_set_if_meta_has_field(payment_entry, "custom_original_sales_invoice", self.sales_invoice)
		_set_if_meta_has_field(payment_entry, "custom_ra_bill", self.ra_bill)
		_set_if_meta_has_field(payment_entry, "custom_retention_release_amount", release_amount)
		_set_if_meta_has_field(payment_entry, "custom_retention_receivable_account", retention_account)
		if payment_entry.meta.has_field("retention_record"):
			payment_entry.retention_record = self.name
		payment_entry.remarks = _("Retention Release against Retention Record {0}").format(self.name)

		if hasattr(payment_entry, "setup_party_account_field"):
			payment_entry.setup_party_account_field()

		payment_entry.insert(ignore_permissions=True, ignore_mandatory=True)
		frappe.msgprint(
			_("Draft Payment Entry {0} has been created for retention receipt.").format(
				frappe.bold(payment_entry.name)
			)
		)
		return payment_entry.name


@frappe.whitelist()
def create_sales_invoice_for_retention_records(retention_records):
	frappe.throw(
		_(
			"Retention release is now recorded directly through Payment Entry against Retention Receivable."
		)
	)

	names = _parse_retention_record_names(retention_records)
	records = _get_retention_records_for_invoice(names)
	_validate_retention_records_for_invoice(records)

	company = _get_retention_invoice_company(records)
	if not company:
		frappe.throw(_("Please set the default Company before creating a Sales Invoice."))

	customer = records[0].customer
	project = records[0].project
	sales_order = get_retention_record_sales_order(records[0])
	if not customer or not frappe.db.exists("Customer", customer):
		frappe.throw(_("Customer {0} does not exist.").format(customer or ""))

	currency = _get_retention_invoice_currency(records, company)
	item_code = _ensure_retention_release_item(company)
	income_account = get_construction_account(company, "ra_bill_income", project=project)
	remarks = _("Retention Release for selected Retention Records: {0}").format(
		", ".join(record.name for record in records)
	)

	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": customer,
			"company": company,
			"project": project,
			"currency": currency,
			"posting_date": today(),
			"due_date": add_days(today(), 15),
			"remarks": remarks,
		}
	)

	_set_if_meta_has_field(invoice, "project", project)
	_set_if_meta_has_field(invoice, "sales_order", sales_order)
	if len(records) == 1:
		_set_if_meta_has_field(invoice, "retention_record", records[0].name)
		_set_if_meta_has_field(invoice, "ra_bill", records[0].ra_bill)
		_set_if_meta_has_field(invoice, "boq", records[0].boq)

	item_meta = frappe.get_meta("Sales Invoice Item")
	for record in records:
		release_amount = flt(record.balance_amount)
		item_data = {
			"item_code": item_code,
			"item_name": "Retention Release",
			"description": _get_retention_invoice_item_description(record),
			"qty": 1,
			"rate": release_amount,
			"amount": release_amount,
			"uom": "Nos",
			"income_account": income_account,
			"project": record.project,
		}
		invoice.append(
			"items",
			{
				fieldname: value
				for fieldname, value in item_data.items()
				if item_meta.has_field(fieldname) and value not in (None, "")
			},
		)

	if len(records) > 1 and invoice.meta.has_field("retention_records"):
		retention_reference_meta = frappe.get_meta("Sales Invoice Retention Reference")
		for record in records:
			reference_data = {
				"retention_record": record.name,
				"ra_bill": record.ra_bill,
				"boq": record.boq,
				"sales_order": get_retention_record_sales_order(record),
				"project": record.project,
				"retention_amount": record.retention_amount,
				"balance_amount": record.balance_amount,
			}
			invoice.append(
				"retention_records",
				{
					fieldname: value
					for fieldname, value in reference_data.items()
					if retention_reference_meta.has_field(fieldname) and value not in (None, "")
				},
			)

	validate_sales_invoice_references(invoice)
	if hasattr(invoice, "set_missing_values"):
		invoice.set_missing_values()
	if hasattr(invoice, "calculate_taxes_and_totals"):
		invoice.calculate_taxes_and_totals()
	invoice.insert(ignore_permissions=True)

	for record in records:
		_update_retention_record_for_draft_invoice(record, invoice.name)

	return invoice.name


def sync_from_ra_bill(ra_bill, sales_invoice=None):
	if flt(ra_bill.retention_amount) <= 0:
		return None

	record_name = frappe.db.get_value("Retention Record", {"ra_bill": ra_bill.name}, "name")
	if record_name:
		record = frappe.get_doc("Retention Record", record_name)
	else:
		record = frappe.new_doc("Retention Record")
		record.ra_bill = ra_bill.name
		record.released_amount = 0

	record.project = ra_bill.project
	record.customer = ra_bill.customer
	record.boq = ra_bill.boq
	record.sales_order = get_ra_bill_sales_order(ra_bill)
	record.sales_invoice = sales_invoice or ra_bill.sales_invoice
	record.retention_percent = ra_bill.retention_percent
	record.gross_amount = ra_bill.gross_amount
	record.retention_amount = ra_bill.retention_amount

	if record_name:
		record.save(ignore_permissions=True)
	else:
		record.insert(ignore_permissions=True)

	return record.name


def set_sales_invoice_for_ra_bill(ra_bill, sales_invoice):
	record_name = frappe.db.get_value("Retention Record", {"ra_bill": ra_bill.name}, "name")
	if not record_name:
		return sync_from_ra_bill(ra_bill, sales_invoice=sales_invoice)

	values = {"sales_invoice": sales_invoice}
	sales_order = get_ra_bill_sales_order(ra_bill)
	if frappe.get_meta("Retention Record").has_field("sales_order") and sales_order:
		values["sales_order"] = sales_order

	frappe.db.set_value("Retention Record", record_name, values, update_modified=True)
	return record_name


def _parse_retention_record_names(retention_records):
	if isinstance(retention_records, str):
		retention_records = frappe.parse_json(retention_records)

	if isinstance(retention_records, dict):
		retention_records = (
			retention_records.get("retention_records")
			or retention_records.get("names")
			or retention_records.get("items")
		)

	names = []
	seen = set()
	for value in retention_records or []:
		if isinstance(value, dict):
			value = value.get("name") or value.get("retention_record")
		if not value or value in seen:
			continue
		names.append(value)
		seen.add(value)

	if not names:
		frappe.throw(_("Please select at least one Retention Record."))

	return names


def _get_retention_records_for_invoice(names):
	records = []
	for name in names:
		if not frappe.db.exists("Retention Record", name):
			frappe.throw(_("Retention Record {0} does not exist.").format(name))
		records.append(frappe.get_doc("Retention Record", name))
	return records


def _validate_retention_records_for_invoice(records):
	if not records:
		frappe.throw(_("Please select at least one Retention Record."))

	customers = {record.customer for record in records if record.customer}
	if any(not record.customer for record in records) or len(customers) != 1:
		frappe.throw(_("Please select Retention Records for the same Customer only."))

	projects = {record.project for record in records if record.project}
	if any(not record.project for record in records) or len(projects) != 1:
		frappe.throw(_("Please select Retention Records for the same Project only."))

	for record in records:
		record._sync_and_validate_ra_bill_links()

	sales_orders = {get_retention_record_sales_order(record) for record in records}
	sales_orders.discard(None)
	sales_orders.discard("")
	if len(sales_orders) > 1:
		frappe.throw(_("Please select Retention Records for the same Sales Order only."))

	for record in records:
		if record.status == "Cancelled":
			frappe.throw(_("Retention Record {0} is Cancelled.").format(record.name))

		if record.status not in ("Held", "Partially Released"):
			frappe.throw(
				_("Retention Record {0} must be Held or Partially Released.").format(
					record.name
				)
			)

		if flt(record.balance_amount) <= 0:
			frappe.throw(
				_("Retention Record {0} has no remaining balance to invoice.").format(
					record.name
				)
			)

		if _has_active_release_invoice(record):
			frappe.throw(
				_("Retention Record {0} already has a retention release invoice: {1}").format(
					record.name,
					record.retention_release_invoice,
				)
			)


def _has_active_release_invoice(record):
	if not record.retention_release_invoice:
		return False

	invoice = frappe.db.get_value(
		"Sales Invoice",
		record.retention_release_invoice,
		["name", "docstatus"],
		as_dict=True,
	)
	return bool(invoice and invoice.docstatus != 2)


def _get_retention_invoice_company(records):
	project = records[0].project if records else None
	company = None

	if project and frappe.get_meta("Project").has_field("company"):
		company = frappe.db.get_value("Project", project, "company")

	return (
		company
		or frappe.defaults.get_user_default("Company")
		or frappe.defaults.get_global_default("company")
	)


def _get_retention_invoice_currency(records, company):
	currencies = set()
	for record in records:
		if record.ra_bill and frappe.db.exists("RA Bill", record.ra_bill):
			currency = frappe.db.get_value("RA Bill", record.ra_bill, "currency")
			if currency:
				currencies.add(currency)

	if len(currencies) > 1:
		frappe.throw(_("Please select Retention Records with the same Currency only."))

	return next(iter(currencies), None) or frappe.get_cached_value(
		"Company", company, "default_currency"
	) or frappe.defaults.get_global_default("currency")


def _get_retention_invoice_item_description(record):
	return _("Retention Release against RA Bill {0} / Retention Record {1}").format(
		record.ra_bill or "-",
		record.name,
	)


def _set_if_meta_has_field(doc, fieldname, value):
	if doc.meta.has_field(fieldname) and value not in (None, ""):
		doc.set(fieldname, value)


def get_ra_bill_sales_order(ra_bill):
	if not ra_bill:
		return None

	if isinstance(ra_bill, str):
		values = get_ra_bill_reference_values(ra_bill)
	else:
		values = get_ra_bill_reference_values(ra_bill.name, ra_bill_doc=ra_bill)

	return values.get("sales_order") if values else None


def get_retention_record_sales_order(record):
	if not record:
		return None

	sales_order = record.get("sales_order")
	if sales_order:
		return sales_order

	if record.get("ra_bill"):
		return get_ra_bill_sales_order(record.ra_bill)

	if record.get("boq"):
		return frappe.db.get_value("BOQ", record.boq, "sales_order")

	return None


def get_ra_bill_reference_values(ra_bill, ra_bill_doc=None):
	if not ra_bill:
		return frappe._dict()

	if ra_bill_doc:
		values = frappe._dict(
			{
				"name": ra_bill_doc.name,
				"customer": ra_bill_doc.get("customer"),
				"project": ra_bill_doc.get("project"),
				"boq": ra_bill_doc.get("boq"),
				"sales_order": ra_bill_doc.get("sales_order"),
			}
		)
	else:
		values = frappe.db.get_value(
			"RA Bill",
			ra_bill,
			["name", "customer", "project", "boq", "sales_order"],
			as_dict=True,
		)

	if not values:
		return frappe._dict()

	boq_values = None
	if values.get("boq"):
		boq_values = frappe.db.get_value(
			"BOQ",
			values.boq,
			["sales_order", "client", "project"],
			as_dict=True,
		)

	if values.get("sales_order") and boq_values and boq_values.get("sales_order"):
		if values.sales_order != boq_values.sales_order:
			frappe.throw(
				_("RA Bill Sales Order must match the Sales Order linked to BOQ {0}.").format(
					values.boq
				)
			)

	if not values.get("sales_order") and boq_values:
		values.sales_order = boq_values.get("sales_order")

	return values


def validate_sales_invoice_references(invoice, method=None):
	if not invoice:
		return

	if getattr(invoice, "retention_record", None):
		_validate_retention_sales_invoice_references(invoice)
	elif getattr(invoice, "ra_bill", None):
		_validate_ra_bill_sales_invoice_references(invoice)


def _validate_ra_bill_sales_invoice_references(invoice):
	expected = get_ra_bill_reference_values(invoice.ra_bill)
	if not expected:
		frappe.throw(_("RA Bill {0} does not exist.").format(invoice.ra_bill))

	_validate_invoice_field(invoice, "customer", expected.customer, _("Customer"))
	_validate_invoice_field(invoice, "project", expected.project, _("Project"))
	_validate_invoice_field(invoice, "boq", expected.boq, _("BOQ"))
	_validate_invoice_field(
		invoice,
		"sales_order",
		expected.sales_order,
		_("Sales Order"),
		mismatch_message=_("Sales Invoice Sales Order must match the Sales Order linked to the originating RA Bill."),
	)


def _validate_retention_sales_invoice_references(invoice):
	record = frappe.get_doc("Retention Record", invoice.retention_record)
	record._sync_and_validate_ra_bill_links()
	expected_sales_order = get_retention_record_sales_order(record)

	_validate_invoice_field(invoice, "customer", record.customer, _("Customer"))
	_validate_invoice_field(invoice, "project", record.project, _("Project"))
	_validate_invoice_field(invoice, "ra_bill", record.ra_bill, _("RA Bill"))
	_validate_invoice_field(invoice, "boq", record.boq, _("BOQ"))
	_validate_invoice_field(
		invoice,
		"sales_order",
		expected_sales_order,
		_("Sales Order"),
		mismatch_message=_("Retention Sales Invoice Sales Order must match the Sales Order linked to Retention Record {0}.").format(
			record.name
		),
	)


def _validate_invoice_field(invoice, fieldname, expected_value, label, mismatch_message=None):
	if not expected_value or not invoice.meta.has_field(fieldname):
		return

	current_value = invoice.get(fieldname)
	if current_value and current_value != expected_value:
		frappe.throw(
			mismatch_message
			or _("Sales Invoice {0} must match the source document {0}.").format(label)
		)
	if not current_value:
		invoice.set(fieldname, expected_value)


def _update_retention_record_for_draft_invoice(record, invoice_name):
	values = {
		"retention_release_invoice": invoice_name,
		"invoice_date": today(),
		"invoice_status": "Draft",
		"paid_amount": 0,
		"outstanding_amount": flt(record.balance_amount),
	}
	if record.meta.has_field("release_invoice_date"):
		values["release_invoice_date"] = today()

	frappe.db.set_value(
		"Retention Record",
		record.name,
		values,
		update_modified=True,
	)


def sync_from_sales_invoice(invoice, payment_entry=None):
	if not invoice:
		return None

	references = _get_invoice_retention_references(invoice)
	if not references:
		return None

	remaining_paid = (
		max(0, flt(invoice.grand_total) - flt(invoice.outstanding_amount))
		if invoice.docstatus == 1
		else 0
	)
	updated_records = []

	for reference in references:
		record = frappe.get_doc("Retention Record", reference["name"])
		if record.status == "Cancelled":
			continue

		release_amount = _get_invoice_reference_release_amount(record, reference)
		retention_amount = flt(record.retention_amount)

		record.invoice_date = invoice.posting_date

		if invoice.docstatus == 2:
			if _has_other_active_release_invoice(record, invoice.name):
				continue
			record.retention_release_invoice = invoice.name
			record.invoice_status = "Cancelled"
			record.paid_amount = 0
			record.outstanding_amount = 0
			record.released_amount = 0
			record.balance_amount = max(0, retention_amount)
			record.status = "Held"
		elif invoice.docstatus == 1:
			record.retention_release_invoice = invoice.name
			allocated_paid = min(remaining_paid, release_amount)
			remaining_paid = max(0, remaining_paid - allocated_paid)
			pre_invoice_released = max(0, retention_amount - release_amount)
			record.invoice_status = "Submitted"
			record.paid_amount = allocated_paid
			record.outstanding_amount = max(0, release_amount - allocated_paid)
			record.released_amount = min(
				retention_amount,
				pre_invoice_released + allocated_paid,
			)
			record.balance_amount = max(0, retention_amount - flt(record.released_amount))
			record.status = _get_retention_status(
				record.released_amount,
				retention_amount,
			)
		else:
			record.retention_release_invoice = invoice.name
			pre_invoice_released = max(0, retention_amount - release_amount)
			record.invoice_status = "Draft"
			record.paid_amount = 0
			record.outstanding_amount = release_amount
			record.released_amount = pre_invoice_released
			record.balance_amount = max(0, retention_amount - pre_invoice_released)
			record.status = _get_retention_status(
				record.released_amount,
				retention_amount,
			)

		if payment_entry:
			record.last_payment_entry = payment_entry.name

		if record.status == "Released" and not record.release_date:
			record.release_date = (
				getattr(payment_entry, "posting_date", None)
				or getattr(invoice, "posting_date", None)
				or today()
			)
		elif record.status != "Released":
			record.release_date = None

		record.save(ignore_permissions=True)
		updated_records.append(record.name)

	return updated_records[0] if len(updated_records) == 1 else updated_records


def _get_invoice_retention_references(invoice):
	references = []
	seen = set()

	def add_reference(name, release_amount=0):
		if not name or name in seen or not frappe.db.exists("Retention Record", name):
			return
		references.append({"name": name, "release_amount": flt(release_amount)})
		seen.add(name)

	if invoice.meta.has_field("retention_records"):
		for row in invoice.get("retention_records") or []:
			add_reference(row.retention_record, row.balance_amount)

	if getattr(invoice, "retention_record", None):
		add_reference(invoice.retention_record)

	if invoice.name:
		for row in frappe.get_all(
			"Retention Record",
			filters={"retention_release_invoice": invoice.name},
			fields=["name"],
			order_by="creation asc, name asc",
		):
			add_reference(row.name)

	return references


def _get_invoice_reference_release_amount(record, reference):
	release_amount = flt(reference.get("release_amount"))
	if release_amount > 0:
		return min(release_amount, flt(record.retention_amount))

	stored_release_amount = flt(record.paid_amount) + flt(record.outstanding_amount)
	if stored_release_amount > 0:
		return min(stored_release_amount, flt(record.retention_amount))

	current_balance = flt(record.balance_amount)
	if current_balance > 0:
		return min(current_balance, flt(record.retention_amount))

	return flt(record.retention_amount)


def _has_other_active_release_invoice(record, invoice_name):
	if not record.retention_release_invoice or record.retention_release_invoice == invoice_name:
		return False

	invoice = frappe.db.get_value(
		"Sales Invoice",
		record.retention_release_invoice,
		["name", "docstatus"],
		as_dict=True,
	)
	return bool(invoice and invoice.docstatus != 2)


def _get_retention_status(released_amount, retention_amount):
	released_amount = flt(released_amount)
	retention_amount = flt(retention_amount)
	if released_amount <= 0:
		return "Held"
	if released_amount < retention_amount:
		return "Partially Released"
	return "Released"


def sync_from_payment_entry(payment_entry):
	if not payment_entry:
		return None

	if _is_retention_release_payment(payment_entry):
		return sync_retention_record_from_release_payments(payment_entry)

	for reference in payment_entry.get("references") or []:
		if reference.reference_doctype != "Sales Invoice" or not reference.reference_name:
			continue
		invoice = frappe.get_doc("Sales Invoice", reference.reference_name)
		sync_from_sales_invoice(invoice, payment_entry=payment_entry)

	return payment_entry.name


def on_sales_invoice_submit(doc, method=None):
	sync_from_sales_invoice(doc)


def on_sales_invoice_cancel(doc, method=None):
	sync_from_sales_invoice(doc)


def on_sales_invoice_update_after_submit(doc, method=None):
	sync_from_sales_invoice(doc)


def on_payment_entry_submit(doc, method=None):
	sync_from_payment_entry(doc)


def on_payment_entry_cancel(doc, method=None):
	sync_from_payment_entry(doc)


def on_payment_entry_update_after_submit(doc, method=None):
	sync_from_payment_entry(doc)


def _is_retention_release_payment(payment_entry):
	if not payment_entry or payment_entry.payment_type != "Receive" or payment_entry.party_type != "Customer":
		return False

	if payment_entry.meta.has_field("custom_is_retention_payment") and payment_entry.get("custom_is_retention_payment"):
		return True

	retention_account = get_construction_account(
		payment_entry.company,
		"retention_receivable",
		transaction=payment_entry,
	)
	if payment_entry.paid_from != retention_account:
		return False

	if payment_entry.meta.has_field("custom_retention_record"):
		return bool(payment_entry.get("custom_retention_record"))

	if payment_entry.meta.has_field("retention_record"):
		return bool(payment_entry.get("retention_record"))

	return True


def sync_retention_record_from_release_payments(payment_entry):
	if not payment_entry or not payment_entry.company:
		return None

	record_name = _get_payment_entry_retention_record(payment_entry)
	if not record_name:
		return sync_retention_records_from_release_payments(
			payment_entry.party,
			payment_entry.company,
			payment_entry=payment_entry,
		)

	record = frappe.get_doc("Retention Record", record_name)
	retention_account = get_construction_account(
		payment_entry.company,
		"retention_receivable",
		transaction=payment_entry,
	)
	released_amount = min(
		_get_total_retention_release_payments(payment_entry.company, retention_account, record_name=record.name),
		flt(record.retention_amount),
	)
	_update_retention_record_release_status(record, released_amount, payment_entry=payment_entry)
	return record.name


def sync_retention_records_from_release_payments(customer, company, payment_entry=None):
	if not customer or not company:
		return None

	retention_account = get_construction_account(company, "retention_receivable")
	total_released = _get_total_retention_release_payments(company, retention_account, customer=customer)
	records = frappe.get_all(
		"Retention Record",
		filters={"customer": customer, "status": ["!=", "Cancelled"]},
		fields=["name"],
		order_by="creation asc, name asc",
	)

	updated_records = []
	for row in records:
		record = frappe.get_doc("Retention Record", row.name)
		retention_amount = flt(record.retention_amount)
		released_amount = min(total_released, retention_amount)
		total_released = max(0, total_released - released_amount)
		_update_retention_record_release_status(record, released_amount, payment_entry=payment_entry)
		updated_records.append(record.name)

	return updated_records[0] if len(updated_records) == 1 else updated_records


def _update_retention_record_release_status(record, released_amount, payment_entry=None):
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


def _get_total_retention_release_payments(company, retention_account, customer=None, record_name=None):
	base_filters = {
			"docstatus": 1,
			"payment_type": "Receive",
			"party_type": "Customer",
			"company": company,
			"paid_from": retention_account,
	}
	if customer:
		base_filters["party"] = customer
	if record_name:
		total = 0
		seen_payment_entries = set()
		for record_field in _get_payment_entry_retention_record_fields():
			filters = base_filters.copy()
			filters[record_field] = record_name
			for row in frappe.get_all("Payment Entry", filters=filters, fields=["name", "paid_amount"]):
				if row.name in seen_payment_entries:
					continue

				seen_payment_entries.add(row.name)
				total += flt(row.paid_amount)

		return total

	rows = frappe.get_all("Payment Entry", filters=base_filters, fields=["paid_amount"])
	return sum(flt(row.paid_amount) for row in rows)


def _get_open_retention_payment_entry(record_name):
	record_field = _get_payment_entry_retention_record_field()
	if not record_field:
		return None

	filters = {record_field: record_name, "docstatus": 0}

	return frappe.db.get_value("Payment Entry", filters, "name", order_by="modified desc")


def _get_payment_entry_retention_record(payment_entry):
	if not payment_entry:
		return None

	for fieldname in ("custom_retention_record", "retention_record"):
		if payment_entry.meta.has_field(fieldname) and payment_entry.get(fieldname):
			return payment_entry.get(fieldname)

	return None


def _get_payment_entry_retention_record_field():
	fields = _get_payment_entry_retention_record_fields()
	return fields[0] if fields else None


def _get_payment_entry_retention_record_fields():
	meta = frappe.get_meta("Payment Entry")
	return [
		fieldname
		for fieldname in ("custom_retention_record", "retention_record")
		if meta.has_field(fieldname)
	]


def _get_retention_payment_company(record):
	if record.sales_invoice:
		company = frappe.db.get_value("Sales Invoice", record.sales_invoice, "company")
		if company:
			return company

	if record.ra_bill:
		company = frappe.db.get_value("RA Bill", record.ra_bill, "company")
		if company:
			return company

	if record.project and frappe.get_meta("Project").has_field("company"):
		company = frappe.db.get_value("Project", record.project, "company")
		if company:
			return company

	return frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")


def _get_retention_release_bank_account(company, customer):
	from erpnext.accounts.doctype.bank_account.bank_account import get_default_company_bank_account

	bank_account_name = get_default_company_bank_account(company, "Customer", customer)
	if isinstance(bank_account_name, dict):
		bank_account_name = bank_account_name.get("name")
	if bank_account_name:
		account = frappe.db.get_value("Bank Account", bank_account_name, "account")
		if account:
			return account

	return None


def _get_retention_clearing_cost_center(company):
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


def mark_cancelled_from_ra_bill(ra_bill):
	record_name = frappe.db.get_value("Retention Record", {"ra_bill": ra_bill.name}, "name")
	if not record_name:
		return None

	record = frappe.get_doc("Retention Record", record_name)
	record.status = "Cancelled"
	record.remarks = _append_remark(record.remarks, CANCEL_REMARK)
	record.save(ignore_permissions=True)
	return record.name


def _ensure_retention_release_item(company):
	item_code = "Retention Release"
	item_group = _get_retention_item_group()

	item = None
	if frappe.db.exists("Item", item_code):
		item = frappe.get_doc("Item", item_code)

	if not item:
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": item_code,
				"description": "Retention release billing item",
				"item_group": item_group,
				"stock_uom": "Nos",
				"is_stock_item": 0,
				"is_purchase_item": 0,
				"is_sales_item": 1,
			}
		)
		if company:
			item_defaults = get_construction_account(company, "ra_bill_income")
			item.append(
				"item_defaults",
				{
					"company": company,
					"income_account": item_defaults,
				},
			)
		item.insert(ignore_permissions=True)
		return item_code

	if not item.item_group or not frappe.db.exists("Item Group", item.item_group):
		item.item_group = item_group

	if not item.stock_uom:
		item.stock_uom = "Nos"
	if item.is_stock_item is None:
		item.is_stock_item = 0
	if item.is_sales_item is None:
		item.is_sales_item = 1
	if item.is_purchase_item is None:
		item.is_purchase_item = 0
	if not item.description:
		item.description = "Retention release billing item"
	if item.item_name != item_code:
		item.item_name = item_code

	item.save(ignore_permissions=True)
	return item_code


def _get_retention_item_group():
	for group_name in ("Services", "All Item Groups"):
		if frappe.db.exists("Item Group", group_name):
			return group_name

	item_group = frappe.db.get_value(
		"Item Group",
		{"is_group": 0},
		"name",
	)
	if item_group:
		return item_group

	if not frappe.db.exists("Item Group", "Services"):
		item_group_doc = frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": "Services",
				"parent_item_group": "All Item Groups" if frappe.db.exists("Item Group", "All Item Groups") else "",
				"is_group": 0,
			}
		)
		item_group_doc.insert(ignore_permissions=True)
		return item_group_doc.name

	return "Services"


def _append_remark(existing, remark):
	remark = (remark or "").strip()
	if not remark:
		return existing

	existing = (existing or "").strip()
	if not existing:
		return remark

	if remark in existing:
		return existing

	return f"{existing}\n{remark}"
