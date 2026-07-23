import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, today

from construction_management.construction_management.doctype.sc_work_order.sc_work_order import (
	TOLERANCE,
	get_item_billing_summary,
	get_submitted_bill_total,
	update_sc_work_order_summary,
)
from construction_management.construction_management.accounting_dimensions import (
	get_ra_bill_project_cost_center,
)
from construction_management.construction_management.utils.accounting import (
	apply_construction_accounts_to_purchase_invoice,
	get_construction_account,
)
from construction_management.construction_management.purchase_order import (
	get_purchase_order_contract_value,
	get_po_item_billing_summary,
	validate_purchase_order_for_sc_bill,
)


class SCBill(Document):
	def validate(self):
		self._sync_work_order_context()
		self._sync_purchase_order_context()
		self._set_bill_no()
		self._validate_header_values()
		self._sync_measured_items()
		self._calculate_totals()
		self._validate_bill_balance()

	def on_submit(self):
		self._validate_bill_balance()
		self.db_set("status", "Submitted")
		update_sc_work_order_summary(self.sc_work_order)

	def on_cancel(self):
		self.db_set("status", "Cancelled")
		update_sc_work_order_summary(self.sc_work_order)

	def _sync_work_order_context(self):
		if not self.sc_work_order:
			return

		work_order = frappe.db.get_value(
			"SC Work Order",
			self.sc_work_order,
			[
				"docstatus",
				"project",
				"supplier",
				"billing_type",
				"boq",
				"company",
				"currency",
				"contract_value",
			],
			as_dict=True,
		)
		if not work_order:
			frappe.throw(_("SC Work Order {0} does not exist.").format(self.sc_work_order))
		if work_order.docstatus != 1:
			frappe.throw(_("SC Work Order must be submitted before billing."))

		for fieldname in ("project", "supplier", "billing_type", "boq", "company", "currency"):
			self.set(fieldname, work_order.get(fieldname))
		self.contract_value = flt(work_order.contract_value)

	def _sync_purchase_order_context(self):
		if not self.purchase_order:
			return

		purchase_order = frappe.db.get_value(
			"Purchase Order",
			self.purchase_order,
			[
				"name",
				"docstatus",
				"supplier",
				"company",
				"project",
				"currency",
				"conversion_rate",
				"sc_work_order",
				"boq",
				"status",
			],
			as_dict=True,
		)
		if not purchase_order:
			frappe.throw(_("Purchase Order {0} does not exist.").format(self.purchase_order))
		if purchase_order.docstatus != 1:
			frappe.throw(_("Purchase Order must be submitted before billing."))
		if not purchase_order.sc_work_order:
			frappe.throw(_("Purchase Order {0} is not linked to an SC Work Order.").format(self.purchase_order))
		if self.sc_work_order and self.sc_work_order != purchase_order.sc_work_order:
			frappe.throw(
				_("Purchase Order {0} does not belong to SC Work Order {1}.").format(
					self.purchase_order,
					self.sc_work_order,
				)
			)

		validate_purchase_order_for_sc_bill(frappe.get_doc("Purchase Order", self.purchase_order))
		for fieldname in ("sc_work_order", "supplier", "company", "project", "currency", "boq"):
			if purchase_order.get(fieldname):
				self.set(fieldname, purchase_order.get(fieldname))
		self.contract_value = get_purchase_order_contract_value(self.purchase_order)

	def _set_bill_no(self):
		if self.bill_no or not self.sc_work_order:
			return

		last = frappe.db.get_all(
			"SC Bill",
			filters={"sc_work_order": self.sc_work_order, "name": ["!=", self.name]},
			fields=["bill_no"],
			order_by="bill_no desc",
			limit=1,
		)
		self.bill_no = (last[0].bill_no + 1) if last else 1

	def _validate_header_values(self):
		if flt(self.retention_percent) < 0 or flt(self.retention_percent) > 100:
			frappe.throw(_("Retention % must be between 0 and 100."))
		if flt(self.ld_deduction) < 0:
			frappe.throw(_("LD Deduction cannot be negative."))
		if flt(self.bill_amount) < 0:
			frappe.throw(_("Bill Amount cannot be negative."))

	def _sync_measured_items(self):
		if self.billing_type != "Measured":
			return
		if self.purchase_order:
			self._sync_purchase_order_items()
			return

		work_order = frappe.get_doc("SC Work Order", self.sc_work_order)
		work_order_items = {row.name: row for row in work_order.items}

		for row in self.items:
			if not row.sc_work_order_item:
				continue

			source = work_order_items.get(row.sc_work_order_item)
			if not source:
				frappe.throw(_("SC Work Order Item {0} is invalid.").format(row.sc_work_order_item))

			summary = get_item_billing_summary(
				self.sc_work_order,
				row.sc_work_order_item,
				self.name,
			)
			row.boq_item = source.boq_item
			row.item_code = source.item
			row.description = source.description
			row.assigned_qty = flt(source.assigned_qty)
			row.uom = source.uom
			row.sc_rate = flt(source.sc_rate)
			row.previous_qty = flt(summary.get("previous_qty"))
			row.previous_amount = flt(summary.get("previous_amount"))
			row.previous_percent = _qty_percent(row.previous_qty, row.assigned_qty)
			row.current_qty = flt(row.current_qty)
			if not row.current_qty and flt(row.get("current_percent")):
				row.current_qty = flt(row.assigned_qty) * (flt(row.current_percent) / 100)
			if row.current_qty < 0:
				frappe.throw(_("Current Qty for {0} cannot be negative.").format(row.description))
			if flt(row.get("current_percent")) < 0:
				frappe.throw(_("Current % for {0} cannot be negative.").format(row.description))
			row.cumulative_qty = row.previous_qty + row.current_qty
			row.balance_qty = max(row.assigned_qty - row.cumulative_qty, 0)
			row.current_percent = _qty_percent(row.current_qty, row.assigned_qty)
			row.cumulative_percent = _qty_percent(row.cumulative_qty, row.assigned_qty)
			row.balance_percent = max(100 - row.cumulative_percent, 0)
			row.current_amount = row.current_qty * row.sc_rate
			row.cumulative_amount = row.previous_amount + row.current_amount
			row.balance_amount = max((row.assigned_qty * row.sc_rate) - row.cumulative_amount, 0)
			row.bill_amount = row.current_amount

			if row.cumulative_qty > row.assigned_qty + TOLERANCE:
				frappe.throw(
					_("Current Qty for {0} exceeds remaining subcontract quantity.").format(
						row.description
					)
				)

	def _sync_purchase_order_items(self):
		purchase_order = frappe.get_doc("Purchase Order", self.purchase_order)
		purchase_order_items = {row.name: row for row in purchase_order.items}
		seen = set()

		for row in self.items:
			if not row.purchase_order_item:
				continue
			if row.purchase_order_item in seen:
				frappe.throw(
					_("Purchase Order Item {0} is duplicated in this SC Bill.").format(
						row.purchase_order_item
					)
				)
			seen.add(row.purchase_order_item)

			source = purchase_order_items.get(row.purchase_order_item)
			if not source:
				frappe.throw(_("Purchase Order Item {0} is invalid.").format(row.purchase_order_item))

			summary = get_po_item_billing_summary(
				self.purchase_order,
				row.purchase_order_item,
				self.name,
			)
			row.purchase_order = self.purchase_order
			row.sc_work_order_item = source.get("sc_work_order_item")
			row.boq_item = source.get("boq_item")
			row.item_code = source.item_code
			row.description = source.description or source.item_name or source.item_code
			row.assigned_qty = flt(source.qty)
			row.uom = source.uom
			row.sc_rate = flt(source.rate)
			row.cost_center = row.get("cost_center") or source.get("cost_center")
			row.previous_qty = flt(summary.get("previous_qty"))
			row.previous_amount = flt(summary.get("previous_amount"))
			row.previous_percent = _qty_percent(row.previous_qty, row.assigned_qty)
			row.current_qty = flt(row.current_qty)
			if not row.current_qty and flt(row.get("current_percent")):
				row.current_qty = flt(row.assigned_qty) * (flt(row.current_percent) / 100)
			if row.current_qty < 0:
				frappe.throw(_("Current Qty for {0} cannot be negative.").format(row.description))
			if flt(row.get("current_percent")) < 0:
				frappe.throw(_("Current % for {0} cannot be negative.").format(row.description))

			row.cumulative_qty = row.previous_qty + row.current_qty
			row.balance_qty = max(row.assigned_qty - row.cumulative_qty, 0)
			row.current_percent = _qty_percent(row.current_qty, row.assigned_qty)
			row.cumulative_percent = _qty_percent(row.cumulative_qty, row.assigned_qty)
			row.balance_percent = max(100 - row.cumulative_percent, 0)
			row.current_amount = row.current_qty * row.sc_rate
			row.cumulative_amount = row.previous_amount + row.current_amount
			row.balance_amount = max((row.assigned_qty * row.sc_rate) - row.cumulative_amount, 0)
			row.bill_amount = row.current_amount

			if row.cumulative_qty > row.assigned_qty + TOLERANCE:
				frappe.throw(
					_("Current Qty for {0} cannot exceed remaining Purchase Order quantity.").format(
						row.description
					)
				)
			if flt(row.cumulative_percent) > 100 + TOLERANCE:
				frappe.throw(
					_("Current % for {0} cannot exceed remaining Purchase Order percentage.").format(
						row.description
					)
				)
			if row.cumulative_amount > (flt(row.assigned_qty) * flt(row.sc_rate)) + TOLERANCE:
				frappe.throw(
					_("Current Amount for {0} cannot exceed remaining Purchase Order amount.").format(
						row.description
					)
				)
			if flt(row.cumulative_percent) > 100 + TOLERANCE:
				frappe.throw(
					_("Current % for {0} exceeds remaining subcontract percentage.").format(
						row.description
					)
				)
			if row.cumulative_amount > (flt(row.assigned_qty) * flt(row.sc_rate)) + TOLERANCE:
				frappe.throw(
					_("Current Amount for {0} exceeds remaining subcontract amount.").format(
						row.description
					)
				)

	def _calculate_totals(self):
		if self.purchase_order:
			from construction_management.construction_management.purchase_order import (
				get_submitted_sc_bill_total,
			)

			self.previous_billed = get_submitted_sc_bill_total(self.purchase_order, self.name)
		else:
			self.previous_billed = get_submitted_bill_total(self.sc_work_order, self.name)
		if self.billing_type == "Measured":
			if not self.items:
				frappe.throw(_("Please add at least one measured bill item."))
			self.gross_amount = sum(flt(row.current_amount) for row in self.items)
			self.bill_amount = self.gross_amount
		else:
			self.gross_amount = flt(self.bill_amount)

		self.retention_amount = self.gross_amount * (flt(self.retention_percent) / 100)
		self.net_payable = self.gross_amount - self.retention_amount - flt(self.ld_deduction)
		self.cumulative_billed = self.previous_billed + self.gross_amount
		self.balance_amount = max(flt(self.contract_value) - self.cumulative_billed, 0)

	def _validate_bill_balance(self):
		if flt(self.gross_amount) <= 0:
			frappe.throw(_("Gross Amount must be greater than 0."))
		if flt(self.net_payable) < 0:
			frappe.throw(_("Net Payable cannot be negative."))
		if flt(self.cumulative_billed) > flt(self.contract_value) + TOLERANCE:
			frappe.throw(_("Cumulative billing cannot exceed Contract Value."))

	@frappe.whitelist()
	def approve(self):
		if self.docstatus != 1:
			frappe.throw(_("Only submitted SC Bills can be approved."))
		if self.status == "Approved":
			return self.name
		if self.status != "Submitted":
			frappe.throw(_("SC Bill must be Submitted before approval. Current status: {0}").format(self.status))

		self.db_set("status", "Approved")
		return self.name

	@frappe.whitelist()
	def create_purchase_invoice(self):
		if self.status != "Approved":
			frappe.throw(_("SC Bill must be Approved before creating a Purchase Invoice."))
		if self.purchase_invoice:
			frappe.throw(_("Purchase Invoice {0} already exists for this SC Bill.").format(self.purchase_invoice))
		if not self.supplier:
			frappe.throw(_("Supplier is required to create a Purchase Invoice."))
		if flt(self.gross_amount) <= 0:
			frappe.throw(_("Gross Amount must be greater than 0 to create a Purchase Invoice."))

		ensure_sc_bill_service_item()
		company = self.company or frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
		if not company:
			frappe.throw(_("Please set a Company before creating a Purchase Invoice."))

		project_cost_center = get_ra_bill_project_cost_center(
			project=self.project,
			company=company,
		)

		item_description = "\n".join(
			filter(
				None,
				[
					_("SC Bill: {0}").format(self.name),
					_("SC Work Order: {0}").format(self.sc_work_order),
					_("Project: {0}").format(self.project),
					_("Billing Type: {0}").format(self.billing_type),
					self.billing_remarks,
				],
			)
		)
		pi = frappe.new_doc("Purchase Invoice")
		pi.supplier = self.supplier
		pi.company = company
		pi.currency = self.currency
		pi.conversion_rate = 1
		pi.posting_date = self.billing_period_to or today()
		pi.due_date = add_days(pi.posting_date, 30)
		pi.project = self.project
		pi.remarks = self.remarks or _("Created from SC Bill {0}").format(self.name)
		_set_if_exists(pi, "cost_center", project_cost_center)
		if pi.meta.has_field("sc_bill"):
			pi.sc_bill = self.name
		if pi.meta.has_field("sc_work_order"):
			pi.sc_work_order = self.sc_work_order
		if pi.meta.has_field("purchase_order"):
			pi.purchase_order = self.purchase_order

		expense_account = get_construction_account(
			company,
			"subcontract_expense",
			project=self.project,
			transaction=self,
		)
		for row in self._get_purchase_invoice_items(
			expense_account,
			project_cost_center,
			item_description,
		):
			pi.append("items", row)

		apply_construction_accounts_to_purchase_invoice(pi)
		if hasattr(pi, "set_missing_values"):
			pi.set_missing_values()
		apply_construction_accounts_to_purchase_invoice(pi)
		if hasattr(pi, "calculate_taxes_and_totals"):
			pi.calculate_taxes_and_totals()
		pi.insert(ignore_permissions=True)

		self.db_set("purchase_invoice", pi.name)
		self.db_set("status", "Invoiced")
		if flt(self.retention_amount) > 0:
			from construction_management.construction_management.doctype.retention_payable.retention_payable import (
				sync_from_sc_bill,
			)

			sync_from_sc_bill(self, purchase_invoice=pi.name)
		update_sc_work_order_summary(self.sc_work_order)

		frappe.msgprint(
			_("Draft Purchase Invoice <b>{0}</b> created successfully.").format(pi.name),
			title=_("Purchase Invoice Created"),
			indicator="green",
		)
		return pi.name

	def _get_purchase_invoice_items(self, expense_account, cost_center, fallback_description):
		if self.billing_type != "Measured":
			return [
				_filter_child_fields(
					"Purchase Invoice Item",
					{
						"item_code": "SC Bill Services",
						"item_name": "SC Bill Services",
						"description": fallback_description,
						"qty": 1,
						"rate": flt(self.gross_amount),
						"uom": "Nos",
						"project": self.project,
						"cost_center": cost_center,
						"expense_account": expense_account,
						"purchase_order": self.purchase_order,
					},
				)
			]

		items = []
		for row in self.items:
			qty = flt(row.current_qty)
			amount = flt(row.current_amount)
			rate = flt(row.sc_rate)
			if qty <= 0 or amount <= 0:
				continue

			description = "\n".join(
				filter(
					None,
					[
						row.description,
						_("SC Bill: {0}").format(self.name),
						_("SC Work Order: {0}").format(self.sc_work_order),
						_("BOQ Item: {0}").format(row.boq_item) if row.boq_item else None,
						_("Current Qty: {0} {1}").format(qty, row.uom or "").strip(),
						_("Current %: {0}").format(flt(row.get("current_percent"), 4)),
						_("Project: {0}").format(self.project) if self.project else None,
					],
				)
			)
			item_code = row.get("item_code") or "SC Bill Services"
			if row.get("purchase_order_item"):
				item_code = frappe.db.get_value("Purchase Order Item", row.purchase_order_item, "item_code") or item_code
			items.append(
				_filter_child_fields(
					"Purchase Invoice Item",
					{
						"item_code": item_code,
						"item_name": row.description or item_code,
						"description": description,
						"qty": qty,
						"rate": rate,
						"uom": row.uom or "Nos",
						"project": self.project,
						"cost_center": row.get("cost_center") or cost_center,
						"expense_account": expense_account,
						"purchase_order": row.get("purchase_order") or self.purchase_order,
						"po_detail": row.get("purchase_order_item"),
						"sc_work_order_item": row.get("sc_work_order_item"),
						"sc_bill_item": row.name,
						"boq_item": row.get("boq_item"),
					},
				)
			)

		if not items:
			frappe.throw(_("No SC Bill Items with a positive current amount were found to invoice."))

		item_total = sum(flt(item.get("qty")) * flt(item.get("rate")) for item in items)
		if flt(item_total, 2) != flt(self.gross_amount, 2):
			frappe.throw(
				_(
					"Detailed SC Bill item total does not match Gross Amount. "
					"Item total: {0}, Gross amount: {1}."
				).format(
					frappe.format_value(item_total, {"fieldtype": "Currency"}),
					frappe.format_value(self.gross_amount, {"fieldtype": "Currency"}),
				)
			)

		return items


