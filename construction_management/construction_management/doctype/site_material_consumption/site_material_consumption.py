import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, nowdate, nowtime

from erpnext.setup.doctype.item_group.item_group import get_item_group_defaults
from erpnext.stock.doctype.item.item import get_item_defaults
from erpnext.stock.get_item_details import get_conversion_factor
from erpnext.stock.stock_ledger import is_negative_stock_allowed
from erpnext.stock.utils import get_stock_balance


class SiteMaterialConsumption(Document):
	def before_validate(self):
		self.set_missing_defaults()
		self.set_item_defaults()
		self.set_totals()

	def validate(self):
		self.validate_header()
		self.validate_items()
		self.set_totals()

	def on_submit(self):
		self.create_stock_entry()

	def on_cancel(self):
		self.cancel_stock_entry()
		self.unlink_purchase_invoice_references()

	def on_trash(self):
		self.unlink_purchase_invoice_references()

	def set_missing_defaults(self):
		settings = get_construction_settings()
		if not self.company and settings.get("default_company"):
			self.company = settings.default_company

		if self.project:
			project_values = frappe.db.get_value("Project", self.project, ["company", "cost_center"], as_dict=True)
			if project_values:
				if not self.company and project_values.company:
					self.company = project_values.company
				if not self.cost_center and project_values.cost_center:
					self.cost_center = project_values.cost_center

		if not self.cost_center and self.company:
			self.cost_center = frappe.get_cached_value("Company", self.company, "cost_center")

		if not self.posting_date:
			self.posting_date = nowdate()
		if not self.posting_time:
			self.posting_time = nowtime()
		self.set_posting_time = 1

	def validate_header(self):
		if not self.items:
			frappe.throw(_("Please add at least one material item."))

		settings = get_construction_settings()
		require_project_warehouse = settings.get("require_project_warehouse")
		if require_project_warehouse in (None, ""):
			require_project_warehouse = 1
		if cint(require_project_warehouse) and not self.source_warehouse:
			frappe.throw(_("Site Warehouse is required."))

		if self.source_warehouse:
			warehouse = frappe.db.get_value(
				"Warehouse", self.source_warehouse, ["is_group", "company"], as_dict=True
			)
			if not warehouse:
				frappe.throw(_("Warehouse {0} does not exist.").format(frappe.bold(self.source_warehouse)))
			if cint(warehouse.is_group):
				frappe.throw(_("Please select a non-group Site Warehouse."))
			if warehouse.company and self.company and warehouse.company != self.company:
				frappe.throw(
					_("Warehouse {0} belongs to company {1}, not {2}.").format(
						frappe.bold(self.source_warehouse),
						frappe.bold(warehouse.company),
						frappe.bold(self.company),
					)
				)

	def validate_items(self):
		for row in self.items:
			self.validate_item_row(row)

	def validate_item_row(self, row):
		if flt(row.qty) <= 0:
			frappe.throw(_("Row {0}: Consume Qty must be greater than zero.").format(row.idx))

		item = frappe.get_cached_doc("Item", row.item_code)
		if not cint(item.is_stock_item):
			frappe.throw(_("Row {0}: Item {1} is not a stock item.").format(row.idx, frappe.bold(row.item_code)))
		if cint(item.disabled):
			frappe.throw(_("Row {0}: Item {1} is disabled.").format(row.idx, frappe.bold(row.item_code)))

		if not self.source_warehouse:
			frappe.throw(_("Row {0}: Site Warehouse is required.").format(row.idx))

		stock_qty = flt(row.qty) * flt(row.conversion_factor or 1)
		if not is_negative_stock_allowed(item_code=row.item_code) and flt(row.available_qty) < stock_qty:
			frappe.throw(
				_(
					"Cannot consume {0} {1} of {2}.<br><br>Available quantity in {3} is {4} {5}."
				).format(
					flt(row.qty),
					row.uom or row.stock_uom,
					frappe.bold(row.item_name or row.item_code),
					frappe.bold(self.source_warehouse),
					flt(row.available_qty),
					row.stock_uom,
				)
			)

		if row.expense_account:
			validate_expense_account(row.expense_account, self.company, row.idx)

	def set_item_defaults(self):
		for row in self.items:
			if not row.item_code:
				continue

			project = row.project or self.project
			details = get_consumption_item_details(
				row.item_code,
				self.source_warehouse,
				self.company,
				project,
				self.posting_date,
				self.posting_time,
				row.uom,
			)
			for fieldname, value in details.items():
				if fieldname in {"available_qty", "valuation_rate", "amount"}:
					row.set(fieldname, value)
				elif not row.get(fieldname) and value:
					row.set(fieldname, value)

			row.project = project
			row.cost_center = row.cost_center or self.cost_center or get_default_cost_center(
				row.item_code, self.company, project
			)
			row.expense_account = row.expense_account or get_default_expense_account(row.item_code, self.company)
			row.amount = flt(row.qty) * flt(row.conversion_factor or 1) * flt(row.valuation_rate)

	def set_totals(self):
		self.total_qty = sum(flt(row.qty) for row in self.items)
		self.total_amount = sum(flt(row.amount) for row in self.items)

	def create_stock_entry(self):
		if self.stock_entry:
			stock_entry = frappe.get_doc("Stock Entry", self.stock_entry)
			if stock_entry.docstatus == 1:
				return
			if stock_entry.docstatus == 0:
				stock_entry.flags.ignore_permissions = True
				stock_entry.submit()
				return
			frappe.throw(_("Linked Stock Entry {0} is cancelled. Please amend this document.").format(self.stock_entry))

		stock_entry = frappe.new_doc("Stock Entry")
		stock_entry.update(
			{
				"company": self.company,
				"purpose": "Material Issue",
				"posting_date": self.posting_date,
				"posting_time": self.posting_time,
				"set_posting_time": 1,
				"project": self.project,
				"cost_center": self.cost_center,
				"remarks": self.get_stock_entry_remarks(),
			}
		)
		stock_entry.set_stock_entry_type()

		for row in self.items:
			stock_entry.append(
				"items",
				{
					"item_code": row.item_code,
					"item_name": row.item_name,
					"description": row.description,
					"s_warehouse": self.source_warehouse,
					"qty": row.qty,
					"uom": row.uom,
					"stock_uom": row.stock_uom,
					"conversion_factor": row.conversion_factor or 1,
					"expense_account": row.expense_account,
					"project": row.project or self.project,
					"cost_center": row.cost_center or self.cost_center,
				},
			)

		stock_entry.flags.ignore_permissions = True
		stock_entry.insert(ignore_permissions=True)
		stock_entry.submit()
		self.db_set("stock_entry", stock_entry.name, update_modified=False)

	def get_stock_entry_remarks(self):
		remarks = _("Auto-created from Site Material Consumption {0}").format(self.name)
		if self.remarks:
			remarks = f"{remarks}\n\n{self.remarks}"
		return remarks

	def cancel_stock_entry(self):
		if not self.stock_entry:
			return

		stock_entry = frappe.get_doc("Stock Entry", self.stock_entry)
		if stock_entry.docstatus == 2:
			return
		if stock_entry.docstatus != 1:
			frappe.throw(_("Linked Stock Entry {0} is not submitted.").format(self.stock_entry))

		stock_entry.flags.ignore_permissions = True
		stock_entry.cancel()

	def unlink_purchase_invoice_references(self):
		from construction_management.construction_management.overrides.purchase_invoice import (
			unlink_site_material_consumption,
		)

		unlink_site_material_consumption(site_material_consumption=self)


