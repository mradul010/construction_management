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
		self.set_transaction_defaults()
		self.set_missing_defaults()
		self.set_employee_details()
		self.set_item_defaults()
		self.set_issue_type()
		self.set_totals()

	def validate(self):
		self.validate_header()
		self.validate_return_against()
		self.validate_items()
		self.validate_project_company()
		self.set_totals()

	def on_submit(self):
		try:
			self.sync_employee_issue_history()
		except Exception:
			frappe.log_error(
				title="Site Material Consumption Submit Error",
				message=frappe.get_traceback(),
			)
			raise

	def on_cancel(self):
		self.cancel_stock_entry()
		self.remove_employee_issue_history()

	def set_transaction_defaults(self):
		if self.return_against:
			self.transaction_type = "Material Return"
			return
		if not self.get("transaction_type"):
			self.transaction_type = "Material Issue"

	def set_missing_defaults(self):
		settings = get_construction_settings()
		if not self.company and settings.get("default_company"):
			self.company = settings.default_company

		if self.is_material_return() and self.return_against:
			original = frappe.db.get_value(
				"Site Material Consumption",
				self.return_against,
				["company", "project", "source_warehouse", "cost_center"],
				as_dict=True,
			)
			if original:
				self.company = self.company or original.company
				self.project = self.project or original.project
				self.source_warehouse = self.source_warehouse or original.source_warehouse
				self.cost_center = self.cost_center or original.cost_center

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
		self.source_warehouse = self.source_warehouse or get_site_material_warehouse(
			company=self.company,
			project=self.project,
			return_against=self.return_against if self.is_material_return() else None,
			item_codes=get_item_codes(self.items),
			validate=self.docstatus == 1,
		)

	def set_employee_details(self):
		if not self.employee:
			self.employee_name = None
			if not self.subcontractor_supplier:
				self.subcontractor_supplier_name = None
			return

		employee = frappe.db.get_value(
			"Employee",
			self.employee,
			["employee_name", "subcontractor_supplier"],
			as_dict=True,
		)
		if not employee:
			return

		self.employee_name = employee.employee_name
		if employee.subcontractor_supplier:
			self.subcontractor_supplier = employee.subcontractor_supplier
		self.set_supplier_name()

	def set_supplier_name(self):
		if self.subcontractor_supplier:
			self.subcontractor_supplier_name = frappe.db.get_value(
				"Supplier", self.subcontractor_supplier, "supplier_name"
			)
		else:
			self.subcontractor_supplier_name = None

	def set_issue_type(self):
		item_codes = [row.item_code for row in self.items or [] if row.item_code]
		if len(set(item_codes)) == 1:
			self.type_of_issued = item_codes[0]
		else:
			self.type_of_issued = None

	def validate_header(self):
		if not self.items:
			frappe.throw(_("Please add at least one material item."))
		if get_transaction_type(self) not in ("Material Issue", "Material Return"):
			frappe.throw(_("Transaction Type must be Material Issue or Material Return."))

		self.source_warehouse = self.source_warehouse or get_site_material_warehouse(
			company=self.company,
			project=self.project,
			return_against=self.return_against if self.is_material_return() else None,
			item_codes=get_item_codes(self.items),
			validate=self.docstatus == 1,
		)
		if self.docstatus == 1 and self.source_warehouse:
			validate_site_material_warehouse(self.source_warehouse, self.company)

	def validate_project_company(self):
		project_company = frappe.db.get_value("Project", self.project, "company")
		if project_company and self.company and project_company != self.company:
			frappe.throw(_("Project {0} belongs to Company {1}.").format(self.project, project_company))

	def validate_items(self):
		if self.is_material_return():
			self.set_return_item_balances(validate=True)
		for row in self.items:
			self.validate_item_row(row, validate_stock=self.docstatus == 1)

	def validate_item_row(self, row, validate_stock=False):
		if flt(row.qty) <= 0:
			frappe.throw(_("Row {0}: Consume Qty must be greater than zero.").format(row.idx))

		item = frappe.get_cached_doc("Item", row.item_code)
		if validate_stock:
			if not cint(item.is_stock_item):
				frappe.throw(_("Row {0}: Item {1} is not a stock item.").format(row.idx, frappe.bold(row.item_code)))
			if cint(item.disabled):
				frappe.throw(_("Row {0}: Item {1} is disabled.").format(row.idx, frappe.bold(row.item_code)))

			stock_qty = flt(row.qty) * flt(row.conversion_factor or 1)
			if (
				self.source_warehouse
				and not is_negative_stock_allowed(item_code=row.item_code)
				and flt(row.available_qty) < stock_qty
			):
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

	def validate_return_against(self):
		if not self.is_material_return():
			self.return_against = None
			for row in self.items or []:
				row.issued_qty = 0
				row.previously_returned_qty = 0
				row.returnable_qty = 0
				row.original_consumption_item = None
			return

		if not self.return_against:
			frappe.throw(_("Return Against is required for Material Return."))

		if self.return_against == self.name:
			frappe.throw(_("Return Against cannot be the same document."))

		original = frappe.get_doc("Site Material Consumption", self.return_against)
		if original.docstatus != 1:
			frappe.throw(_("Return Against must be a submitted Site Material Consumption."))
		if get_transaction_type(original) != "Material Issue":
			frappe.throw(_("Return Against must be a Material Issue transaction."))
		if self.company and original.company and self.company != original.company:
			frappe.throw(_("Company must match the original Site Material Consumption."))
		if self.project and original.project and self.project != original.project:
			frappe.throw(_("Project must match the original Site Material Consumption."))
		return_warehouse = get_site_material_warehouse(
			company=self.company or original.company,
			project=self.project or original.project,
			return_against=original.name,
		)
		if not return_warehouse or not original.stock_entry:
			frappe.throw(
				_(
					"Original Site Material Consumption {0} did not create a warehouse Stock Entry. "
					"Material Return cannot update stock for this document."
				).format(frappe.bold(original.name))
			)
		self.source_warehouse = return_warehouse

	def set_return_item_balances(self, validate=False):
		balances = get_original_return_balances(
			self.return_against,
			exclude_return=self.name if self.name and not self.is_new() else None,
		)
		current_stock_qty_by_item = {}
		for row in self.items or []:
			if not row.item_code:
				continue
			if row.item_code not in balances:
				frappe.throw(
					_("Row {0}: Item {1} does not exist in original Site Material Consumption {2}.").format(
						row.idx,
						frappe.bold(row.item_code),
						frappe.bold(self.return_against),
					)
				)

			balance = balances[row.item_code]
			conversion_factor = flt(row.conversion_factor or balance.conversion_factor or 1) or 1
			current_stock_qty_by_item[row.item_code] = current_stock_qty_by_item.get(row.item_code, 0) + (
				flt(row.qty) * conversion_factor
			)
			row.issued_qty = flt(balance.issued_stock_qty) / conversion_factor
			row.previously_returned_qty = flt(balance.previously_returned_stock_qty) / conversion_factor
			row.returnable_qty = flt(balance.returnable_stock_qty) / conversion_factor
			row.original_consumption_item = row.original_consumption_item or balance.original_consumption_item

		if not validate:
			return

		for item_code, current_stock_qty in current_stock_qty_by_item.items():
			returnable_stock_qty = flt(balances[item_code].returnable_stock_qty)
			if current_stock_qty > returnable_stock_qty:
				frappe.throw(
					_("Cannot return {0} stock qty of {1}. Remaining returnable stock qty is {2}.").format(
						flt(current_stock_qty),
						frappe.bold(item_code),
						flt(returnable_stock_qty),
					)
				)

	def set_item_defaults(self):
		for row in self.items:
			if not row.item_code:
				continue

			details = get_consumption_item_details(
				row.item_code,
				self.source_warehouse,
				self.company,
				self.project,
				self.posting_date,
				self.posting_time,
				row.uom,
			)
			for fieldname, value in details.items():
				if fieldname in {"available_qty", "valuation_rate", "amount"}:
					if self.is_material_return() and fieldname == "valuation_rate" and row.get(fieldname):
						continue
					row.set(fieldname, value)
				elif not row.get(fieldname) and value:
					row.set(fieldname, value)

			row.project = row.project or self.project
			row.cost_center = row.cost_center or self.cost_center or get_default_cost_center(
				row.item_code, self.company, self.project
			)
			row.expense_account = row.expense_account or get_default_expense_account(row.item_code, self.company)
			row.amount = flt(row.qty) * flt(row.conversion_factor or 1) * flt(row.valuation_rate)

	def set_totals(self):
		self.total_qty = sum(flt(row.qty) for row in self.items)
		self.total_amount = sum(flt(row.amount) for row in self.items)

	def create_stock_entry(self):
		if self.is_material_return():
			self.create_return_stock_entry()
			return

		self.validate_stock_entry_items()

		if not self.source_warehouse:
			self.source_warehouse = get_site_material_warehouse(
				company=self.company,
				project=self.project,
				item_codes=get_item_codes(self.items),
			)
		if not self.source_warehouse:
			frappe.throw(_("Unable to determine a stock warehouse for Site Material Consumption."))

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

	def create_return_stock_entry(self):
		self.validate_stock_entry_items()

		if self.stock_entry:
			stock_entry = frappe.get_doc("Stock Entry", self.stock_entry)
			if stock_entry.docstatus == 1:
				return
			if stock_entry.docstatus == 0:
				stock_entry.flags.ignore_permissions = True
				stock_entry.submit()
				return
			frappe.throw(_("Linked Stock Entry {0} is cancelled. Please amend this document.").format(self.stock_entry))

		if not self.source_warehouse:
			frappe.throw(_("A return warehouse could not be determined from the original consumption."))

		stock_entry = frappe.new_doc("Stock Entry")
		stock_entry.update(
			{
				"company": self.company,
				"purpose": "Material Receipt",
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
					"t_warehouse": self.source_warehouse,
					"qty": row.qty,
					"uom": row.uom,
					"stock_uom": row.stock_uom,
					"conversion_factor": row.conversion_factor or 1,
					"basic_rate": row.valuation_rate,
					"expense_account": row.expense_account,
					"project": row.project or self.project,
					"cost_center": row.cost_center or self.cost_center,
				},
			)

		stock_entry.flags.ignore_permissions = True
		stock_entry.insert(ignore_permissions=True)
		stock_entry.submit()
		self.db_set("stock_entry", stock_entry.name, update_modified=False)

	def validate_stock_entry_items(self):
		for row in self.items or []:
			self.validate_item_row(row, validate_stock=True)

	def is_material_return(self):
		return get_transaction_type(self) == "Material Return"

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

	def sync_employee_issue_history(self):
		if self.is_material_return():
			return
		if not self.employee:
			return

		employee = frappe.get_doc("Employee", self.employee)
		history_field = get_employee_issue_history_field(employee)
		if not history_field:
			frappe.throw(_("Employee Issue History field is not configured."))

		for item in self.items or []:
			existing = None
			for history in employee.get(history_field) or []:
				if history.get("site_material_consumption_item") == item.name:
					existing = history
					break

			history = existing or employee.append(history_field, {})
			set_child_value_if_exists(history, "posting_date", self.posting_date)
			set_child_value_if_exists(history, "project", item.project or self.project)
			set_child_value_if_exists(
				history,
				"subcontractor_supplier",
				self.subcontractor_supplier,
			)
			set_child_value_if_exists(history, "site_material_consumption", self.name)
			set_child_value_if_exists(history, "site_material_consumption_item", item.name)
			set_child_value_if_exists(history, "stock_entry", self.stock_entry)
			set_child_value_if_exists(history, "item", item.item_code)
			set_child_value_if_exists(
				history,
				"item_name",
				item.item_name or frappe.db.get_value("Item", item.item_code, "item_name"),
			)
			set_child_value_if_exists(history, "qty", item.qty)
			set_child_value_if_exists(history, "uom", item.uom)

		employee.flags.ignore_permissions = True
		employee.save()

	def remove_employee_issue_history(self):
		if not self.employee:
			return

		employee = frappe.get_doc("Employee", self.employee)
		history_field = get_employee_issue_history_field(employee)
		if not history_field:
			return

		rows = [
			row
			for row in employee.get(history_field) or []
			if row.get("site_material_consumption") != self.name
		]
		employee.set(history_field, rows)
		employee.flags.ignore_permissions = True
		employee.save()