def ensure_sc_bill_service_item():
	if frappe.db.exists("Item", "SC Bill Services"):
		return

	item_data = {
		"doctype": "Item",
		"item_code": "SC Bill Services",
		"item_name": "SC Bill Services",
		"description": "Service item for subcontract bills",
		"item_group": get_sc_bill_service_item_group(),
		"stock_uom": "Nos",
		"is_stock_item": 0,
		"is_purchase_item": 1,
		"is_sales_item": 0,
	}
	item_meta = frappe.get_meta("Item")
	if item_meta.has_field("boq_main_category"):
		item_data["boq_main_category"] = get_sc_bill_service_boq_category()

	item = frappe.get_doc(item_data)
	item.insert(ignore_permissions=True)


def get_sc_bill_service_item_group():
	if frappe.db.exists("Item Group", "Services"):
		return "Services"

	item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
	if not item_group:
		frappe.throw(_("Please create an Item Group before creating SC Bill Purchase Invoices."))

	return item_group


def get_sc_bill_service_boq_category():
	category = frappe.db.get_value("BOQ Category", {}, "name", order_by="name asc")
	if not category:
		frappe.throw(_("Please create a BOQ Category before creating SC Bill Purchase Invoices."))

	return category


@frappe.whitelist()
def get_work_order_context(sc_work_order):
	if not sc_work_order:
		return {}

	doc = frappe.get_doc("SC Work Order", sc_work_order)
	return {
		"project": doc.project,
		"supplier": doc.supplier,
		"billing_type": doc.billing_type,
		"boq": doc.boq,
		"company": doc.company,
		"currency": doc.currency,
		"contract_value": doc.contract_value,
		"items": [
			_get_bill_item_context(doc.name, row)
			for row in doc.items
		],
	}


