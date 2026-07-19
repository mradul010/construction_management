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


class SCBill(Document):
	def validate(self):
		self._sync_work_order_context()
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
			row.description = source.description
			row.assigned_qty = flt(source.assigned_qty)
			row.uom = source.uom
			row.sc_rate = flt(source.sc_rate)
			row.previous_qty = flt(summary.get("previous_qty"))
			row.previous_amount = flt(summary.get("previous_amount"))
			row.current_qty = flt(row.current_qty)
			if row.current_qty < 0:
				frappe.throw(_("Current Qty for {0} cannot be negative.").format(row.description))
			row.cumulative_qty = row.previous_qty + row.current_qty
			row.balance_qty = max(row.assigned_qty - row.cumulative_qty, 0)
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

	def _calculate_totals(self):
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
		if flt(self.net_payable) <= 0:
			frappe.throw(_("Net Payable must be greater than 0 to create a Purchase Invoice."))

		ensure_sc_bill_service_item()
		company = self.company or frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
		if not company:
			frappe.throw(_("Please set a Company before creating a Purchase Invoice."))

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

		row = {
			"item_code": "SC Bill Services",
			"item_name": "SC Bill Services",
			"description": item_description,
			"qty": 1,
			"rate": flt(self.net_payable),
			"uom": "Nos",
			"project": self.project,
		}
		expense_account = frappe.db.get_value("Company", company, "default_expense_account")
		if expense_account:
			row["expense_account"] = expense_account
		pi.append("items", row)

		if hasattr(pi, "set_missing_values"):
			pi.set_missing_values()
		if hasattr(pi, "calculate_taxes_and_totals"):
			pi.calculate_taxes_and_totals()
		pi.insert(ignore_permissions=True)

		self.db_set("purchase_invoice", pi.name)
		self.db_set("status", "Invoiced")
		update_sc_work_order_summary(self.sc_work_order)

		frappe.msgprint(
			_("Draft Purchase Invoice <b>{0}</b> created successfully.").format(pi.name),
			title=_("Purchase Invoice Created"),
			indicator="green",
		)
		return pi.name


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


def _get_bill_item_context(sc_work_order, row):
	summary = get_item_billing_summary(sc_work_order, row.name)
	return {
		"sc_work_order_item": row.name,
		"boq_item": row.boq_item,
		"description": row.description,
		"assigned_qty": flt(row.assigned_qty),
		"uom": row.uom,
		"sc_rate": flt(row.sc_rate),
		"previous_qty": flt(summary.get("previous_qty")),
		"previous_amount": flt(summary.get("previous_amount")),
	}