def get_construction_settings():
	try:
		return frappe.get_cached_doc("Construction Settings")
	except Exception:
		return frappe._dict()


def get_employee_issue_history_field(employee):
	if employee.meta.has_field("issue_history"):
		return "issue_history"
	if employee.meta.has_field("fuel_issue_history"):
		return "fuel_issue_history"


def set_child_value_if_exists(row, fieldname, value):
	if row.meta.has_field(fieldname):
		row.set(fieldname, value)


def get_item_codes(items):
	return [row.item_code for row in items or [] if row.item_code]


def get_site_material_warehouse(company=None, project=None, return_against=None, validate=True, item_codes=None):
	warehouse = None
	if return_against:
		warehouse = get_return_warehouse_from_original_stock_entry(return_against)

	if not warehouse and project and frappe.get_meta("Project").has_field("site_material_warehouse"):
		warehouse = frappe.db.get_value("Project", project, "site_material_warehouse")

	settings = get_construction_settings()
	if not warehouse:
		warehouse = settings.get("default_site_material_warehouse")
	if not warehouse:
		warehouse = get_previous_site_material_warehouse(company=company, project=project)
	if not warehouse:
		warehouse = get_common_item_default_warehouse(item_codes, company)
	if not warehouse:
		warehouse = get_stock_settings_default_warehouse(company)

	if validate and warehouse:
		validate_site_material_warehouse(warehouse, company)

	return warehouse


