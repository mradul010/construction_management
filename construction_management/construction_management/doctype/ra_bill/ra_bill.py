import frappe
from frappe.model.document import Document
from frappe.utils import flt


class RABill(Document):
	def validate(self):
		self._set_bill_no()
		self._fetch_boq_item_details()
		self._fill_prev_cumulative_qty()
		self._calculate_row_totals()
		self._calculate_header_totals()

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

	def _fill_prev_cumulative_qty(self):
		"""
		For each row, sum current_qty from all previous submitted
		RA Bills for the same project + boq + boq_item.
		Excludes the current document being saved.
		"""
		for row in self.items:
			if not row.boq_item:
				continue

			result = frappe.db.sql(
				"""
				SELECT COALESCE(SUM(rbi.current_qty), 0) AS total
				FROM `tabRA Bill Item` rbi
				JOIN `tabRA Bill` rb ON rb.name = rbi.parent
				WHERE rb.project = %s
				  AND rb.boq = %s
				  AND rbi.boq_item = %s
				  AND rb.docstatus = 1
				  AND rb.name != %s
				""",
				(self.project, self.boq, row.boq_item, self.name or "__new__"),
			)

			row.prev_cumulative_qty = result[0][0] if result else 0

	def _calculate_row_totals(self):
		"""
		Calculate current_qty and current_amount for each row from Work %.
		"""
		for row in self.items:
			row.work_percent = row.work_percent or 0
			row.current_qty = (row.boq_qty or 0) * (row.work_percent / 100)
			row.current_amount = (row.current_qty or 0) * (row.boq_rate or 0)

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

	def on_submit(self):
		self.db_set("status", "Submitted")

	def on_cancel(self):
		self.db_set("status", "Cancelled")

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

		period_str = ""
		if self.billing_period_from and self.billing_period_to:
			period_str = (
				f"{frappe.format(self.billing_period_from, {'fieldtype': 'Date'})} to "
				f"{frappe.format(self.billing_period_to, {'fieldtype': 'Date'})}"
			)

		category_labels = {}
		boq_item_codes = {}

		def get_category_label(category):
			if not category:
				return ""
			if category not in category_labels:
				category_labels[category] = (
					frappe.db.get_value("BOQ Category", category, "category_name") or category
				)
			return category_labels[category]

		def get_invoice_item_code(row):
			if not row.boq_item:
				return "RA Bill Services"

			if row.boq_item not in boq_item_codes:
				boq_item_code = frappe.db.get_value("BOQ Item", row.boq_item, "item")
				if boq_item_code and frappe.db.exists("Item", boq_item_code):
					boq_item_codes[row.boq_item] = boq_item_code
				else:
					boq_item_codes[row.boq_item] = "RA Bill Services"

			return boq_item_codes[row.boq_item]

		invoice_items = []
		for row in self.items:
			if not row.current_amount or row.current_amount <= 0:
				continue

			description_lines = [
				f"Category: {get_category_label(row.category_name)}",
				f"Sub Category: {get_category_label(row.sub_category)}",
				f"Item: {row.item_name or ''}",
				f"BOQ Qty: {flt(row.boq_qty)} {row.uom or ''}".strip(),
				f"BOQ Rate: {flt(row.boq_rate)}",
				f"Work Completed: {flt(row.work_percent)}%",
				f"Current Qty: {flt(row.current_qty)}",
				f"Amount: {flt(row.current_amount)}",
			]
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
					"item_code": get_invoice_item_code(row),
					"item_name": row.item_name or "RA Bill Services",
					"description": "\n".join(description_lines),
					"qty": 1,
					"rate": row.current_amount,
					"uom": "Nos",
					"income_account": income_account,
				}
			)

		if not invoice_items:
			frappe.throw("No RA Bill Items with a positive current amount were found to invoice.")

		invoice_gross = sum(flt(item.get("rate")) for item in invoice_items)
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

		si_data = {
			"doctype": "Sales Invoice",
			"company": company,
			"customer": self.customer,
			"debit_to": receivable_account,
			"project": self.project,
			"currency": invoice_currency,
			"conversion_rate": conversion_rate,
			"due_date": frappe.utils.add_days(frappe.utils.today(), 30),
			"remarks": f"Created from RA Bill {self.name}",
			"items": invoice_items,
		}

		if frappe.get_meta("Sales Invoice").has_field("ra_bill"):
			si_data["ra_bill"] = self.name

		try:
			si = frappe.get_doc(si_data)
			si.insert(ignore_permissions=True)
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

			si_data["items"] = fallback_items
			try:
				si = frappe.get_doc(si_data)
				si.insert(ignore_permissions=True)
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

	if not boq or not subcategory:
		return []

	txt = txt or ""
	like_txt = f"%{txt}%"
	prefix_txt = f"{txt}%"

	return frappe.db.sql(
		"""
		SELECT name, item_name, qty, unit_rate, uom
		FROM `tabBOQ Item`
		WHERE parent = %(boq)s
		  AND parenttype = 'BOQ'
		  AND parentfield = 'items'
		  AND boq_category = %(subcategory)s
		  AND (%(txt)s = '' OR item_name LIKE %(like_txt)s OR name LIKE %(like_txt)s)
		ORDER BY
		  CASE
		    WHEN item_name LIKE %(prefix_txt)s THEN 0
		    WHEN item_name LIKE %(like_txt)s THEN 1
		    WHEN name LIKE %(prefix_txt)s THEN 2
		    ELSE 3
		  END,
		  item_name ASC
		LIMIT %(start)s, %(page_len)s
		""",
		{
			"boq": boq,
			"subcategory": subcategory,
			"txt": txt,
			"like_txt": like_txt,
			"prefix_txt": prefix_txt,
			"start": start,
			"page_len": page_len,
		},
	)