@frappe.whitelist()
def get_purchase_order_context(purchase_order):
	if not purchase_order:
		return {}

	doc = frappe.get_doc("Purchase Order", purchase_order)
	validate_purchase_order_for_sc_bill(doc)
	billing_type = frappe.db.get_value("SC Work Order", doc.sc_work_order, "billing_type") or "Measured"
	return {
		"purchase_order": doc.name,
		"sc_work_order": doc.sc_work_order,
		"project": doc.project,
		"supplier": doc.supplier,
		"billing_type": billing_type,
		"boq": doc.get("boq"),
		"company": doc.company,
		"currency": doc.currency,
		"contract_value": get_purchase_order_contract_value(doc.name),
		"items": [
			_get_purchase_order_bill_item_context(doc.name, row)
			for row in doc.items
		],
	}


def _get_bill_item_context(sc_work_order, row):
	summary = get_item_billing_summary(sc_work_order, row.name)
	previous_qty = flt(summary.get("previous_qty"))
	assigned_qty = flt(row.assigned_qty)
	return {
		"sc_work_order_item": row.name,
		"boq_item": row.boq_item,
		"description": row.description,
		"assigned_qty": assigned_qty,
		"uom": row.uom,
		"sc_rate": flt(row.sc_rate),
		"previous_qty": previous_qty,
		"previous_percent": _qty_percent(previous_qty, assigned_qty),
		"previous_amount": flt(summary.get("previous_amount")),
		"balance_qty": max(assigned_qty - previous_qty, 0),
		"balance_percent": max(100 - _qty_percent(previous_qty, assigned_qty), 0),
	}


