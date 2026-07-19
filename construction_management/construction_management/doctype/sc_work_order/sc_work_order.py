import frappe
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.model.document import Document
from frappe.utils import flt


VALID_SCOPE_TYPES = {"BOQ Linked", "Standalone"}
VALID_BILLING_TYPES = {"Measured", "Milestone", "Lump Sum"}
TOLERANCE = 0.0001


class SCWorkOrder(Document):
	def validate(self):
		self._sync_boq_context()
		self._validate_header()
		self._fetch_boq_item_details()
		self._calculate_item_totals()
		self._validate_items()
		self.calculate_totals()

	def on_submit(self):
		self.db_set("status", "Submitted")

	def on_cancel(self):
		self.db_set("status", "Cancelled")
		update_sc_work_order_summary(self.name)

	def _sync_boq_context(self):
		if self.scope_type != "BOQ Linked" or not self.boq:
			return

		boq = frappe.db.get_value(
			"BOQ",
			self.boq,
			["project", "company", "currency"],
			as_dict=True,
		)
		if not boq:
			frappe.throw(_("BOQ {0} does not exist.").format(self.boq))

		for fieldname, label in (
			("project", _("Project")),
			("company", _("Company")),
			("currency", _("Currency")),
		):
			value = boq.get(fieldname)
			if self.get(fieldname) and value and self.get(fieldname) != value:
				frappe.throw(_("SC Work Order {0} must match BOQ {0}.").format(label))
			if value and not self.get(fieldname):
				self.set(fieldname, value)

	def _validate_header(self):
		if self.scope_type not in VALID_SCOPE_TYPES:
			frappe.throw(_("Invalid Scope Type: {0}").format(self.scope_type))

		if self.billing_type not in VALID_BILLING_TYPES:
			frappe.throw(_("Invalid Billing Type: {0}").format(self.billing_type))

		if self.scope_type == "BOQ Linked" and not self.boq:
			frappe.throw(_("BOQ Linked subcontract work orders require a BOQ."))

		if self.scope_type == "Standalone" and self.boq:
			frappe.throw(_("Standalone subcontract work orders cannot be linked to a BOQ."))

		if flt(self.standalone_contract_value) < 0:
			frappe.throw(_("Standalone Contract Value cannot be negative."))

	def _fetch_boq_item_details(self):
		if self.scope_type != "BOQ Linked":
			return

		for row in self.items:
			if not row.boq_item:
				continue

			boq_item = frappe.db.get_value(
				"BOQ Item",
				{
					"name": row.boq_item,
					"parent": self.boq,
					"parenttype": "BOQ",
				},
				[
					"item",
					"item_name",
					"qty",
					"uom",
					"unit_rate",
					"boq_category",
					"boq_item_key",
					"component_key",
				],
				as_dict=True,
			)
			if not boq_item:
				frappe.throw(
					_("BOQ Item {0} does not belong to BOQ {1}.").format(
						row.boq_item, self.boq
					)
				)

			row.item = boq_item.item
			row.description = row.description or boq_item.item_name or boq_item.item or row.boq_item
			row.boq_qty = flt(boq_item.qty)
			row.uom = boq_item.uom
			row.boq_rate = flt(boq_item.unit_rate)
			row.category = boq_item.boq_category
			row.boq_item_key = boq_item.boq_item_key or boq_item.component_key or row.boq_item
			if not row.assigned_qty:
				row.assigned_qty = row.boq_qty
			if not row.sc_rate:
				row.sc_rate = row.boq_rate

	def _calculate_item_totals(self):
		for row in self.items:
			row.assigned_qty = flt(row.assigned_qty)
			row.boq_qty = flt(row.boq_qty)
			row.boq_rate = flt(row.boq_rate)
			row.sc_rate = flt(row.sc_rate)
			row.boq_amount = row.assigned_qty * row.boq_rate
			row.sc_amount = row.assigned_qty * row.sc_rate
			row.margin_amount = row.boq_amount - row.sc_amount
			row.margin_percent = (row.margin_amount / row.boq_amount * 100) if row.boq_amount else 0

	def _validate_items(self):
		if self.scope_type == "BOQ Linked" and not self.items:
			frappe.throw(_("Please add at least one BOQ scope item."))

		seen = set()
		for row in self.items:
			label = row.description or row.boq_item or row.idx

			if flt(row.assigned_qty) < 0:
				frappe.throw(_("Assigned Qty for {0} cannot be negative.").format(label))
			if flt(row.sc_rate) < 0:
				frappe.throw(_("Subcontract Rate for {0} cannot be negative.").format(label))

			if self.scope_type == "Standalone":
				if row.boq_item:
					frappe.throw(_("Standalone contracts cannot contain BOQ items."))
				continue

			if not row.boq_item:
				frappe.throw(_("BOQ Item is required for BOQ Linked contracts."))
			if row.boq_item in seen:
				frappe.throw(_("Duplicate BOQ Item found: {0}.").format(row.boq_item))
			seen.add(row.boq_item)

			if flt(row.assigned_qty) <= 0:
				frappe.throw(_("Assigned Qty for {0} must be greater than 0.").format(label))
			if flt(row.boq_qty) <= 0:
				frappe.throw(_("BOQ Qty for {0} must be greater than 0.").format(label))
			if flt(row.assigned_qty) > flt(row.boq_qty) + TOLERANCE:
				frappe.throw(
					_("Assigned Qty for {0} cannot exceed BOQ Qty {1}.").format(
						label, flt(row.boq_qty, 4)
					)
				)

	def calculate_totals(self):
		if self.scope_type == "Standalone":
			self.boq_amount = 0
			self.sc_amount = flt(self.standalone_contract_value)
			self.margin_amount = 0
			self.margin_percent = 0
			self.contract_value = self.sc_amount
		else:
			self.boq_amount = sum(flt(row.boq_amount) for row in self.items)
			self.sc_amount = sum(flt(row.sc_amount) for row in self.items)
			self.margin_amount = self.boq_amount - self.sc_amount
			self.margin_percent = (
				(self.margin_amount / self.boq_amount * 100) if self.boq_amount else 0
			)
			self.contract_value = self.sc_amount

		previous_total = get_submitted_bill_total(self.name)
		self.total_billed = previous_total
		self.balance_amount = max(flt(self.contract_value) - previous_total, 0)

		if self.docstatus == 1 and self.status != "Cancelled":
			if self.balance_amount <= TOLERANCE and self.contract_value:
				self.status = "Completed"
			elif self.total_billed > TOLERANCE:
				self.status = "Billing In Progress"
			else:
				self.status = "Submitted"