def get_construction_settings():
	try:
		return frappe.get_cached_doc("Construction Settings")
	except Exception:
		return frappe._dict()


def validate_expense_account(account, company, row_idx=None):
	account_values = frappe.db.get_value("Account", account, ["company", "is_group", "account_type"], as_dict=True)
	if not account_values:
		frappe.throw(_("Row {0}: Expense Account {1} does not exist.").format(row_idx, frappe.bold(account)))
	if cint(account_values.is_group):
		frappe.throw(_("Row {0}: Expense Account {1} must be a ledger account.").format(row_idx, frappe.bold(account)))
	if account_values.account_type == "Stock":
		frappe.throw(
			_("Row {0}: Expense Account {1} must not be a Stock type account.").format(
				row_idx,
				frappe.bold(account),
			)
		)
	if company and account_values.company and account_values.company != company:
		frappe.throw(
			_("Row {0}: Expense Account {1} belongs to company {2}, not {3}.").format(
				row_idx,
				frappe.bold(account),
				frappe.bold(account_values.company),
				frappe.bold(company),
			)
		)


def get_default_cost_center(item_code=None, company=None, project=None):
	if project:
		cost_center = frappe.get_cached_value("Project", project, "cost_center")
		if cost_center:
			return cost_center

	item_defaults = get_safe_item_defaults(item_code, company)
	if item_defaults.get("buying_cost_center"):
		return item_defaults.buying_cost_center

	if company:
		return frappe.get_cached_value("Company", company, "cost_center")


