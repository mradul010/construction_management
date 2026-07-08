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


@frappe.whitelist()
def create_sales_invoice_for_retention_records(retention_records):
	names = _parse_retention_record_names(retention_records)
	records = _get_retention_records_for_invoice(names)
	_validate_retention_records_for_invoice(records)

	company = _get_retention_invoice_company(records)
	if not company:
		frappe.throw(_("Please set the default Company before creating a Sales Invoice."))

	customer = records[0].customer
	project = records[0].project
	if not customer or not frappe.db.exists("Customer", customer):
		frappe.throw(_("Customer {0} does not exist.").format(customer or ""))

	currency = _get_retention_invoice_currency(records, company)
	item_code = _ensure_retention_release_item(company)
	income_account = frappe.db.get_value("Company", company, "default_income_account")
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
	) or "AED"


def _get_retention_invoice_item_description(record):
	return _("Retention Release against RA Bill {0} / Retention Record {1}").format(
		record.ra_bill or "-",
		record.name,
	)


def _set_if_meta_has_field(doc, fieldname, value):
	if doc.meta.has_field(fieldname) and value not in (None, ""):
		doc.set(fieldname, value)


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