def _get_purchase_order_bill_item_context(purchase_order, row):
	summary = get_po_item_billing_summary(purchase_order, row.name)
	previous_qty = flt(summary.get("previous_qty"))
	assigned_qty = flt(row.qty)
	previous_percent = _qty_percent(previous_qty, assigned_qty)
	return {
		"purchase_order": purchase_order,
		"purchase_order_item": row.name,
		"sc_work_order_item": row.get("sc_work_order_item"),
		"boq_item": row.get("boq_item"),
		"item_code": row.item_code,
		"description": row.description or row.item_name or row.item_code,
		"assigned_qty": assigned_qty,
		"uom": row.uom,
		"sc_rate": flt(row.rate),
		"previous_qty": previous_qty,
		"previous_percent": previous_percent,
		"previous_amount": flt(summary.get("previous_amount")),
		"balance_qty": max(assigned_qty - previous_qty, 0),
		"balance_percent": max(100 - previous_percent, 0),
		"cost_center": row.get("cost_center"),
	}


def _qty_percent(qty, total_qty):
	total_qty = flt(total_qty)
	return flt((flt(qty) / total_qty) * 100) if total_qty else 0


def _set_if_exists(doc, fieldname, value):
	if doc.meta.has_field(fieldname) and value not in (None, ""):
		doc.set(fieldname, value)


def _filter_child_fields(doctype, row):
	meta = frappe.get_meta(doctype)
	return {
		fieldname: value
		for fieldname, value in row.items()
		if meta.has_field(fieldname) and value not in (None, "")
	}