def get_default_expense_account(item_code, company):
	item_defaults = get_safe_item_defaults(item_code, company)
	for account in (
		item_defaults.get("expense_account"),
		get_safe_item_group_defaults(item_code, company).get("expense_account"),
		get_construction_settings().get("default_material_consumption_expense_account"),
		frappe.get_cached_value("Company", company, "default_expense_account") if company else None,
	):
		if is_valid_ledger_account(account, company):
			return account


def get_safe_item_defaults(item_code, company):
	if not item_code or not company:
		return frappe._dict()
	try:
		return frappe._dict(get_item_defaults(item_code, company) or {})
	except Exception:
		return frappe._dict()


def get_safe_item_group_defaults(item_code, company):
	if not item_code or not company:
		return frappe._dict()
	try:
		return frappe._dict(get_item_group_defaults(item_code, company) or {})
	except Exception:
		return frappe._dict()


def is_valid_ledger_account(account, company):
	if not account:
		return False
	account_values = frappe.db.get_value("Account", account, ["company", "is_group", "account_type"], as_dict=True)
	return bool(
		account_values
		and not cint(account_values.is_group)
		and account_values.account_type != "Stock"
		and (not company or not account_values.company or account_values.company == company)
	)


@frappe.whitelist()
def get_consumption_item_details(
	item_code,
	source_warehouse=None,
	company=None,
	project=None,
	posting_date=None,
	posting_time=None,
	uom=None,
):
	item = frappe.get_cached_doc("Item", item_code)
	if not cint(item.is_stock_item) or cint(item.disabled):
		frappe.throw(_("Please select an enabled stock item."))

	stock_uom = item.stock_uom
	uom = uom or stock_uom
	conversion = flt(get_conversion_factor(item_code, uom).get("conversion_factor") or 1)
	available_qty, valuation_rate = (0, 0)
	if source_warehouse:
		available_qty, valuation_rate = get_stock_balance(
			item_code,
			source_warehouse,
			posting_date or nowdate(),
			posting_time or nowtime(),
			with_valuation_rate=True,
		)

	return {
		"item_name": item.item_name,
		"description": item.description,
		"uom": uom,
		"stock_uom": stock_uom,
		"conversion_factor": conversion,
		"available_qty": flt(available_qty),
		"valuation_rate": flt(valuation_rate),
		"expense_account": get_default_expense_account(item_code, company),
		"project": project,
		"cost_center": get_default_cost_center(item_code, company, project),
	}


@frappe.whitelist()
def get_available_materials(source_warehouse, company=None, project=None, posting_date=None, posting_time=None):
	if not source_warehouse:
		frappe.throw(_("Please select a Site Warehouse first."))

	bin_table = frappe.qb.DocType("Bin")
	item_table = frappe.qb.DocType("Item")
	query = (
		frappe.qb.from_(bin_table)
		.inner_join(item_table)
		.on(bin_table.item_code == item_table.name)
		.select(
			bin_table.item_code,
			bin_table.actual_qty,
			bin_table.stock_value,
			item_table.item_name,
			item_table.description,
			item_table.stock_uom,
		)
		.where(
			(bin_table.warehouse == source_warehouse)
			& (bin_table.actual_qty > 0)
			& (item_table.is_stock_item == 1)
			& (item_table.disabled == 0)
		)
		.orderby(item_table.item_name)
	)

	rows = []
	for row in query.run(as_dict=True):
		valuation_rate = flt(row.stock_value) / flt(row.actual_qty) if flt(row.actual_qty) else 0
		rows.append(
			{
				"item_code": row.item_code,
				"item_name": row.item_name,
				"description": row.description,
				"uom": row.stock_uom,
				"stock_uom": row.stock_uom,
				"conversion_factor": 1,
				"available_qty": flt(row.actual_qty),
				"qty": 0,
				"valuation_rate": valuation_rate,
				"expense_account": get_default_expense_account(row.item_code, company),
				"project": project,
				"cost_center": get_default_cost_center(row.item_code, company, project),
			}
		)
	return rows
