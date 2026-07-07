import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, getdate, today


AMOUNT_TOLERANCE = 0.0001
CANCEL_REMARK = "Cancelled because RA Bill was cancelled"


class RetentionRecord(Document):
	def validate(self):
		self._validate_amounts()
		self._set_balance_and_status()

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
		if self.status == "Cancelled":
			frappe.throw(_("Cannot create a Sales Invoice for a Cancelled Retention Record."))

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
		income_account = frappe.db.get_value("Company", company, "default_income_account")
		company_currency = frappe.get_cached_value("Company", company, "default_currency")
		ra_bill_doc = None
		if self.ra_bill and frappe.db.exists("RA Bill", self.ra_bill):
			ra_bill_doc = frappe.get_doc("RA Bill", self.ra_bill)
		currency = (
			getattr(ra_bill_doc, "currency", None)
			or company_currency
			or "AED"
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
	def make_payment_entry(self):
		if not self.retention_release_invoice:
			frappe.throw(_("No retention invoice exists to pay against."))

		invoice = frappe.get_doc("Sales Invoice", self.retention_release_invoice)
		if invoice.docstatus != 1:
			frappe.throw(_("The retention invoice must be submitted before making payment."))

		if flt(invoice.outstanding_amount) <= 0:
			frappe.throw(_("The retention invoice has no outstanding balance."))

		payment_entry = invoice.get_payment_entry()
		if not payment_entry:
			frappe.throw(_("Unable to create a standard Payment Entry for this invoice."))

		payment_entry.insert(ignore_permissions=True)
		self.last_payment_entry = payment_entry.name
		self.save(ignore_permissions=True)
		return payment_entry.name


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

	frappe.db.set_value(
		"Retention Record",
		record_name,
		"sales_invoice",
		sales_invoice,
		update_modified=True,
	)
	return record_name


def sync_from_sales_invoice(invoice, payment_entry=None):
	if not invoice:
		return None

	retention_record_name = None
	if getattr(invoice, "retention_record", None):
		retention_record_name = invoice.retention_record
	elif invoice.name:
		retention_record_name = frappe.db.get_value(
			"Retention Record",
			{"retention_release_invoice": invoice.name},
			"name",
		)

	if not retention_record_name:
		return None

	record = frappe.get_doc("Retention Record", retention_record_name)
	if record.status == "Cancelled":
		return record.name

	record.retention_release_invoice = invoice.name
	record.invoice_date = invoice.posting_date
	if invoice.docstatus == 2:
		record.invoice_status = "Cancelled"
		record.paid_amount = 0
		record.outstanding_amount = 0
		record.released_amount = 0
		record.balance_amount = max(0, flt(record.retention_amount))
		record.status = "Held"
	elif invoice.docstatus == 1:
		record.invoice_status = "Submitted"
		paid_amount = max(0, flt(invoice.grand_total) - flt(invoice.outstanding_amount))
		record.paid_amount = paid_amount
		record.outstanding_amount = flt(invoice.outstanding_amount)
		record.released_amount = paid_amount
		record.balance_amount = max(0, flt(record.retention_amount) - paid_amount)
		if paid_amount <= 0:
			record.status = "Held"
		elif paid_amount < flt(record.retention_amount):
			record.status = "Partially Released"
		else:
			record.status = "Released"
	else:
		record.invoice_status = "Draft"
		record.paid_amount = 0
		record.outstanding_amount = flt(invoice.grand_total)
		record.released_amount = 0
		record.balance_amount = max(0, flt(record.retention_amount))
		record.status = "Held"

	if payment_entry:
		record.last_payment_entry = payment_entry.name

	record.save(ignore_permissions=True)
	return record.name


def sync_from_payment_entry(payment_entry):
	if not payment_entry:
		return None

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
			item_defaults = frappe.db.get_value("Company", company, "default_income_account")
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
