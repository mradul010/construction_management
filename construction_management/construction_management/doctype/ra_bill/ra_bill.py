import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today


OVERBILLING_TOLERANCE = 0.0001

RA_BILL_TAX_CHARGE_TYPES = {
	"Actual",
	"On Net Total",
	"On Previous Row Amount",
	"On Previous Row Total",
	"On Item Quantity",
}


class RABill(Document):
	def validate(self):
		self._set_bill_no()
		self._fetch_boq_item_details()
		self._fill_previous_work_summary()
		self.validate_item_values()
		self._calculate_row_totals()
		self._validate_no_duplicate_items()
		self._validate_not_overbilling()
		self._calculate_header_totals()
		self._validate_payment_and_tax_fields()
		self.calculate_taxes_and_grand_total()

	def _set_bill_no(self):
		"""
		Auto-increment bill_no per project+BOQ combination.
		Bill 1, Bill 2, Bill 3 ... independently per BOQ.
		"""
		if self.bill_no:
			return

		existing = frappe.db.get_all(
			"RA Bill",
			filters={
				"project": self.project,
				"boq": self.boq,
				"name": ["!=", self.name],
			},
			fields=["bill_no"],
			order_by="bill_no desc",
			limit=1,
		)
		self.bill_no = (existing[0].bill_no + 1) if existing else 1

	def validate_item_values(self):
		for row in self.items:
			if not row.boq_item:
				continue

			item = row.item_name or row.boq_item

			if flt(row.work_percent) <= 0:
				frappe.throw(
					_("Work % for item {0} must be greater than 0.").format(item)
				)

			if flt(row.work_percent) > 100:
				frappe.throw(
					_("Work % for item {0} cannot be greater than 100.").format(item)
				)

			if flt(row.current_qty) < 0:
				frappe.throw(
					_("Current Qty for item {0} cannot be negative.").format(item)
				)

			if flt(row.boq_qty) <= 0:
				frappe.throw(
					_("BOQ Qty for item {0} must be greater than 0.").format(item)
				)

			if flt(row.boq_rate) < 0:
				frappe.throw(
					_("BOQ Rate for item {0} cannot be negative.").format(item)
				)

	def _fetch_boq_item_details(self):
		"""
		For each RA Bill Item row, fetch item_name, boq_qty,
		boq_rate, and uom from the linked BOQ Item.
		"""
		for row in self.items:
			if not row.boq_item:
				continue

			boq_item = frappe.db.get_value(
				"BOQ Item",
				row.boq_item,
				["item_name", "qty", "unit_rate", "uom", "boq_category"],
				as_dict=True,
			)
			if boq_item:
				row.item_name = boq_item.item_name
				row.boq_qty = boq_item.qty
				row.boq_rate = boq_item.unit_rate
				row.uom = boq_item.uom
				if not row.sub_category and boq_item.boq_category:
					row.sub_category = boq_item.boq_category
				if not row.category_name and boq_item.boq_category:
					row.category_name = (
						frappe.db.get_value(
							"BOQ Category", boq_item.boq_category, "parent_node"
						)
						or boq_item.boq_category
					)

	def _fill_previous_work_summary(self):
		"""
		For each row, read previous submitted billing from RA Bill Transaction.
		If transaction history has not been backfilled yet, the helper falls
		back to submitted RA Bill Items. Values are saved on the row so users
		can see previous and remaining work after reload.
		"""
		for row in self.items:
			if not row.boq_item:
				continue

			summary = _get_boq_item_billing_summary(
				self.boq,
				row.boq_item,
				self.name,
			)
			row.previous_qty = summary["previous_qty"]
			row.previous_percent = summary["previous_percent"]
			row.remaining_qty = summary["remaining_qty"]
			row.remaining_percent = summary["remaining_percent"]
			row.prev_cumulative_qty = summary["previous_qty"]

	def _fill_prev_cumulative_qty(self):
		self._fill_previous_work_summary()

	def _calculate_row_totals(self):
		"""
		Calculate current_qty and current_amount for each row from Work %.
		"""
		for row in self.items:
			row.work_percent = flt(row.work_percent)
			row.current_qty = flt(row.boq_qty) * (row.work_percent / 100)
			row.current_amount = flt(row.current_qty) * flt(row.boq_rate)
			row.cumulative_qty = flt(row.prev_cumulative_qty) + flt(row.current_qty)

	def _validate_no_duplicate_items(self):
		seen_items = set()

		for row in self.items:
			if not row.boq_item:
				continue

			if row.boq_item in seen_items:
				frappe.throw(
					_(
						"Duplicate BOQ Item found: {0}. "
						"The same BOQ Item cannot be selected more than once in the same RA Bill."
					).format(row.item_name or row.boq_item)
				)

			seen_items.add(row.boq_item)

	def _validate_not_overbilling(self):
		for row in self.items:
			if not row.boq_item:
				continue

			boq_qty = flt(row.boq_qty)
			current_qty = flt(row.current_qty)
			summary = _get_boq_item_billing_summary(self.boq, row.boq_item, self.name)
			previous_qty = summary["previous_qty"]
			remaining_qty = summary["remaining_qty"]
			previous_pct = summary["previous_percent"]
			remaining_pct = summary["remaining_percent"]

			row.previous_qty = previous_qty
			row.previous_percent = previous_pct
			row.remaining_qty = remaining_qty
			row.remaining_percent = remaining_pct
			row.prev_cumulative_qty = previous_qty
			row.cumulative_qty = previous_qty + current_qty

			if current_qty > remaining_qty + OVERBILLING_TOLERANCE:
				frappe.throw(
					_(
						"Item: {item}<br>"
						"BOQ Qty: {boq_qty}<br>"
						"Previously Billed Qty: {previous_qty}<br>"
						"Previously Billed %: {previous_pct}<br>"
						"Remaining Qty: {remaining_qty}<br>"
						"Remaining %: {remaining_pct}<br>"
						"You Entered Qty: {current_qty}<br>"
						"You Entered %: {work_percent}<br><br>"
						"Please reduce Work % / Current Qty."
					).format(
						item=row.item_name or row.boq_item,
						boq_qty=flt(boq_qty, 4),
						previous_qty=flt(previous_qty, 4),
						previous_pct=flt(previous_pct, 4),
						remaining_qty=flt(remaining_qty, 4),
						remaining_pct=flt(remaining_pct, 4),
						current_qty=flt(current_qty, 4),
						work_percent=flt(row.work_percent, 4),
					),
					title=_("Overbilling Not Allowed"),
				)

	def _calculate_header_totals(self):
		"""
		Sum up gross_amount, retention_amount, net_payable,
		and cumulative_billed across all submitted bills
		for this project + BOQ including this one.
		"""
		self.gross_amount = sum(row.current_amount or 0 for row in self.items)

		retention_pct = float(self.retention_percent or 0)
		self.retention_amount = self.gross_amount * (retention_pct / 100)
		self.net_payable = self.gross_amount - self.retention_amount

		prev_billed = frappe.db.sql(
			"""
			SELECT COALESCE(SUM(gross_amount), 0)
			FROM `tabRA Bill`
			WHERE project = %s
			  AND boq = %s
			  AND docstatus = 1
			  AND name != %s
			""",
			(self.project, self.boq, self.name or "__new__"),
		)
		self.cumulative_billed = (prev_billed[0][0] if prev_billed else 0) + self.gross_amount

	def _validate_payment_and_tax_fields(self):
		for row in self.get("advances") or []:
			advance_amount = flt(row.advance_amount)
			allocated_amount = flt(row.allocated_amount)

			if advance_amount < 0:
				frappe.throw(_("Advance Amount cannot be negative."))

			if allocated_amount < 0:
				frappe.throw(_("Allocated Amount cannot be negative."))

			if advance_amount and allocated_amount > advance_amount + OVERBILLING_TOLERANCE:
				frappe.throw(
					_(
						"Allocated Amount cannot be greater than Advance Amount "
						"for reference {0}."
					).format(row.reference_name or row.idx)
				)

		for row in self.get("taxes") or []:
			if row.charge_type and row.charge_type not in RA_BILL_TAX_CHARGE_TYPES:
				frappe.throw(_("Invalid tax charge type: {0}").format(row.charge_type))

	def calculate_taxes_and_grand_total(self):
		"""
		Keep the new Sales Invoice-like totals passive.
		RA Bill's existing gross/retention/net calculation remains authoritative.
		"""
		self.net_total = flt(self.gross_amount)

		total_taxes = 0
		for row in self.get("taxes") or []:
			total_taxes += flt(row.tax_amount)
			row.total = flt(self.net_payable) + total_taxes

		self.total_taxes_and_charges = total_taxes
		self.grand_total = flt(self.net_payable) + total_taxes

		self.total_advance = sum(flt(row.allocated_amount) for row in self.get("advances") or [])
		self.outstanding_amount = flt(self.grand_total) - flt(self.total_advance)

	def on_submit(self):
		self._validate_no_duplicate_items()
		self._validate_not_overbilling()
		self._create_ra_bill_transactions()
		self.db_set("status", "Submitted")

	def on_cancel(self):
		self._delete_ra_bill_transactions()
		self.db_set("status", "Cancelled")

	def _delete_ra_bill_transactions(self):
		_delete_ra_bill_transactions(self.name)

	def _create_ra_bill_transactions(self):
		self._delete_ra_bill_transactions()

		for row in self.items:
			current_qty = _get_row_current_qty(row)
			current_amount = _get_row_current_amount(row)
			if current_qty <= 0 or current_amount <= 0:
				continue

			previous_qty = _get_previous_billed_qty(self.boq, row.boq_item, self.name)
			_create_ra_bill_transaction(self, row, previous_qty)

	@frappe.whitelist()
	def approve(self):
		"""
		Approve a submitted RA Bill without saving the submitted document.
		The Create Sales Invoice flow depends on this status.
		"""
		if self.docstatus != 1:
			frappe.throw("Only submitted RA Bills can be approved.")

		if self.status == "Approved":
			return self.name

		if self.status != "Submitted":
			frappe.throw(
				"RA Bill must have status 'Submitted' before approval. "
				f"Current status: {self.status}"
			)

		self.db_set("status", "Approved")
		return self.name

	@frappe.whitelist()
	def create_sales_invoice(self):
		"""
		Creates a draft Sales Invoice from this approved RA Bill.
		Detailed lines:
		  1. One line per RA Bill Item current_amount (positive)
		  2. Retention Deduction -> -retention_amount (negative)
		Net total = net_payable.
		Status set to Invoiced after creation.
		"""
		if self.status != "Approved":
			frappe.throw(
				"RA Bill must have status 'Approved' before creating a Sales Invoice. "
				f"Current status: {self.status}"
			)

		if self.sales_invoice:
			frappe.throw(
				f"Sales Invoice {self.sales_invoice} already exists for this RA Bill. "
				"Cannot create another one."
			)

		if not self.customer:
			frappe.throw("Please set the Customer on this RA Bill before creating a Sales Invoice.")

		if not frappe.db.exists("Customer", self.customer):
			frappe.throw(f"Customer {self.customer} does not exist.")

		if not self.gross_amount or self.gross_amount <= 0:
			frappe.throw("Gross amount must be greater than 0 to create a Sales Invoice.")

		from construction_management.construction_management.setup import (
			ensure_ra_bill_items,
			get_or_create_ra_bill_receivable_account,
		)

		ensure_ra_bill_items()

		company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
		if not company:
			frappe.throw("Please set default Company before creating Sales Invoice.")

		company_currency = frappe.get_cached_value("Company", company, "default_currency")
		income_account = frappe.db.get_value("Company", company, "default_income_account")
		invoice_currency = self.currency or company_currency or "AED"
		conversion_rate = 1.0
		receivable_account = get_or_create_ra_bill_receivable_account(company, invoice_currency)

		def set_if_exists(doc, fieldname, value):
			if doc.meta.has_field(fieldname) and value not in (None, ""):
				doc.set(fieldname, value)

		def append_child_if_table_exists(doc, table_field, row_data):
			table_df = doc.meta.get_field(table_field)
			if not table_df or table_df.fieldtype != "Table" or not table_df.options:
				return

			child_meta = frappe.get_meta(table_df.options)
			filtered_row = {
				fieldname: value
				for fieldname, value in row_data.items()
				if child_meta.has_field(fieldname) and value not in (None, "")
			}
			if filtered_row:
				doc.append(table_field, filtered_row)

		def set_link_if_valid(doc, fieldname, value, parenttype, link_doctype, link_name):
			if not doc.meta.has_field(fieldname) or value in (None, ""):
				return

			if frappe.db.exists(
				"Dynamic Link",
				{
					"parent": value,
					"parenttype": parenttype,
					"link_doctype": link_doctype,
					"link_name": link_name,
				},
			):
				doc.set(fieldname, value)

		def get_first_payment_schedule_due_date():
			due_dates = [
				row.due_date for row in self.get("payment_schedule") or [] if row.due_date
			]
			return min(due_dates) if due_dates else None

		def get_posting_date():
			return self.billing_period_to or today()

		def get_due_date():
			schedule_due_date = get_first_payment_schedule_due_date()
			if schedule_due_date:
				return schedule_due_date
			return frappe.utils.add_days(get_posting_date(), 30)

		def add_advanced_fields(si):
			set_if_exists(si, "customer", self.customer)
			set_if_exists(si, "company", company)
			set_if_exists(si, "debit_to", receivable_account)
			set_if_exists(si, "project", self.project)
			set_if_exists(si, "currency", invoice_currency)
			set_if_exists(si, "conversion_rate", conversion_rate)
			set_if_exists(si, "posting_date", get_posting_date())
			set_if_exists(si, "due_date", get_due_date())
			set_if_exists(si, "remarks", self.remarks or f"Created from RA Bill {self.name}")
			set_if_exists(si, "letter_head", self.letter_head)
			set_if_exists(si, "select_print_heading", self.select_print_heading)
			set_if_exists(si, "language", self.language)
			set_if_exists(si, "ra_bill", self.name)

			set_link_if_valid(
				si,
				"customer_address",
				self.customer_address,
				"Address",
				"Customer",
				self.customer,
			)
			set_link_if_valid(
				si,
				"shipping_address_name",
				self.shipping_address_name,
				"Address",
				"Customer",
				self.customer,
			)
			set_link_if_valid(
				si,
				"contact_person",
				self.contact_person,
				"Contact",
				"Customer",
				self.customer,
			)
			set_link_if_valid(
				si,
				"dispatch_address_name",
				self.dispatch_address_name,
				"Address",
				"Company",
				company,
			)
			set_link_if_valid(
				si,
				"company_address",
				self.company_address,
				"Address",
				"Company",
				company,
			)
			set_link_if_valid(
				si,
				"company_contact_person",
				self.company_contact_person,
				"Contact",
				"Company",
				company,
			)

			for source_field, target_field in (
				("address_display", "address_display"),
				("contact_display", "contact_display"),
				("contact_mobile", "contact_mobile"),
				("contact_email", "contact_email"),
				("shipping_address", "shipping_address"),
				("dispatch_address", "dispatch_address"),
				("company_address_display", "company_address_display"),
				("territory", "territory"),
				("payment_terms_template", "payment_terms_template"),
				("terms", "tc_name"),
				("terms_and_conditions", "terms"),
				("tax_category", "tax_category"),
				("shipping_rule", "shipping_rule"),
				("incoterm", "incoterm"),
				("sales_taxes_and_charges_template", "taxes_and_charges"),
			):
				set_if_exists(si, target_field, self.get(source_field))

			for row in self.get("payment_schedule") or []:
				append_child_if_table_exists(
					si,
					"payment_schedule",
					{
						"payment_term": row.payment_term,
						"description": row.description,
						"due_date": row.due_date,
						"invoice_portion": row.invoice_portion,
						"payment_amount": row.payment_amount,
					},
				)

			for row in self.get("taxes") or []:
				append_child_if_table_exists(
					si,
					"taxes",
					{
						"charge_type": row.charge_type,
						"account_head": row.account_head,
						"description": row.description,
						"rate": row.rate,
						"tax_amount": row.tax_amount,
						"total": row.total,
					},
				)

			for row in self.get("advances") or []:
				append_child_if_table_exists(
					si,
					"advances",
					{
						"reference_type": row.reference_type,
						"reference_name": row.reference_name,
						"remarks": row.remarks,
						"advance_amount": row.advance_amount,
						"allocated_amount": row.allocated_amount,
						"difference_posting_date": row.difference_posting_date,
					},
				)

			for row in self.get("timesheets") or []:
				append_child_if_table_exists(
					si,
					"timesheets",
					{
						"activity_type": row.activity_type,
						"description": row.description,
						"billing_hours": row.billing_hours,
						"billing_amount": row.billing_amount,
						"time_sheet": row.timesheet,
					},
				)

		def make_sales_invoice(items):
			si_data = {
				"doctype": "Sales Invoice",
				"items": items,
			}
			si = frappe.get_doc(si_data)
			add_advanced_fields(si)
			if hasattr(si, "set_missing_values"):
				si.set_missing_values()
			if hasattr(si, "calculate_taxes_and_totals"):
				si.calculate_taxes_and_totals()
			si.insert(ignore_permissions=True)
			return si

		period_str = ""
		if self.billing_period_from and self.billing_period_to:
			period_str = (
				f"{frappe.format(self.billing_period_from, {'fieldtype': 'Date'})} to "
				f"{frappe.format(self.billing_period_to, {'fieldtype': 'Date'})}"
			)

		category_labels = {}

		def get_category_label(category):
			if not category:
				return ""
			if category not in category_labels:
				category_labels[category] = (
					frappe.db.get_value("BOQ Category", category, "category_name") or category
				)
			return category_labels[category]

		invoice_items = []
		for row in self.items:
			qty = flt(row.current_qty or 0)
			rate = flt(row.boq_rate or 0)
			amount = flt(row.current_amount or 0)

			if qty <= 0 or amount <= 0:
				continue

			calculated_amount = flt(qty * rate)

			description_lines = [
				f"Category: {get_category_label(row.category_name)}",
				f"Sub Category: {get_category_label(row.sub_category)}",
				f"Item: {row.item_name or ''}",
				f"BOQ Qty: {flt(row.boq_qty)} {row.uom or ''}".strip(),
				f"BOQ Rate: {rate}",
				f"Work Completed: {flt(row.work_percent)}%",
				f"Current Qty: {qty}",
				f"Amount: {amount}",
			]
			if abs(calculated_amount - amount) > 0.01:
				description_lines.append(
					f"Amount Check: Qty x Rate = {calculated_amount}; RA Bill Current Amount = {amount}"
				)
			if period_str:
				description_lines.append(f"Billing Period: {period_str}")
			description_lines.extend(
				[
					f"RA Bill #{self.bill_no}",
					f"Project: {self.project}",
					f"BOQ: {self.boq}",
				]
			)

			invoice_items.append(
				{
					"item_code": "RA Bill Services",
					"item_name": row.item_name or "RA Bill Services",
					"description": "\n".join(description_lines),
					"qty": qty,
					"rate": rate,
					"uom": row.uom or "Nos",
					"income_account": income_account,
				}
			)

		if not invoice_items:
			frappe.throw("No RA Bill Items with a positive current amount were found to invoice.")

		invoice_gross = sum(
			flt(item.get("qty")) * flt(item.get("rate")) for item in invoice_items
		)
		if flt(invoice_gross, 2) != flt(self.gross_amount, 2):
			frappe.throw(
				"Detailed RA Bill Item total does not match the RA Bill gross amount. "
				f"Item total: {frappe.format(invoice_gross, {'fieldtype': 'Currency'})}, "
				f"Gross amount: {frappe.format(self.gross_amount, {'fieldtype': 'Currency'})}."
			)

		if self.retention_amount and self.retention_amount > 0:
			retention_description = (
				f"Retention held @ {self.retention_percent}%\n"
				f"To be released at project completion\n"
				f"RA Bill #{self.bill_no} | {self.project}"
			)
			invoice_items.append(
				{
					"item_code": "Retention Deduction",
					"item_name": "Retention Deduction",
					"description": retention_description,
					"qty": 1,
					"rate": -self.retention_amount,
					"uom": "Nos",
					"income_account": income_account,
				}
			)

		invoice_net_total = sum(
			flt(item.get("qty")) * flt(item.get("rate")) for item in invoice_items
		)
		if flt(invoice_net_total, 2) != flt(self.net_payable, 2):
			frappe.throw(
				"Sales Invoice item total does not match the RA Bill net payable. "
				f"Invoice total: {frappe.format(invoice_net_total, {'fieldtype': 'Currency'})}, "
				f"Net payable: {frappe.format(self.net_payable, {'fieldtype': 'Currency'})}."
			)

		try:
			si = make_sales_invoice(invoice_items)
		except Exception as negative_rate_error:
			if not (self.retention_amount and self.retention_amount > 0):
				raise

			fallback_items = []
			for item in invoice_items:
				item = item.copy()
				if item["item_code"] == "Retention Deduction":
					item["qty"] = -1
					item["rate"] = self.retention_amount
				fallback_items.append(item)

			try:
				si = make_sales_invoice(fallback_items)
			except Exception:
				raise negative_rate_error

		self.db_set("sales_invoice", si.name)
		self.db_set("status", "Invoiced")

		frappe.msgprint(
			f"Draft Sales Invoice <b>{si.name}</b> created successfully. "
			f"Net payable: {frappe.format(self.net_payable, {'fieldtype': 'Currency'})}. "
			f"Please review and submit from the Accounts module.",
			title="Sales Invoice Created",
			indicator="green",
		)

		return si.name