def get_previous_site_material_warehouse(company=None, project=None):
	if not project:
		return None

	filters = {
		"docstatus": 1,
		"project": project,
		"source_warehouse": ["is", "set"],
	}
	if company:
		filters["company"] = company

	return frappe.db.get_value(
		"Site Material Consumption",
		filters,
		"source_warehouse",
		order_by="posting_date desc, posting_time desc, modified desc",
	)


def get_common_item_default_warehouse(item_codes, company=None):
	warehouses = set()
	for item_code in set(item_codes or []):
		warehouse = get_item_default_warehouse(item_code, company)
		if warehouse:
			warehouses.add(warehouse)

	if len(warehouses) == 1:
		return warehouses.pop()


def get_item_default_warehouse(item_code, company=None):
	item_defaults = get_safe_item_defaults(item_code, company)
	for warehouse in (
		item_defaults.get("default_warehouse"),
		get_safe_item_group_defaults(item_code, company).get("default_warehouse"),
	):
		if is_valid_stock_warehouse(warehouse, company):
			return warehouse


def get_stock_settings_default_warehouse(company=None):
	warehouse = frappe.db.get_single_value("Stock Settings", "default_warehouse")
	if is_valid_stock_warehouse(warehouse, company):
		return warehouse


def get_return_warehouse_from_original_stock_entry(return_against):
	stock_entry = frappe.db.get_value("Site Material Consumption", return_against, "stock_entry")
	if not stock_entry or not frappe.db.exists("Stock Entry", stock_entry):
		return None

	warehouses = frappe.db.get_all(
		"Stock Entry Detail",
		filters={"parent": stock_entry},
		fields=["s_warehouse", "t_warehouse"],
		order_by="idx asc",
	)
	for row in warehouses:
		if row.s_warehouse:
			return row.s_warehouse
	for row in warehouses:
		if row.t_warehouse:
			return row.t_warehouse


