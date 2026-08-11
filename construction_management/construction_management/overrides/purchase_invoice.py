import frappe
from frappe import _
from frappe.utils import flt

from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import PurchaseInvoice
from erpnext.accounts.utils import get_account_currency

from construction_management.construction_management.utils.accounting import get_construction_account


AMOUNT_TOLERANCE = 0.0001


class ConstructionPurchaseInvoice(PurchaseInvoice):
	def validate(self):
		super().validate()
		self.validate_retention_account_for_submit()
		self.validate_site_material_consumption_on_submit()
		self.set_payment_breakdown()

	def on_submit(self):
		super().on_submit()
		self.create_site_material_consumption_on_submit()

	def on_cancel(self):
		self.cancel_site_material_consumption()
		super().on_cancel()

	def make_supplier_gl_entry(self, gl_entries):
		retention_context = self.get_retention_payable_accounting_context()
		if not retention_context:
			super().make_supplier_gl_entry(gl_entries)
			return

		against_voucher = self.name
		if self.is_return and self.return_against and not self.update_outstanding_for_self:
			against_voucher = self.return_against

		for row in self.get_retention_payable_gl_rows(retention_context, against_voucher):
			gl_entries.append(row)

	def validate_retention_account_for_submit(self):
		if getattr(self, "_action", None) != "submit":
			return

		if not self.get_retention_payable_accounting_context(validate_account=False):
			return

		if not self.credit_to:
			frappe.throw(_("Trade Payable Account is required before submitting Purchase Invoice."))

		if not frappe.get_cached_value("Company", self.company, "default_subcontractor_retention_payable_account"):
			frappe.throw(
				_(
					"Default Subcontractor Retention Payable Account is not configured in Company -> "
					"Construction Accounting Settings."
				)
			)

		get_construction_account(
			self.company,
			"subcontractor_retention_payable",
			project=self.project,
			transaction=self,
		)

	def validate_site_material_consumption_on_submit(self):
		if not self.should_consume_site_materials():
			return

		if self.is_return:
			frappe.throw(_("Site materials cannot be auto-consumed from a return Purchase Invoice."))

		if not self.update_stock:
			frappe.throw(_("Enable Update Stock before consuming site materials from Purchase Invoice."))

		if self.get("site_material_consumption"):
			return

		rows = self.get_site_material_consumption_rows()
		if not rows:
			frappe.throw(_("No stock item rows are available to consume."))

		projects = {row.project for row in rows if row.project}
		warehouses = {row.warehouse for row in rows if row.warehouse}
		missing_project_rows = [row.idx for row in rows if not row.project]
		missing_warehouse_rows = [row.idx for row in rows if not row.warehouse]

		if missing_project_rows:
			frappe.throw(
				_("Project is required on Purchase Invoice item rows before site material consumption. Missing rows: {0}").format(
					", ".join(str(idx) for idx in missing_project_rows)
				)
			)
		if missing_warehouse_rows:
			frappe.throw(
				_("Warehouse is required on Purchase Invoice item rows before site material consumption. Missing rows: {0}").format(
					", ".join(str(idx) for idx in missing_warehouse_rows)
				)
			)
		if len(projects) > 1:
			frappe.throw(_("Auto site material consumption supports one Project per Purchase Invoice."))
		if len(warehouses) > 1:
			frappe.throw(_("Auto site material consumption supports one Site Warehouse per Purchase Invoice."))

	def should_consume_site_materials(self):
		return bool(
			self.meta.has_field("consume_site_materials_on_submit")
			and self.get("consume_site_materials_on_submit")
		)

	def get_site_material_consumption_rows(self):
		rows = []
		for row in self.get("items") or []:
			if not row.item_code or flt(row.qty) <= 0:
				continue
			item_values = frappe.db.get_value(
				"Item",
				row.item_code,
				["is_stock_item", "disabled"],
				as_dict=True,
			)
			if not item_values or not item_values.is_stock_item or item_values.disabled:
				continue

			rows.append(
				frappe._dict(
					{
						"idx": row.idx,
						"item_code": row.item_code,
						"item_name": row.item_name,
						"description": row.description,
						"qty": row.qty,
						"uom": row.uom,
						"stock_uom": row.stock_uom,
						"conversion_factor": row.conversion_factor or 1,
						"warehouse": row.warehouse,
						"project": row.project or self.project,
						"cost_center": row.cost_center or self.cost_center,
						"expense_account": self.get_site_material_consumption_expense_account(row.item_code),
					}
				)
			)
		return rows

	def create_site_material_consumption_on_submit(self):
		if not self.should_consume_site_materials():
			return

		if self.get("site_material_consumption"):
			consumption = frappe.get_doc("Site Material Consumption", self.get("site_material_consumption"))
			if consumption.docstatus == 1:
				return
			if consumption.docstatus == 0:
				consumption.flags.ignore_permissions = True
				consumption.submit()
				return
			frappe.throw(
				_("Linked Site Material Consumption {0} is cancelled. Please amend this Purchase Invoice.").format(
					consumption.name
				)
			)

		rows = self.get_site_material_consumption_rows()
		project = rows[0].project
		warehouse = rows[0].warehouse
		cost_center = rows[0].cost_center

		consumption = frappe.new_doc("Site Material Consumption")
		consumption.update(
			{
				"company": self.company,
				"project": project,
				"source_warehouse": warehouse,
				"posting_date": self.posting_date,
				"posting_time": self.posting_time,
				"set_posting_time": 1,
				"cost_center": cost_center,
				"remarks": _("Auto-created from Purchase Invoice {0}").format(self.name),
			}
		)

		for row in rows:
			consumption.append(
				"items",
				{
					"item_code": row.item_code,
					"item_name": row.item_name,
					"description": row.description,
					"qty": row.qty,
					"uom": row.uom,
					"stock_uom": row.stock_uom,
					"conversion_factor": row.conversion_factor,
					"expense_account": row.expense_account,
					"project": row.project,
					"cost_center": row.cost_center,
				},
			)

		consumption.flags.ignore_permissions = True
		consumption.insert(ignore_permissions=True)
		consumption.submit()
		self.db_set("site_material_consumption", consumption.name, update_modified=False)

	def cancel_site_material_consumption(self):
		if not self.meta.has_field("site_material_consumption") or not self.get("site_material_consumption"):
			return

		consumption = frappe.get_doc("Site Material Consumption", self.get("site_material_consumption"))
		if consumption.docstatus == 2:
			return
		if consumption.docstatus != 1:
			frappe.throw(_("Linked Site Material Consumption {0} is not submitted.").format(consumption.name))

		consumption.flags.ignore_permissions = True
		consumption.cancel()

	def get_site_material_consumption_expense_account(self, item_code):
		from construction_management.construction_management.doctype.site_material_consumption.site_material_consumption import (
			get_default_expense_account,
		)

		return get_default_expense_account(item_code, self.company)

	def get_retention_payable_accounting_context(self, validate_account=True):
		if self.is_internal_transfer() or self.is_return:
			return None

		sc_bill = self.get("sc_bill") if self.meta.has_field("sc_bill") else None
		if not sc_bill:
			return None

		sc_bill_values = frappe.db.get_value(
			"SC Bill",
			sc_bill,
			["name", "retention_amount", "gross_amount", "net_payable", "project"],
			as_dict=True,
		)
		if not sc_bill_values:
			return None

		retention_amount = flt(sc_bill_values.retention_amount)
		total = self.get_supplier_gl_total()
		if retention_amount <= AMOUNT_TOLERANCE or total <= AMOUNT_TOLERANCE:
			return None

		retention_amount = min(retention_amount, total)
		context = frappe._dict(
			{
				"sc_bill": sc_bill_values.name,
				"project": self.project or sc_bill_values.project,
				"trade_payable_account": self.credit_to,
				"retention_amount": retention_amount,
				"trade_amount": max(0, total - retention_amount),
				"base_retention_amount": min(
					self.get_supplier_gl_base_total(),
					flt(retention_amount * flt(self.conversion_rate or 1)),
				),
			}
		)
		context.base_trade_amount = max(
			0,
			self.get_supplier_gl_base_total() - context.base_retention_amount,
		)
		context.retention_account = self.get_retention_payable_account(
			context.project,
			validate_account=validate_account,
		)
		return context

	def get_retention_payable_account(self, project, validate_account=True):
		if validate_account:
			return get_construction_account(
				self.company,
				"subcontractor_retention_payable",
				project=project,
				transaction=self,
			)

		return frappe.get_cached_value(
			"Company",
			self.company,
			"default_subcontractor_retention_payable_account",
		)

	def get_retention_payable_gl_rows(self, context, against_voucher):
		return [
			self.get_payable_gl_row(
				account=self.credit_to,
				account_currency=self.party_account_currency,
				amount=context.trade_amount,
				base_amount=context.base_trade_amount,
				against_voucher=against_voucher,
				cost_center=self.cost_center,
				project=context.project,
			),
			self.get_payable_gl_row(
				account=context.retention_account,
				account_currency=get_account_currency(context.retention_account),
				amount=context.retention_amount,
				base_amount=context.base_retention_amount,
				against_voucher=against_voucher,
				cost_center=self.cost_center,
				project=context.project,
			),
		]

	def get_payable_gl_row(
		self,
		account,
		account_currency,
		amount,
		base_amount,
		against_voucher,
		cost_center=None,
		project=None,
	):
		credit_in_account_currency = (
			base_amount if account_currency == self.company_currency else amount
		)
		return self.get_gl_dict(
			{
				"account": account,
				"party_type": "Supplier",
				"party": self.supplier,
				"due_date": self.due_date,
				"against": self.against_expense_account,
				"credit": base_amount,
				"credit_in_account_currency": credit_in_account_currency,
				"credit_in_transaction_currency": amount,
				"against_voucher": against_voucher,
				"against_voucher_type": self.doctype,
				"cost_center": cost_center,
				"project": project,
			},
			account_currency,
			item=self,
		)

	def get_supplier_gl_total(self):
		total_field = "rounded_total" if self.rounding_adjustment and self.rounded_total else "grand_total"
		return flt(self.get(total_field), self.precision(total_field))

	def get_supplier_gl_base_total(self):
		total_field = (
			"base_rounded_total"
			if self.base_rounding_adjustment and self.base_rounded_total
			else "base_grand_total"
		)
		return flt(self.get(total_field), self.precision(total_field))

	def set_payment_breakdown(self):
		if not self.meta.has_field("payment_breakdown"):
			return

		context = self.get_retention_payable_accounting_context(validate_account=False)
		if not context:
			return

		total = context.trade_amount + context.retention_amount
		if total <= AMOUNT_TOLERANCE:
			return

		self.set("payment_breakdown", [])
		self.append_payment_breakdown_row(
			"Trade Payable",
			context.trade_payable_account,
			context.trade_amount,
			context.trade_amount,
			total,
		)
		self.append_payment_breakdown_row(
			"Retention Payable",
			context.retention_account,
			context.retention_amount,
			context.retention_amount,
			total,
		)

	def append_payment_breakdown_row(
		self,
		breakdown_type,
		account,
		amount,
		outstanding_amount,
		total,
		status="Pending",
	):
		if amount <= AMOUNT_TOLERANCE:
			return

		self.append(
			"payment_breakdown",
			{
				"type": breakdown_type,
				"description": account,
				"account": account,
				"amount": amount,
				"percentage": flt((amount / total) * 100),
				"outstanding_amount": outstanding_amount,
				"status": status,
			},
		)