@frappe.whitelist()
def get_customer_address_and_contact(customer):
	if not customer:
		return {}

	from frappe.contacts.doctype.address.address import get_address_display, get_default_address
	from frappe.contacts.doctype.contact.contact import get_default_contact

	billing_address = get_default_address("Customer", customer, "is_primary_address")
	shipping_address = get_default_address("Customer", customer, "is_shipping_address")
	contact = get_default_contact("Customer", customer)
	contact_details = {}

	if contact:
		contact_details = frappe.db.get_value(
			"Contact",
			contact,
			["full_name", "email_id", "mobile_no"],
			as_dict=True,
		) or {}

	return {
		"customer_address": billing_address,
		"address_display": get_address_display(billing_address) if billing_address else "",
		"shipping_address_name": shipping_address,
		"shipping_address": get_address_display(shipping_address) if shipping_address else "",
		"contact_person": contact,
		"contact_display": contact_details.get("full_name") or "",
		"contact_email": contact_details.get("email_id") or "",
		"contact_mobile": contact_details.get("mobile_no") or "",
		"territory": frappe.db.get_value("Customer", customer, "territory") or "",
	}


def _has_ra_bill_transaction_table():
	try:
		return frappe.db.table_exists("RA Bill Transaction")
	except Exception:
		return False


