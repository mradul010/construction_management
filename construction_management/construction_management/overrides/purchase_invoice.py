import frappe
from frappe import _
from frappe.utils import flt

from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import PurchaseInvoice
from erpnext.accounts.utils import get_account_currency

from construction_management.construction_management.utils.accounting import get_construction_account


AMOUNT_TOLERANCE = 0.0001
SITE_MATERIAL_CONSUMPTION_FIELD = "site_material_consumption"
SITE_MATERIAL_CONSUMPTION_ITEM_DOCTYPE = "Site Material Consumption Item"
SITE_MATERIAL_CONSUMPTION_ITEM_SOURCE_FIELDS = ("purchase_invoice", "purchase_invoice_item")


class ConstructionPurchaseInvoice(PurchaseInvoice):
	def validate(self):
		self.prepare_accounting_only_return_before_validate()
		super().validate()
		self.apply_accounting_only_return_accounts()
		self.validate_retention_account_for_submit()
		self.validate_site_material_consumption_on_submit()
		self.set_payment_breakdown()

	def on_submit(self):
		super().on_submit()
		self.create_site_material_consumption_on_submit()

	def on_cancel(self):
		self.cancel_site_material_consumption()
		unlink_site_material_consumption(self)
		super().on_cancel()

	def on_trash(self):
		unlink_site_material_consumption(self)
		super().on_trash()

	def set_expense_account(self, for_validate=False):
		if self.is_accounting_only_return():
			self.apply_accounting_only_return_accounts()
			return

		super().set_expense_account(for_validate=for_validate)

	def is_accounting_only_return(self):
		return bool(
			self.meta.has_field("accounting_only_return")
			and self.get("accounting_only_return")
			and self.is_return
		)

	def prepare_accounting_only_return_before_validate(self):
		if not self.meta.has_field("accounting_only_return"):
			return

		if self.get("accounting_only_return") and not self.is_return:
			frappe.throw(_("Accounting Only Return can be used only on a Purchase Return / Debit Note."))

		if not self.is_accounting_only_return():
			return

		if not self.return_against:
			frappe.throw(_("Return Against is required for an Accounting Only Purchase Return."))

		self.update_stock = 0
		if self.meta.has_field("consume_site_materials_on_submit"):
			self.consume_site_materials_on_submit = 0

	def apply_accounting_only_return_accounts(self):
		if not self.is_accounting_only_return():
			return

		self.update_stock = 0
		for item in self.get("items") or []:
			if not item.item_code or flt(item.qty) >= 0:
				continue

			account = self.get_original_consumption_account_for_return_item(item)
			item.expense_account = account
			if item.meta.has_field("original_consumption_account"):
				item.original_consumption_account = account

		self.set_against_expense_account(force=True)

	def get_original_consumption_account_for_return_item(self, item):
		original_item = item.get("purchase_invoice_item") or self.get_original_purchase_invoice_item_by_row(item)
		if not original_item:
			frappe.throw(
				_(
					"Row #{0}: Original Purchase Invoice Item is required for Accounting Only Return. "
					"Create the return from the original Purchase Invoice, or set Purchase Invoice Item on the row."
				).format(item.idx)
			)

		original_values = self.get_original_purchase_invoice_item_values(original_item)
		if not original_values:
			frappe.throw(
				_("Row #{0}: Original Purchase Invoice Item {1} was not found.").format(
					item.idx, frappe.bold(original_item)
				)
			)

		if not self.is_stock_item(original_values.item_code):
			if original_values.expense_account:
				return self.validate_accounting_only_return_expense_account(
					original_values.expense_account, item
				)
			frappe.throw(
				_("Row #{0}: Original non-stock item {1} does not have an expense account.").format(
					item.idx, frappe.bold(original_values.item_code)
				)
			)

		account = original_values.get("original_consumption_account")
		if account:
			return self.validate_accounting_only_return_expense_account(account, item)

		account = self.get_site_material_consumption_account_for_original_item(
			original_item, original_values=original_values
		)
		if account:
			return self.validate_accounting_only_return_expense_account(account, item)

		frappe.throw(
			_(
				"Row #{0}: Could not determine the original material consumption account for item {1}. "
				"Please ensure the original Purchase Invoice was consumed through Site Material Consumption."
			).format(item.idx, frappe.bold(item.item_code))
		)

	def get_original_purchase_invoice_item_by_row(self, item):
		if not self.return_against:
			return None

		filters = {
			"parent": self.return_against,
			"idx": item.idx,
		}
		if item.item_code:
			filters["item_code"] = item.item_code

		matches = frappe.get_all("Purchase Invoice Item", filters=filters, pluck="name", limit=2)
		return matches[0] if len(matches) == 1 else None

	def get_original_purchase_invoice_item_values(self, original_item):
		fields = [
			"name",
			"parent",
			"idx",
			"item_code",
			"expense_account",
			"project",
			"cost_center",
			"warehouse",
			"qty",
			"uom",
			"stock_uom",
			"conversion_factor",
		]
		if frappe.get_meta("Purchase Invoice Item").has_field("original_consumption_account"):
			fields.append("original_consumption_account")

		return frappe.db.get_value(
			"Purchase Invoice Item",
			original_item,
			fields,
			as_dict=True,
		)

	def is_stock_item(self, item_code):
		return bool(item_code and frappe.db.get_value("Item", item_code, "is_stock_item"))

	def get_site_material_consumption_account_for_original_item(self, original_item, original_values=None):
		row = self.get_site_material_consumption_item_for_original_item(
			original_item, original_values=original_values
		)
		return row.expense_account if row and row.expense_account else None

	def get_site_material_consumption_item_for_original_item(self, original_item, original_values=None):
		if not self.return_against or not frappe.get_meta("Purchase Invoice").has_field(SITE_MATERIAL_CONSUMPTION_FIELD):
			return None

		consumption = frappe.db.get_value("Purchase Invoice", self.return_against, SITE_MATERIAL_CONSUMPTION_FIELD)
		if not consumption or not frappe.db.exists("Site Material Consumption", consumption):
			return None

		meta = frappe.get_meta("Site Material Consumption Item")
		fields = [
			"name",
			"idx",
			"item_code",
			"qty",
			"uom",
			"stock_uom",
			"conversion_factor",
			"expense_account",
			"project",
			"cost_center",
		]

		if meta.has_field("purchase_invoice_item"):
			rows = frappe.get_all(
				"Site Material Consumption Item",
				filters={
					"parent": consumption,
					"purchase_invoice_item": original_item,
				},
				fields=fields,
				limit=2,
			)
			if rows:
				return self.get_unique_site_material_consumption_match(
					rows,
					original_item,
					match_context=_("Purchase Invoice Item reference"),
				)

		original_values = original_values or self.get_original_purchase_invoice_item_values(original_item)
		if not original_values:
			return None

		rows = frappe.get_all(
			"Site Material Consumption Item",
			filters={
				"parent": consumption,
				"item_code": original_values.item_code,
			},
			fields=fields,
			order_by="idx asc",
		)
		if not rows:
			return None

		# SMC excludes non-stock PI rows, so PI Item idx and SMC Item idx can diverge.
		rows = self.filter_site_material_consumption_candidates(rows, original_values)
		return self.get_unique_site_material_consumption_match(
			rows,
			original_item,
			match_context=_("item/project/cost center/quantity fallback"),
		)

	def filter_site_material_consumption_candidates(self, rows, original_values):
		candidates = list(rows)
		for fieldname in ("project", "cost_center", "uom", "stock_uom"):
			value = original_values.get(fieldname)
			if not value:
				continue

			matches = [row for row in candidates if row.get(fieldname) == value]
			if matches:
				candidates = matches

		original_qty = abs(flt(original_values.get("qty")))
		if original_qty:
			matches = [
				row
				for row in candidates
				if abs(abs(flt(row.get("qty"))) - original_qty) <= AMOUNT_TOLERANCE
			]
			if matches:
				candidates = matches

		return candidates

	def get_unique_site_material_consumption_match(self, rows, original_item, match_context=None):
		rows = [row for row in rows if row.get("expense_account")]
		if len(rows) == 1:
			return rows[0]

		if len(rows) > 1:
			frappe.throw(
				_(
					"Could not uniquely determine the Site Material Consumption row for Purchase Invoice Item {0} "
					"using {1}. Matching SMC rows: {2}."
				).format(
					frappe.bold(original_item),
					match_context or _("available references"),
					", ".join(str(row.get("idx")) for row in rows),
				)
			)

		return None

	def validate_accounting_only_return_expense_account(self, account, item):
		account_values = frappe.db.get_value(
			"Account",
			account,
			["company", "is_group", "account_type"],
			as_dict=True,
		)
		if not account_values:
			frappe.throw(_("Row #{0}: Account {1} does not exist.").format(item.idx, frappe.bold(account)))
		if account_values.company != self.company:
			frappe.throw(
				_("Row #{0}: Account {1} does not belong to company {2}.").format(
					item.idx, frappe.bold(account), frappe.bold(self.company)
				)
			)
		if account_values.is_group:
			frappe.throw(_("Row #{0}: Account {1} must be a ledger account.").format(item.idx, frappe.bold(account)))
		if account_values.account_type == "Stock":
			frappe.throw(
				_(
					"Row #{0}: Original material consumption account {1} is a Stock account. "
					"Use an expense account such as Cost of Construction or Cost of Other Jobs."
				).format(item.idx, frappe.bold(account))
			)
		return account

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

		warehouses = {row.warehouse for row in rows if row.warehouse}
		missing_warehouse_rows = [row.idx for row in rows if not row.warehouse]

		if missing_warehouse_rows:
			frappe.throw(
				_("Warehouse is required on Purchase Invoice item rows before site material consumption. Missing rows: {0}").format(
					", ".join(str(idx) for idx in missing_warehouse_rows)
				)
			)
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

			project = row.project
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
						"project": project,
						"cost_center": row.cost_center,
						"expense_account": self.get_site_material_consumption_expense_account(row, project),
						"purchase_invoice": self.name,
						"purchase_invoice_item": row.name,
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
		project = self.get_common_site_material_consumption_value(rows, "project")
		warehouse = rows[0].warehouse
		cost_center = self.get_common_site_material_consumption_value(rows, "cost_center")

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
					"purchase_invoice": row.purchase_invoice,
					"purchase_invoice_item": row.purchase_invoice_item,
					"project": row.project,
					"cost_center": row.cost_center,
				},
			)

		consumption.flags.ignore_permissions = True
		consumption.insert(ignore_permissions=True)
		consumption.submit()
		self.set_original_consumption_accounts_on_purchase_invoice(rows)
		self.db_set("site_material_consumption", consumption.name, update_modified=False)

	def set_original_consumption_accounts_on_purchase_invoice(self, rows):
		if not frappe.get_meta("Purchase Invoice Item").has_field("original_consumption_account"):
			return

		for row in rows:
			if not row.purchase_invoice_item or not row.expense_account:
				continue
			frappe.db.set_value(
				"Purchase Invoice Item",
				row.purchase_invoice_item,
				"original_consumption_account",
				row.expense_account,
				update_modified=False,
			)

	def get_common_site_material_consumption_value(self, rows, fieldname):
		values = [row.get(fieldname) for row in rows]
		non_empty_values = {value for value in values if value}
		return non_empty_values.pop() if len(non_empty_values) == 1 and all(values) else None

	def cancel_site_material_consumption(self):
		if not self.meta.has_field(SITE_MATERIAL_CONSUMPTION_FIELD) or not self.get(SITE_MATERIAL_CONSUMPTION_FIELD):
			return

		consumption_name = self.get(SITE_MATERIAL_CONSUMPTION_FIELD)
		if not frappe.db.exists("Site Material Consumption", consumption_name):
			return

		consumption = frappe.get_doc("Site Material Consumption", consumption_name)
		if consumption.docstatus == 2:
			return
		if consumption.docstatus == 0:
			return

		consumption.flags.ignore_permissions = True
		consumption.cancel()

	def get_site_material_consumption_expense_account(self, row, project=None):
		from construction_management.construction_management.doctype.site_material_consumption.site_material_consumption import (
			get_default_expense_account,
			validate_expense_account,
		)

		consumption_account = row.get("consumption_account") if row.meta.has_field("consumption_account") else None
		if consumption_account:
			validate_expense_account(consumption_account, self.company, row.idx)
			return consumption_account

		if not project:
			frappe.throw(
				_(
					"Consumption Account is required for item {0} because no Project is selected."
				).format(frappe.bold(row.item_code))
			)

		return get_default_expense_account(row.item_code, self.company)

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