def validate_site_material_warehouse(warehouse, company=None):
	values = frappe.db.get_value("Warehouse", warehouse, ["is_group", "company"], as_dict=True)
	if not values:
		frappe.throw(_("Warehouse {0} does not exist.").format(frappe.bold(warehouse)))
	if cint(values.is_group):
		frappe.throw(_("Please select a non-group Site Warehouse."))
	if values.company and company and values.company != company:
		frappe.throw(
			_("Warehouse {0} belongs to company {1}, not {2}.").format(
				frappe.bold(warehouse),
				frappe.bold(values.company),
				frappe.bold(company),
			)
		)


def is_valid_stock_warehouse(warehouse, company=None):
	if not warehouse:
		return False
	values = frappe.db.get_value("Warehouse", warehouse, ["is_group", "company"], as_dict=True)
	return bool(
		values
		and not cint(values.is_group)
		and (not company or not values.company or values.company == company)
	)


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


def get_transaction_type(doc):
	return doc.get("transaction_type") or "Material Issue"


def get_original_return_balances(return_against, exclude_return=None):
	if not return_against:
		return {}

	original = frappe.get_doc("Site Material Consumption", return_against)
	balances = {}
	for row in original.items or []:
		if not row.item_code:
			continue
		conversion_factor = flt(row.conversion_factor or 1) or 1
		item_balance = balances.setdefault(
			row.item_code,
			frappe._dict(
				{
					"item_code": row.item_code,
					"item_name": row.item_name,
					"description": row.description,
					"uom": row.uom,
					"stock_uom": row.stock_uom,
					"conversion_factor": conversion_factor,
					"issued_qty": 0,
					"issued_stock_qty": 0,
					"previously_returned_stock_qty": 0,
					"original_consumption_item": row.name,
					"valuation_rate": row.valuation_rate,
					"expense_account": row.expense_account,
					"project": row.project or original.project,
					"cost_center": row.cost_center or original.cost_center,
					"remarks": row.remarks,
				}
			),
		)
		item_balance.issued_qty += flt(row.qty)
		item_balance.issued_stock_qty += flt(row.qty) * conversion_factor

	for row in get_submitted_return_rows(return_against, exclude_return):
		if row.item_code in balances:
			balances[row.item_code].previously_returned_stock_qty += flt(row.returned_stock_qty)

	for row in balances.values():
		row.returnable_stock_qty = max(row.issued_stock_qty - row.previously_returned_stock_qty, 0)
		row.previously_returned_qty = flt(row.previously_returned_stock_qty) / (flt(row.conversion_factor) or 1)
		row.returnable_qty = flt(row.returnable_stock_qty) / (flt(row.conversion_factor) or 1)

	return balances