def _delete_ra_bill_transactions(ra_bill):
	if not ra_bill or not _has_ra_bill_transaction_table():
		return

	for transaction in frappe.get_all(
		"RA Bill Transaction",
		filters={"ra_bill": ra_bill},
		pluck="name",
	):
		frappe.delete_doc(
			"RA Bill Transaction",
			transaction,
			force=True,
			ignore_permissions=True,
		)


def _get_previous_billed_qty(boq, boq_item, current_ra_bill=None):
	if not boq or not boq_item:
		return 0

	transaction_qty = 0
	transaction_count = 0
	if _has_ra_bill_transaction_table():
		transaction_rows = frappe.db.sql(
			"""
			SELECT COALESCE(SUM(current_qty), 0) AS qty, COUNT(*) AS transaction_count
			FROM `tabRA Bill Transaction`
			WHERE boq = %(boq)s
			  AND boq_item = %(boq_item)s
			  AND (%(current_ra_bill)s = '' OR ra_bill != %(current_ra_bill)s)
			""",
			{
				"boq": boq,
				"boq_item": boq_item,
				"current_ra_bill": current_ra_bill or "",
			},
			as_dict=True,
		)
		if transaction_rows:
			transaction_qty = flt(transaction_rows[0].qty)
			transaction_count = transaction_rows[0].transaction_count or 0

	fallback_qty = _get_previous_billed_qty_from_submitted_ra_bills(
		boq,
		boq_item,
		current_ra_bill,
	)

	if transaction_count:
		return max(transaction_qty, fallback_qty)

	return fallback_qty