def unlink_site_material_consumption(purchase_invoice=None, site_material_consumption=None):
	"""
	Clear PI <-> SMC references that otherwise block Frappe cancel/delete link checks.
	"""
	purchase_invoice_name = _get_doc_name(purchase_invoice)
	consumption_names = set()

	if site_material_consumption:
		consumption_names.add(_get_doc_name(site_material_consumption))

	if purchase_invoice_name:
		consumption_names.update(_get_site_material_consumptions_for_purchase_invoice(purchase_invoice))

	if not consumption_names:
		return

	consumption_names.discard(None)
	for consumption_name in sorted(consumption_names):
		_clear_purchase_invoice_site_material_consumption_link(purchase_invoice_name, consumption_name)
		_clear_site_material_consumption_item_source_links(consumption_name, purchase_invoice_name)


def _get_doc_name(doc):
	if not doc:
		return None
	return doc.name if hasattr(doc, "doctype") else doc


def _get_site_material_consumptions_for_purchase_invoice(purchase_invoice):
	purchase_invoice_name = _get_doc_name(purchase_invoice)
	if not purchase_invoice_name:
		return set()

	consumption_names = set()
	if _doctype_has_field("Purchase Invoice", SITE_MATERIAL_CONSUMPTION_FIELD):
		if hasattr(purchase_invoice, "doctype"):
			consumption_name = purchase_invoice.get(SITE_MATERIAL_CONSUMPTION_FIELD)
		else:
			consumption_name = frappe.db.get_value(
				"Purchase Invoice",
				purchase_invoice_name,
				SITE_MATERIAL_CONSUMPTION_FIELD,
			)
		if consumption_name:
			consumption_names.add(consumption_name)

	if _doctype_has_field(SITE_MATERIAL_CONSUMPTION_ITEM_DOCTYPE, "purchase_invoice"):
		consumption_names.update(
			frappe.get_all(
				SITE_MATERIAL_CONSUMPTION_ITEM_DOCTYPE,
				filters={"purchase_invoice": purchase_invoice_name},
				pluck="parent",
				distinct=True,
			)
		)

	if _doctype_has_field(SITE_MATERIAL_CONSUMPTION_ITEM_DOCTYPE, "purchase_invoice_item"):
		purchase_invoice_items = frappe.get_all(
			"Purchase Invoice Item",
			filters={"parent": purchase_invoice_name, "parenttype": "Purchase Invoice"},
			pluck="name",
		)
		if purchase_invoice_items:
			consumption_names.update(
				frappe.get_all(
					SITE_MATERIAL_CONSUMPTION_ITEM_DOCTYPE,
					filters={"purchase_invoice_item": ("in", purchase_invoice_items)},
					pluck="parent",
					distinct=True,
				)
			)

	return consumption_names