def get_submitted_return_rows(return_against, exclude_return=None):
	conditions = [
		"smc.docstatus = 1",
		"smc.return_against = %(return_against)s",
		"ifnull(smc.transaction_type, 'Material Issue') = 'Material Return'",
	]
	values = {"return_against": return_against}
	if exclude_return:
		conditions.append("smc.name != %(exclude_return)s")
		values["exclude_return"] = exclude_return

	return frappe.db.sql(
		f"""
		select
			item.item_code,
			sum(item.qty * ifnull(item.conversion_factor, 1)) as returned_stock_qty
		from `tabSite Material Consumption` smc
		inner join `tabSite Material Consumption Item` item on item.parent = smc.name
		where {" and ".join(conditions)}
		group by item.item_code
		""",
		values,
		as_dict=True,
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
	if cint(item.disabled):
		frappe.throw(_("Please select an enabled item."))

	stock_uom = item.stock_uom
	uom = uom or stock_uom
	conversion = flt(get_conversion_factor(item_code, uom).get("conversion_factor") or 1)
	available_qty, valuation_rate = (0, 0)
	if cint(item.is_stock_item):
		source_warehouse = source_warehouse or get_site_material_warehouse(
			company=company,
			project=project,
			item_codes=[item_code],
			validate=False,
		)
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
def get_available_materials(source_warehouse=None, company=None, project=None, posting_date=None, posting_time=None):
	source_warehouse = source_warehouse or get_site_material_warehouse(company=company, project=project, validate=False)
	if not source_warehouse:
		return []

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


@frappe.whitelist()
def get_returnable_items(return_against, exclude_return=None):
	original = frappe.get_doc("Site Material Consumption", return_against)
	if original.docstatus != 1:
		frappe.throw(_("Return Against must be a submitted Site Material Consumption."))
	if get_transaction_type(original) != "Material Issue":
		frappe.throw(_("Return Against must be a Material Issue transaction."))
	return_warehouse = get_site_material_warehouse(
		company=original.company,
		project=original.project,
		return_against=original.name,
	)
	if not return_warehouse or not original.stock_entry:
		frappe.throw(
			_(
				"Original Site Material Consumption {0} did not create a warehouse Stock Entry. "
				"Material Return cannot update stock for this document."
			).format(frappe.bold(original.name))
		)

	rows = []
	for balance in get_original_return_balances(return_against, exclude_return).values():
		if flt(balance.returnable_stock_qty) <= 0:
			continue
		rows.append(
			{
				"item_code": balance.item_code,
				"item_name": balance.item_name,
				"description": balance.description,
				"uom": balance.uom,
				"stock_uom": balance.stock_uom,
				"conversion_factor": balance.conversion_factor,
				"available_qty": 0,
				"qty": balance.returnable_qty,
				"issued_qty": balance.issued_qty,
				"previously_returned_qty": balance.previously_returned_qty,
				"returnable_qty": balance.returnable_qty,
				"valuation_rate": balance.valuation_rate,
				"amount": flt(balance.returnable_qty) * flt(balance.conversion_factor) * flt(balance.valuation_rate),
				"expense_account": balance.expense_account,
				"project": balance.project,
				"cost_center": balance.cost_center,
				"original_consumption_item": balance.original_consumption_item,
				"remarks": balance.remarks,
			}
		)
	return {
		"company": original.company,
		"project": original.project,
		"source_warehouse": return_warehouse,
		"cost_center": original.cost_center,
		"items": rows,
	}


@frappe.whitelist()
def get_stock_entry_action_status(name):
	doc = frappe.get_doc("Site Material Consumption", name)
	doc.check_permission("read")

	stock_entry_docstatus = None
	stock_entry_exists = False
	if doc.stock_entry and frappe.db.exists("Stock Entry", doc.stock_entry):
		stock_entry_exists = True
		stock_entry_docstatus = cint(frappe.db.get_value("Stock Entry", doc.stock_entry, "docstatus"))

	is_submitted_issue = doc.docstatus == 1 and get_transaction_type(doc) == "Material Issue"
	has_returnable_qty = False
	if is_submitted_issue and stock_entry_docstatus == 1:
		has_returnable_qty = any(
			flt(balance.remaining_transfer_qty) > 0
			for balance in get_stock_entry_return_balances(doc.stock_entry).values()
		)

	return {
		"stock_entry": doc.stock_entry,
		"stock_entry_exists": stock_entry_exists,
		"stock_entry_docstatus": stock_entry_docstatus,
		"can_create_stock_entry": is_submitted_issue and not doc.stock_entry,
		"can_open_stock_entry": stock_entry_exists and stock_entry_docstatus == 0,
		"can_view_stock_entry": stock_entry_exists,
		"can_return_material": is_submitted_issue and stock_entry_docstatus == 1 and has_returnable_qty,
		"has_returnable_qty": has_returnable_qty,
	}


@frappe.whitelist()
def create_stock_entry_from_consumption(name):
	doc = frappe.get_doc("Site Material Consumption", name)
	doc.check_permission("submit")
	if doc.docstatus != 1:
		frappe.throw(_("Site Material Consumption must be submitted before creating Stock Entry."))
	if get_transaction_type(doc) != "Material Issue":
		frappe.throw(_("Stock Entry action is only available for Material Issue documents."))

	doc.create_stock_entry()
	doc.reload()
	doc.sync_employee_issue_history()
	return get_stock_entry_action_status(doc.name)


@frappe.whitelist()
def make_return_stock_entry(name):
	original = frappe.get_doc("Site Material Consumption", name)
	original.check_permission("read")
	if original.docstatus != 1:
		frappe.throw(_("Return Material is available only for submitted Site Material Consumption."))
	if get_transaction_type(original) != "Material Issue":
		frappe.throw(_("Return Material is available only for Material Issue documents."))

	status = get_stock_entry_action_status(original.name)
	if status.get("stock_entry_docstatus") != 1:
		frappe.throw(_("Return Material is available only after the issue Stock Entry is submitted."))
	if not status.get("has_returnable_qty"):
		frappe.throw(_("All issued material has already been returned."))

	stock_entry = frappe.get_doc("Stock Entry", original.stock_entry)
	return_entry = frappe.new_doc("Stock Entry")
	return_entry.update(
		{
			"company": stock_entry.company,
			"purpose": get_reverse_stock_entry_purpose(stock_entry),
			"is_return": 1,
			"posting_date": nowdate(),
			"posting_time": nowtime(),
			"set_posting_time": 1,
			"project": stock_entry.get("project") or original.project,
			"cost_center": stock_entry.get("cost_center") or original.cost_center,
			"remarks": _("Return against Stock Entry {0} from Site Material Consumption {1}").format(
				stock_entry.name,
				original.name,
			),
		}
	)
	return_entry.set_stock_entry_type()

	for balance in get_stock_entry_return_balances(stock_entry.name).values():
		if flt(balance.remaining_transfer_qty) <= 0:
			continue

		row = balance.original_row
		return_entry.append(
			"items",
			{
				"item_code": row.item_code,
				"item_name": row.item_name,
				"description": row.description,
				"s_warehouse": row.t_warehouse,
				"t_warehouse": row.s_warehouse,
				"qty": flt(balance.remaining_qty),
				"uom": row.uom,
				"stock_uom": row.stock_uom,
				"conversion_factor": row.conversion_factor or 1,
				"basic_rate": row.basic_rate,
				"valuation_rate": row.valuation_rate,
				"allow_zero_valuation_rate": row.allow_zero_valuation_rate,
				"set_basic_rate_manually": row.set_basic_rate_manually,
				"expense_account": row.expense_account,
				"project": row.project or stock_entry.get("project") or original.project,
				"cost_center": row.cost_center or stock_entry.get("cost_center") or original.cost_center,
				"batch_no": row.batch_no,
				"serial_no": row.serial_no,
				"use_serial_batch_fields": row.use_serial_batch_fields,
				"against_stock_entry": stock_entry.name,
				"ste_detail": row.name,
			},
		)

	if not return_entry.items:
		frappe.throw(_("All issued material has already been returned."))

	return return_entry.as_dict()


def get_reverse_stock_entry_purpose(stock_entry):
	if stock_entry.purpose == "Material Issue":
		return "Material Receipt"
	if stock_entry.purpose == "Material Receipt":
		return "Material Issue"
	return stock_entry.purpose


def get_stock_entry_return_balances(stock_entry_name, exclude_stock_entry=None):
	stock_entry = frappe.get_doc("Stock Entry", stock_entry_name)
	if stock_entry.docstatus != 1:
		frappe.throw(_("Original Stock Entry {0} must be submitted.").format(frappe.bold(stock_entry_name)))

	returned_qty_by_detail = get_submitted_return_stock_entry_qty(stock_entry_name, exclude_stock_entry)
	balances = {}
	for row in stock_entry.items:
		original_transfer_qty = flt(row.transfer_qty) or (flt(row.qty) * flt(row.conversion_factor or 1))
		returned_transfer_qty = flt(returned_qty_by_detail.get(row.name))
		remaining_transfer_qty = max(original_transfer_qty - returned_transfer_qty, 0)
		conversion_factor = flt(row.conversion_factor or 1) or 1
		balances[row.name] = frappe._dict(
			{
				"original_row": row,
				"original_transfer_qty": original_transfer_qty,
				"returned_transfer_qty": returned_transfer_qty,
				"remaining_transfer_qty": remaining_transfer_qty,
				"remaining_qty": remaining_transfer_qty / conversion_factor,
			}
		)

	return balances


def get_submitted_return_stock_entry_qty(stock_entry_name, exclude_stock_entry=None):
	conditions = [
		"se.docstatus = 1",
		"se.is_return = 1",
		"sed.against_stock_entry = %(stock_entry)s",
	]
	values = {"stock_entry": stock_entry_name}
	if exclude_stock_entry:
		conditions.append("se.name != %(exclude_stock_entry)s")
		values["exclude_stock_entry"] = exclude_stock_entry

	rows = frappe.db.sql(
		f"""
		select
			sed.ste_detail,
			sum(sed.transfer_qty) as returned_transfer_qty
		from `tabStock Entry` se
		inner join `tabStock Entry Detail` sed on sed.parent = se.name
		where {" and ".join(conditions)}
		group by sed.ste_detail
		""",
		values,
		as_dict=True,
	)
	return {row.ste_detail: flt(row.returned_transfer_qty) for row in rows if row.ste_detail}


def validate_site_material_return_stock_entry(doc, method=None):
	if not cint(doc.get("is_return")):
		return

	site_stock_entries = {
		row.against_stock_entry
		for row in doc.items
		if row.against_stock_entry
		and frappe.db.exists("Site Material Consumption", {"stock_entry": row.against_stock_entry})
	}
	if not site_stock_entries:
		return
	if len(site_stock_entries) > 1:
		frappe.throw(_("Return Stock Entry can reference only one original Site Material Consumption Stock Entry."))

	original_stock_entry = next(iter(site_stock_entries))
	original = frappe.get_doc("Stock Entry", original_stock_entry)
	if original.docstatus != 1:
		frappe.throw(_("Original Stock Entry {0} must be submitted.").format(frappe.bold(original_stock_entry)))
	if doc.company != original.company:
		frappe.throw(_("Return Stock Entry company must match the original Stock Entry."))

	original_rows = {row.name: row for row in original.items}
	balances = get_stock_entry_return_balances(
		original_stock_entry,
		exclude_stock_entry=doc.name if not doc.is_new() else None,
	)

	for row in doc.items:
		if row.against_stock_entry != original_stock_entry:
			frappe.throw(_("Row {0}: Return item must reference the original Stock Entry.").format(row.idx))
		if not row.ste_detail or row.ste_detail not in original_rows:
			frappe.throw(_("Row {0}: Return item must reference an original Stock Entry row.").format(row.idx))

		original_row = original_rows[row.ste_detail]
		if row.item_code != original_row.item_code:
			frappe.throw(_("Row {0}: Item must match the original Stock Entry row.").format(row.idx))
		if row.s_warehouse != original_row.t_warehouse or row.t_warehouse != original_row.s_warehouse:
			frappe.throw(_("Row {0}: Warehouses must reverse the original Stock Entry movement.").format(row.idx))
		if flt(row.qty) <= 0:
			frappe.throw(_("Row {0}: Return quantity must be greater than zero.").format(row.idx))

		transfer_qty = flt(row.transfer_qty) or (flt(row.qty) * flt(row.conversion_factor or 1))
		remaining_transfer_qty = flt(balances[row.ste_detail].remaining_transfer_qty)
		if transfer_qty > remaining_transfer_qty:
			frappe.throw(
				_("Row {0}: Return quantity cannot exceed remaining returnable quantity {1} {2}.").format(
					row.idx,
					flt(balances[row.ste_detail].remaining_qty),
					original_row.uom or original_row.stock_uom,
				)
			)