def _get_previous_billed_qty_from_submitted_ra_bills(boq, boq_item, current_ra_bill=None):
	result = frappe.db.sql(
		"""
		SELECT COALESCE(
			SUM(
				CASE
					WHEN COALESCE(rbi.current_qty, 0) > 0 THEN rbi.current_qty
					ELSE COALESCE(NULLIF(rbi.boq_qty, 0), bi.qty, 0)
						* COALESCE(rbi.work_percent, 0) / 100
				END
			),
			0
		) AS qty
		FROM `tabRA Bill Item` rbi
		JOIN `tabRA Bill` rb ON rb.name = rbi.parent
		LEFT JOIN `tabBOQ Item` bi ON bi.name = rbi.boq_item
		WHERE rb.boq = %(boq)s
		  AND rbi.boq_item = %(boq_item)s
		  AND rb.docstatus = 1
		  AND (%(current_ra_bill)s = '' OR rb.name != %(current_ra_bill)s)
		""",
		{
			"boq": boq,
			"boq_item": boq_item,
			"current_ra_bill": current_ra_bill or "",
		},
	)
	return flt(result[0][0]) if result else 0


def _get_boq_item_qty(boq, boq_item):
	if not boq_item:
		return 0

	filters = {"name": boq_item}
	if boq:
		filters["parent"] = boq

	qty = frappe.db.get_value("BOQ Item", filters, "qty")
	if qty is None and boq:
		qty = frappe.db.get_value("BOQ Item", boq_item, "qty")

	return flt(qty)