def _clear_purchase_invoice_site_material_consumption_link(purchase_invoice_name, consumption_name):
	if not _doctype_has_field("Purchase Invoice", SITE_MATERIAL_CONSUMPTION_FIELD):
		return

	filters = {SITE_MATERIAL_CONSUMPTION_FIELD: consumption_name}
	if purchase_invoice_name:
		filters["name"] = purchase_invoice_name

	for invoice_name in frappe.get_all("Purchase Invoice", filters=filters, pluck="name"):
		frappe.db.set_value(
			"Purchase Invoice",
			invoice_name,
			SITE_MATERIAL_CONSUMPTION_FIELD,
			None,
			update_modified=False,
		)


def _clear_site_material_consumption_item_source_links(consumption_name, purchase_invoice_name=None):
	if not consumption_name or not frappe.db.exists("Site Material Consumption", consumption_name):
		return

	item_meta = frappe.get_meta(SITE_MATERIAL_CONSUMPTION_ITEM_DOCTYPE)
	fields_to_clear = [
		fieldname
		for fieldname in SITE_MATERIAL_CONSUMPTION_ITEM_SOURCE_FIELDS
		if item_meta.has_field(fieldname) and item_meta.get_field(fieldname).fieldtype == "Link"
	]
	if not fields_to_clear:
		return

	filters = {
		"parent": consumption_name,
		"parenttype": "Site Material Consumption",
	}

	item_names = _get_site_material_consumption_item_names_to_unlink(
		filters,
		item_meta,
		purchase_invoice_name,
	)
	if not item_names:
		return

	for item in frappe.get_all(
		SITE_MATERIAL_CONSUMPTION_ITEM_DOCTYPE,
		filters={"name": ("in", item_names)},
		fields=["name", *fields_to_clear],
	):
		values = {fieldname: None for fieldname in fields_to_clear if item.get(fieldname)}
		if values:
			frappe.db.set_value(
				SITE_MATERIAL_CONSUMPTION_ITEM_DOCTYPE,
				item.name,
				values,
				update_modified=False,
			)