def get_submitted_bill_total(sc_work_order, exclude_bill=None):
	if not sc_work_order:
		return 0

	conditions = [
		"sc_work_order = %(sc_work_order)s",
		"docstatus = 1",
		"status != 'Cancelled'",
	]
	values = {"sc_work_order": sc_work_order}
	if exclude_bill:
		conditions.append("name != %(exclude_bill)s")
		values["exclude_bill"] = exclude_bill

	result = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(gross_amount), 0)
		FROM `tabSC Bill`
		WHERE {" AND ".join(conditions)}
		""",
		values,
	)
	return flt(result[0][0] if result else 0)


def get_item_billing_summary(sc_work_order, sc_work_order_item, exclude_bill=None):
	if not sc_work_order or not sc_work_order_item:
		return {"previous_qty": 0, "previous_amount": 0}

	conditions = [
		"bill.sc_work_order = %(sc_work_order)s",
		"bill.docstatus = 1",
		"bill.status != 'Cancelled'",
		"item.sc_work_order_item = %(sc_work_order_item)s",
	]
	values = {
		"sc_work_order": sc_work_order,
		"sc_work_order_item": sc_work_order_item,
	}
	if exclude_bill:
		conditions.append("bill.name != %(exclude_bill)s")
		values["exclude_bill"] = exclude_bill

	result = frappe.db.sql(
		f"""
		SELECT
			COALESCE(SUM(item.current_qty), 0) AS previous_qty,
			COALESCE(SUM(item.current_amount), 0) AS previous_amount
		FROM `tabSC Bill Item` item
		INNER JOIN `tabSC Bill` bill ON bill.name = item.parent
		WHERE {" AND ".join(conditions)}
		""",
		values,
		as_dict=True,
	)
	return result[0] if result else {"previous_qty": 0, "previous_amount": 0}


def update_sc_work_order_summary(sc_work_order):
	if not sc_work_order or not frappe.db.exists("SC Work Order", sc_work_order):
		return

	doc = frappe.get_doc("SC Work Order", sc_work_order)
	doc.calculate_totals()
	frappe.db.set_value(
		"SC Work Order",
		sc_work_order,
		{
			"boq_amount": doc.boq_amount,
			"sc_amount": doc.sc_amount,
			"margin_amount": doc.margin_amount,
			"contract_value": doc.contract_value,
			"total_billed": doc.total_billed,
			"balance_amount": doc.balance_amount,
			"margin_percent": doc.margin_percent,
			"status": doc.status,
		},
		update_modified=False,
	)


@frappe.whitelist()
def get_boq_item_details(boq, boq_item):
	if not boq or not boq_item:
		return {}

	item = frappe.db.get_value(
		"BOQ Item",
		{"name": boq_item, "parent": boq, "parenttype": "BOQ"},
		[
			"name",
			"item",
			"item_name",
			"qty",
			"uom",
			"unit_rate",
			"boq_category",
			"boq_item_key",
			"component_key",
		],
		as_dict=True,
	)
	if not item:
		return {}

	return {
		"boq_item": item.name,
		"item": item.item,
		"description": item.item_name or item.item,
		"boq_qty": flt(item.qty),
		"assigned_qty": flt(item.qty),
		"uom": item.uom,
		"boq_rate": flt(item.unit_rate),
		"sc_rate": flt(item.unit_rate),
		"category": item.boq_category,
		"boq_item_key": item.boq_item_key or item.component_key or item.name,
	}


@frappe.whitelist()
def make_sc_bill(source_name, target_doc=None):
	def set_missing_values(source, target):
		target.sc_work_order = source.name
		target.project = source.project
		target.supplier = source.supplier
		target.billing_type = source.billing_type
		target.boq = source.boq
		target.company = source.company
		target.currency = source.currency
		target.contract_value = source.contract_value
		target.previous_billed = get_submitted_bill_total(source.name)
		target.status = "Draft"

		if source.billing_type != "Measured":
			target.items = []

	def update_item(source, target, source_parent):
		summary = get_item_billing_summary(source_parent.name, source.name)
		previous_qty = flt(summary.get("previous_qty"))
		previous_amount = flt(summary.get("previous_amount"))
		target.sc_work_order_item = source.name
		target.boq_item = source.boq_item
		target.description = source.description
		target.assigned_qty = source.assigned_qty
		target.uom = source.uom
		target.sc_rate = source.sc_rate
		target.previous_qty = previous_qty
		target.previous_amount = previous_amount
		target.cumulative_qty = previous_qty
		target.balance_qty = max(flt(source.assigned_qty) - previous_qty, 0)
		target.cumulative_amount = previous_amount
		target.balance_amount = max(flt(source.sc_amount) - previous_amount, 0)

	return get_mapped_doc(
		"SC Work Order",
		source_name,
		{
			"SC Work Order": {
				"doctype": "SC Bill",
				"field_map": {
					"name": "sc_work_order",
					"project": "project",
					"supplier": "supplier",
					"billing_type": "billing_type",
					"boq": "boq",
					"company": "company",
					"currency": "currency",
					"contract_value": "contract_value",
				},
				"validation": {"docstatus": ["=", 1]},
			},
			"SC Work Order Item": {
				"doctype": "SC Bill Item",
				"field_map": {
					"name": "sc_work_order_item",
					"boq_item": "boq_item",
					"description": "description",
					"assigned_qty": "assigned_qty",
					"uom": "uom",
					"sc_rate": "sc_rate",
				},
				"postprocess": update_item,
			},
		},
		target_doc,
		set_missing_values,
	)


@frappe.whitelist()
def search_boq_items(doctype, txt, searchfield, start, page_len, filters):
	boq = (filters or {}).get("boq")
	if not boq:
		return []

	return frappe.db.sql(
		"""
		SELECT name, item_name
		FROM `tabBOQ Item`
		WHERE parent = %(boq)s
		  AND parenttype = 'BOQ'
		  AND ({searchfield} LIKE %(txt)s OR item_name LIKE %(txt)s OR item LIKE %(txt)s)
		ORDER BY idx
		LIMIT %(start)s, %(page_len)s
		""".format(searchfield=searchfield),
		{"boq": boq, "txt": f"%{txt}%", "start": start, "page_len": page_len},
	)