def _qty_to_percent(qty, boq_qty):
	boq_qty = flt(boq_qty)
	return (flt(qty) / boq_qty * 100) if boq_qty else 0


def _get_row_boq_qty(row, boq=None):
	return flt(row.get("boq_qty")) or _get_boq_item_qty(boq, row.get("boq_item"))


def _get_row_current_qty(row):
	current_qty = flt(row.get("current_qty"))
	if current_qty:
		return current_qty

	return _get_row_boq_qty(row) * flt(row.get("work_percent")) / 100


def _get_row_current_amount(row):
	current_amount = flt(row.get("current_amount"))
	if current_amount:
		return current_amount

	return _get_row_current_qty(row) * flt(row.get("boq_rate"))


def _get_transaction_date(ra_bill):
	date_value = (
		ra_bill.get("billing_period_to")
		or ra_bill.get("billing_period_from")
		or ra_bill.get("creation")
	)
	return getdate(date_value) if date_value else today()


def _create_ra_bill_transaction(ra_bill, row, previous_qty=0):
	boq_qty = _get_row_boq_qty(row, ra_bill.boq)
	current_qty = _get_row_current_qty(row)
	current_amount = _get_row_current_amount(row)
	cumulative_qty = flt(previous_qty) + current_qty
	cumulative_percent = _qty_to_percent(cumulative_qty, boq_qty)
	remaining_qty = boq_qty - cumulative_qty
	remaining_percent = 100 - cumulative_percent if boq_qty else 0

	transaction = frappe.get_doc(
		{
			"doctype": "RA Bill Transaction",
			"ra_bill": ra_bill.name,
			"project": ra_bill.project,
			"boq": ra_bill.boq,
			"boq_item": row.boq_item,
			"item_name": row.item_name,
			"category_name": row.category_name,
			"sub_category": row.sub_category,
			"boq_qty": boq_qty,
			"boq_rate": flt(row.boq_rate),
			"uom": row.uom,
			"work_percent": flt(row.work_percent),
			"current_qty": current_qty,
			"current_amount": current_amount,
			"cumulative_qty_after_bill": cumulative_qty,
			"cumulative_percent_after_bill": cumulative_percent,
			"remaining_qty_after_bill": remaining_qty,
			"remaining_percent_after_bill": remaining_percent,
			"transaction_date": _get_transaction_date(ra_bill),
			"docstatus_source": ra_bill.docstatus or 1,
		}
	)
	transaction.insert(ignore_permissions=True)
	return transaction