def sync_purchase_invoice_payment_breakdown_from_payment_entry(payment_entry, method=None):
	if not payment_entry:
		return

	for reference in payment_entry.get("references") or []:
		if reference.reference_doctype == "Purchase Invoice" and reference.reference_name:
			sync_purchase_invoice_payment_breakdown(reference.reference_name)

	if payment_entry.meta.has_field("custom_original_purchase_invoice") and payment_entry.get("custom_original_purchase_invoice"):
		sync_purchase_invoice_payment_breakdown(payment_entry.get("custom_original_purchase_invoice"))


def sync_purchase_invoice_payment_breakdown(invoice_name, method=None):
	if hasattr(invoice_name, "doctype"):
		invoice_name = invoice_name.name
	if not invoice_name or not frappe.get_meta("Purchase Invoice").has_field("payment_breakdown"):
		return

	invoice = frappe.get_doc("Purchase Invoice", invoice_name)
	if not invoice.get("payment_breakdown"):
		return

	for row in invoice.get("payment_breakdown"):
		paid_amount = get_paid_amount_for_breakdown_row(invoice, row)
		outstanding_amount = max(0, flt(row.amount) - paid_amount)
		if outstanding_amount <= AMOUNT_TOLERANCE:
			status = "Paid"
		elif paid_amount > AMOUNT_TOLERANCE:
			status = "Partially Paid"
		else:
			status = "Pending"

		if flt(row.outstanding_amount) == flt(outstanding_amount) and row.status == status:
			continue

		frappe.db.set_value(
			row.doctype,
			row.name,
			{
				"outstanding_amount": outstanding_amount,
				"status": status,
			},
			update_modified=False,
		)