def _get_site_material_consumption_item_names_to_unlink(filters, item_meta, purchase_invoice_name=None):
	if not purchase_invoice_name:
		return frappe.get_all(SITE_MATERIAL_CONSUMPTION_ITEM_DOCTYPE, filters=filters, pluck="name")

	item_names = set()
	if item_meta.has_field("purchase_invoice"):
		item_names.update(
			frappe.get_all(
				SITE_MATERIAL_CONSUMPTION_ITEM_DOCTYPE,
				filters={**filters, "purchase_invoice": purchase_invoice_name},
				pluck="name",
			)
		)

	if item_meta.has_field("purchase_invoice_item"):
		purchase_invoice_items = frappe.get_all(
			"Purchase Invoice Item",
			filters={"parent": purchase_invoice_name, "parenttype": "Purchase Invoice"},
			pluck="name",
		)
		if purchase_invoice_items:
			item_names.update(
				frappe.get_all(
					SITE_MATERIAL_CONSUMPTION_ITEM_DOCTYPE,
					filters={**filters, "purchase_invoice_item": ("in", purchase_invoice_items)},
					pluck="name",
				)
			)

	return item_names


def _doctype_has_field(doctype, fieldname):
	try:
		return frappe.get_meta(doctype).has_field(fieldname)
	except frappe.DoesNotExistError:
		frappe.clear_last_message()
		return False


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