def _get_boq_item_billing_summary(boq, boq_item, current_ra_bill=None):
	boq_qty = _get_boq_item_qty(boq, boq_item)
	previous_qty = _get_previous_billed_qty(boq, boq_item, current_ra_bill)
	previous_percent = _qty_to_percent(previous_qty, boq_qty) if boq_qty > 0 else 0
	remaining_qty = max(0, boq_qty - previous_qty)
	remaining_percent = max(0, 100 - previous_percent) if boq_qty > 0 else 0

	return {
		"boq_qty": boq_qty,
		"previous_qty": previous_qty,
		"previous_percent": previous_percent,
		"remaining_qty": remaining_qty,
		"remaining_percent": remaining_percent,
	}


def _coerce_list(value):
	if not value:
		return []

	if isinstance(value, str):
		try:
			value = frappe.parse_json(value)
		except Exception:
			value = [item.strip() for item in value.split(",")]

	if isinstance(value, (list, tuple, set)):
		return [item for item in value if item]

	return [value]


@frappe.whitelist()
def get_boq_item_billing_summary(boq, boq_item, current_ra_bill=None):
	return _get_boq_item_billing_summary(boq, boq_item, current_ra_bill)


@frappe.whitelist()
def get_boq_item_previous_work(boq, boq_item, current_ra_bill=None):
	"""
	Return previous completed qty/percent and remaining qty/percent
	for selected BOQ Item in selected BOQ.
	"""
	return _get_boq_item_billing_summary(boq, boq_item, current_ra_bill)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_ra_bill_categories(doctype, txt, searchfield, start, page_len, filters, **kwargs):
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	filters = filters or {}
	boq = filters.get("boq")

	if not boq:
		return []

	txt = txt or ""
	like_txt = f"%{txt}%"
	prefix_txt = f"{txt}%"

	return frappe.db.sql(
		"""
		SELECT DISTINCT parent_cat.name, parent_cat.category_name
		FROM `tabBOQ Item` item
		JOIN `tabBOQ Category` sub_cat ON sub_cat.name = item.boq_category
		JOIN `tabBOQ Category` parent_cat
		  ON parent_cat.name = COALESCE(NULLIF(sub_cat.parent_node, ''), sub_cat.name)
		WHERE item.parent = %(boq)s
		  AND item.parenttype = 'BOQ'
		  AND item.parentfield = 'items'
		  AND (%(txt)s = ''
		    OR parent_cat.category_name LIKE %(like_txt)s
		    OR parent_cat.name LIKE %(like_txt)s)
		ORDER BY
		  CASE
		    WHEN parent_cat.category_name LIKE %(prefix_txt)s THEN 0
		    WHEN parent_cat.category_name LIKE %(like_txt)s THEN 1
		    WHEN parent_cat.name LIKE %(prefix_txt)s THEN 2
		    ELSE 3
		  END,
		  parent_cat.category_name ASC
		LIMIT %(start)s, %(page_len)s
		""",
		{
			"boq": boq,
			"txt": txt,
			"like_txt": like_txt,
			"prefix_txt": prefix_txt,
			"start": start,
			"page_len": page_len,
		},
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_ra_bill_subcategories(doctype, txt, searchfield, start, page_len, filters, **kwargs):
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	filters = filters or {}
	boq = filters.get("boq")
	category = filters.get("category")

	if not boq or not category:
		return []

	txt = txt or ""
	like_txt = f"%{txt}%"
	prefix_txt = f"{txt}%"

	return frappe.db.sql(
		"""
		SELECT DISTINCT sub_cat.name, sub_cat.category_name
		FROM `tabBOQ Item` item
		JOIN `tabBOQ Category` sub_cat ON sub_cat.name = item.boq_category
		WHERE item.parent = %(boq)s
		  AND item.parenttype = 'BOQ'
		  AND item.parentfield = 'items'
		  AND (sub_cat.parent_node = %(category)s OR sub_cat.name = %(category)s)
		  AND (%(txt)s = ''
		    OR sub_cat.category_name LIKE %(like_txt)s
		    OR sub_cat.name LIKE %(like_txt)s)
		ORDER BY
		  CASE
		    WHEN sub_cat.category_name LIKE %(prefix_txt)s THEN 0
		    WHEN sub_cat.category_name LIKE %(like_txt)s THEN 1
		    WHEN sub_cat.name LIKE %(prefix_txt)s THEN 2
		    ELSE 3
		  END,
		  sub_cat.category_name ASC
		LIMIT %(start)s, %(page_len)s
		""",
		{
			"boq": boq,
			"category": category,
			"txt": txt,
			"like_txt": like_txt,
			"prefix_txt": prefix_txt,
			"start": start,
			"page_len": page_len,
		},
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_boq_items_for_ra_bill(doctype, txt, searchfield, start, page_len, filters, **kwargs):
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	filters = filters or {}
	boq = filters.get("boq")
	subcategory = filters.get("subcategory")
	exclude_items = set(_coerce_list(filters.get("exclude_items")))
	current_ra_bill = filters.get("current_ra_bill")

	if not boq or not subcategory:
		return []

	txt = txt or ""
	like_txt = f"%{txt}%"
	prefix_txt = f"{txt}%"
	start = int(start or 0)
	page_len = int(page_len or 20)
	candidate_limit = max(start + page_len + 50, page_len)

	conditions = [
		"parent = %(boq)s",
		"parenttype = 'BOQ'",
		"parentfield = 'items'",
		"boq_category = %(subcategory)s",
		"(%(txt)s = '' OR item_name LIKE %(like_txt)s OR name LIKE %(like_txt)s)",
	]
	params = {
		"boq": boq,
		"subcategory": subcategory,
		"txt": txt,
		"like_txt": like_txt,
		"prefix_txt": prefix_txt,
		"candidate_limit": candidate_limit,
	}
	if exclude_items:
		conditions.append("name NOT IN %(exclude_items)s")
		params["exclude_items"] = tuple(exclude_items)

	candidates = frappe.db.sql(
		f"""
		SELECT name, item_name, qty, unit_rate, uom
		FROM `tabBOQ Item`
		WHERE {" AND ".join(conditions)}
		ORDER BY
		  CASE
		    WHEN item_name LIKE %(prefix_txt)s THEN 0
		    WHEN item_name LIKE %(like_txt)s THEN 1
		    WHEN name LIKE %(prefix_txt)s THEN 2
		    ELSE 3
		END,
		  item_name ASC
		LIMIT %(candidate_limit)s
		""",
		params,
	)

	available_items = []
	for name, item_name, qty, unit_rate, uom in candidates:
		previous_qty = _get_previous_billed_qty(boq, name, current_ra_bill)
		if previous_qty >= flt(qty) - OVERBILLING_TOLERANCE:
			continue

		available_items.append((name, item_name, qty, unit_rate, uom))

	return available_items[start : start + page_len]