def get_paid_amount_for_breakdown_row(invoice, breakdown_row):
	if breakdown_row.type == "Retention Payable":
		return get_retention_payable_paid_amount(invoice, breakdown_row.account)
	if breakdown_row.type == "Trade Payable":
		return get_trade_payable_paid_amount(invoice, breakdown_row.account)
	return 0


def get_trade_payable_paid_amount(invoice, account):
	rows = frappe.get_all(
		"Payment Entry Reference",
		filters={
			"reference_doctype": "Purchase Invoice",
			"reference_name": invoice.name,
			"docstatus": 1,
		},
		fields=["parent", "allocated_amount"],
	)
	total = 0
	for row in rows:
		payment = frappe.db.get_value(
			"Payment Entry",
			{
				"name": row.parent,
				"docstatus": 1,
				"payment_type": "Pay",
				"party_type": "Supplier",
				"party": invoice.supplier,
				"company": invoice.company,
				"paid_to": account,
			},
			["name"],
			as_dict=True,
		)
		if payment:
			total += flt(row.allocated_amount)
	return min(total, flt(invoice.get("grand_total")))


def get_retention_payable_paid_amount(invoice, account):
	if not invoice.meta.has_field("retention_payable") or not invoice.get("retention_payable"):
		return 0

	total = 0
	meta = frappe.get_meta("Payment Entry")
	for fieldname in ("custom_retention_payable", "retention_payable"):
		if not meta.has_field(fieldname):
			continue
		rows = frappe.get_all(
			"Payment Entry",
			filters={
				"docstatus": 1,
				"payment_type": "Pay",
				"party_type": "Supplier",
				"party": invoice.supplier,
				"company": invoice.company,
				"paid_to": account,
				fieldname: invoice.retention_payable,
			},
			fields=["paid_amount"],
		)
		total += sum(flt(row.paid_amount) for row in rows)
	return total
