import frappe
from frappe.model.document import Document


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
				["item_name", "qty", "unit_rate", "uom"],
				as_dict=True,
			)
			if boq_item:
				row.item_name = boq_item.item_name
				row.boq_qty = boq_item.qty
				row.boq_rate = boq_item.unit_rate
				row.uom = boq_item.uom

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
		Calculate cumulative_qty, completion_pct, current_amount
		for each row.
		"""
		for row in self.items:
			row.cumulative_qty = (row.prev_cumulative_qty or 0) + (row.current_qty or 0)

			if row.boq_qty and row.boq_qty > 0:
				row.completion_pct = (row.cumulative_qty / row.boq_qty) * 100
			else:
				row.completion_pct = 0

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
	def create_sales_invoice(self):
		"""
		Called when PM clicks the "Create Sales Invoice" button.
		Creates a Sales Invoice with one line for net_payable amount.
		Sets status to Invoiced and links the Sales Invoice back.
		"""
		if self.status != "Approved":
			frappe.throw("RA Bill must be Approved before creating a Sales Invoice.")

		if self.sales_invoice:
			frappe.throw(f"Sales Invoice {self.sales_invoice} already exists for this RA Bill.")

		if not frappe.db.exists("Item", "RA Bill Services"):
			item = frappe.get_doc({
				"doctype": "Item",
				"item_code": "RA Bill Services",
				"item_name": "RA Bill Services",
				"item_group": "Services",
				"stock_uom": "Nos",
				"is_stock_item": 0,
			})
			item.insert(ignore_permissions=True)

		si = frappe.get_doc({
			"doctype": "Sales Invoice",
			"customer": self.customer,
			"project": self.project,
			"currency": self.currency,
			"due_date": frappe.utils.add_days(frappe.utils.today(), 30),
			"items": [{
				"item_code": "RA Bill Services",
				"item_name": "RA Bill Services",
				"description": (
					f"RA Bill #{self.bill_no} | "
					f"{self.billing_period_from} to {self.billing_period_to} | "
					f"Project: {self.project} | BOQ: {self.boq}"
				),
				"qty": 1,
				"rate": self.net_payable,
				"uom": "Nos",
			}],
		})

		si.insert(ignore_permissions=True)

		self.db_set("sales_invoice", si.name)
		self.db_set("status", "Invoiced")

		frappe.msgprint(
			f"Sales Invoice {si.name} created successfully.",
			alert=True,
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
