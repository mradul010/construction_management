from frappe import _

import frappe
from frappe.utils import cint, flt, getdate

from erpnext import get_company_currency
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
	get_accounting_dimensions,
	get_dimension_with_children,
)
from erpnext.accounts.report.financial_statements import get_cost_centers_with_children
from erpnext.accounts.report.general_ledger.general_ledger import get_accounts_with_children


ROOT_TYPES = {"Asset", "Liability", "Equity", "Income", "Expense"}
MANAGEMENT_SUMMARY_VIEW = "Cost Summary"
ACCOUNTING_SUMMARY_VIEW = "Accounting Summary"
DETAIL_VIEW = "Transaction Details"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	columns = get_columns(filters)
	data = get_data(filters)
	report_summary = get_report_summary(data, filters)

	return columns, data, None, None, report_summary


def validate_filters(filters):
	normalize_view_mode(filters)

	if filters.get("include_child_cost_centers") is None:
		filters.include_child_cost_centers = 1
	if filters.get("include_default_book_entries") is None:
		filters.include_default_book_entries = 1
	if filters.get("show_cancelled_entries") is None:
		filters.show_cancelled_entries = 0
	if filters.get("account_type") is None and filters.view_mode != ACCOUNTING_SUMMARY_VIEW:
		filters.account_type = "Expense"

	if not filters.get("company"):
		frappe.throw(_("{0} is mandatory").format(_("Company")))

	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(
			_("{0} and {1} are mandatory").format(frappe.bold(_("From Date")), frappe.bold(_("To Date")))
		)

	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date must be before To Date"))

	if filters.get("cost_center"):
		cost_center_company = frappe.db.get_value("Cost Center", filters.cost_center, "company")
		if not cost_center_company:
			frappe.throw(_("Cost Center {0} does not exist").format(filters.cost_center))
		if cost_center_company != filters.company:
			frappe.throw(_("Cost Center {0} does not belong to company {1}").format(filters.cost_center, filters.company))

	if filters.get("account"):
		account_company = frappe.db.get_value("Account", filters.account, "company")
		if not account_company:
			frappe.throw(_("Account {0} does not exist").format(filters.account))
		if account_company != filters.company:
			frappe.throw(_("Account {0} does not belong to company {1}").format(filters.account, filters.company))


def normalize_view_mode(filters):
	if filters.get("view_mode") in (None, "", "Summary"):
		filters.view_mode = MANAGEMENT_SUMMARY_VIEW


def get_columns(filters):
	if filters.get("view_mode") == DETAIL_VIEW:
		return get_detail_columns()
	if filters.get("view_mode") == ACCOUNTING_SUMMARY_VIEW:
		return get_accounting_summary_columns()
	return get_summary_columns()


def get_summary_columns():
	return [
		{
			"label": _("Cost Center"),
			"fieldname": "cost_center",
			"fieldtype": "Link",
			"options": "Cost Center",
			"width": 240,
		},
		{
			"label": _("Parent Cost Center"),
			"fieldname": "parent_cost_center",
			"fieldtype": "Link",
			"options": "Cost Center",
			"width": 220,
		},
		{
			"label": _("Cost Spent"),
			"fieldname": "cost_spent",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 170,
		},
		{
			"label": _("Currency"),
			"fieldname": "currency",
			"fieldtype": "Link",
			"options": "Currency",
			"hidden": 1,
		},
	]


def get_accounting_summary_columns():
	return [
		{
			"label": _("Cost Center"),
			"fieldname": "cost_center",
			"fieldtype": "Link",
			"options": "Cost Center",
			"width": 240,
		},
		{
			"label": _("Parent Cost Center"),
			"fieldname": "parent_cost_center",
			"fieldtype": "Link",
			"options": "Cost Center",
			"width": 220,
		},
		{
			"label": _("Total Debit"),
			"fieldname": "total_debit",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
		{
			"label": _("Total Credit"),
			"fieldname": "total_credit",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
		{
			"label": _("Net Balance"),
			"fieldname": "net_balance",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
		{
			"label": _("Currency"),
			"fieldname": "currency",
			"fieldtype": "Link",
			"options": "Currency",
			"hidden": 1,
		},
	]


def get_detail_columns():
	columns = [
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
		{
			"label": _("Cost Center"),
			"fieldname": "cost_center",
			"fieldtype": "Link",
			"options": "Cost Center",
			"width": 210,
		},
		{
			"label": _("Account"),
			"fieldname": "account",
			"fieldtype": "Link",
			"options": "Account",
			"width": 210,
		},
		{"label": _("Account Name"), "fieldname": "account_name", "fieldtype": "Data", "width": 180},
		{"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Link", "options": "DocType", "width": 140},
		{
			"label": _("Voucher No"),
			"fieldname": "voucher_no",
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 180,
		},
		{"label": _("Against"), "fieldname": "against", "fieldtype": "Data", "width": 170},
		{"label": _("Remarks"), "fieldname": "remarks", "fieldtype": "Data", "width": 260},
		{"label": _("Cost Spent"), "fieldname": "cost_spent", "fieldtype": "Currency", "options": "currency", "width": 140},
	]

	if frappe.get_meta("GL Entry").has_field("project"):
		columns.append(
			{
				"label": _("Project"),
				"fieldname": "project",
				"fieldtype": "Link",
				"options": "Project",
				"width": 170,
			}
		)

	columns.extend(
		[
			{"label": _("Created On"), "fieldname": "creation", "fieldtype": "Datetime", "width": 160},
			{
				"label": _("Currency"),
				"fieldname": "currency",
				"fieldtype": "Link",
				"options": "Currency",
				"hidden": 1,
			},
		]
	)
	return columns


def get_data(filters):
	if filters.get("view_mode") == DETAIL_VIEW:
		return get_detail_data(filters)
	return get_summary_data(filters)


def get_summary_data(filters):
	conditions, values = get_conditions(filters)
	currency = get_company_currency(filters.company)

	rows = frappe.db.sql(
		f"""
		SELECT
			`tabGL Entry`.`cost_center` AS cost_center,
			cc.`parent_cost_center` AS parent_cost_center,
			COALESCE(SUM(`tabGL Entry`.`debit`), 0) AS total_debit,
			COALESCE(SUM(`tabGL Entry`.`credit`), 0) AS total_credit,
			COALESCE(SUM(`tabGL Entry`.`debit` - `tabGL Entry`.`credit`), 0) AS net_balance,
			COALESCE(SUM(`tabGL Entry`.`debit` - `tabGL Entry`.`credit`), 0) AS cost_spent,
			%(currency)s AS currency
		FROM `tabGL Entry`
		LEFT JOIN `tabCost Center` cc ON cc.`name` = `tabGL Entry`.`cost_center`
		LEFT JOIN `tabAccount` acc ON acc.`name` = `tabGL Entry`.`account`
		WHERE {" AND ".join(conditions)}
		GROUP BY `tabGL Entry`.`cost_center`, cc.`parent_cost_center`
		ORDER BY cc.`lft` ASC, `tabGL Entry`.`cost_center` ASC
		""",
		values | {"currency": currency},
		as_dict=True,
	)

	if not rows and filters.get("cost_center"):
		return get_zero_activity_cost_center_rows(filters, currency)

	return rows


def get_detail_data(filters):
	conditions, values = get_conditions(filters)
	currency = get_company_currency(filters.company)
	project_field = "`tabGL Entry`.`project` AS project," if frappe.get_meta("GL Entry").has_field("project") else ""

	rows = frappe.db.sql(
		f"""
		SELECT
			`tabGL Entry`.`posting_date`,
			`tabGL Entry`.`cost_center`,
			`tabGL Entry`.`account`,
			acc.`account_name`,
			`tabGL Entry`.`voucher_type`,
			`tabGL Entry`.`voucher_no`,
			`tabGL Entry`.`against`,
			`tabGL Entry`.`party_type`,
			`tabGL Entry`.`party`,
			`tabGL Entry`.`remarks`,
			`tabGL Entry`.`debit`,
			`tabGL Entry`.`credit`,
			(`tabGL Entry`.`debit` - `tabGL Entry`.`credit`) AS net_amount,
			(`tabGL Entry`.`debit` - `tabGL Entry`.`credit`) AS cost_spent,
			{project_field}
			`tabGL Entry`.`creation`,
			%(currency)s AS currency
		FROM `tabGL Entry`
		LEFT JOIN `tabAccount` acc ON acc.`name` = `tabGL Entry`.`account`
		LEFT JOIN `tabCost Center` cc ON cc.`name` = `tabGL Entry`.`cost_center`
		WHERE {" AND ".join(conditions)}
		ORDER BY `tabGL Entry`.`cost_center` ASC, `tabGL Entry`.`posting_date` ASC, `tabGL Entry`.`creation` ASC
		""",
		values | {"currency": currency},
		as_dict=True,
	)

	return rows


def get_conditions(filters):
	values = {
		"company": filters.company,
		"from_date": filters.from_date,
		"to_date": filters.to_date,
	}
	conditions = [
		"`tabGL Entry`.`company` = %(company)s",
		"`tabGL Entry`.`posting_date` >= %(from_date)s",
		"`tabGL Entry`.`posting_date` <= %(to_date)s",
		"`tabGL Entry`.`cost_center` IS NOT NULL",
		"`tabGL Entry`.`cost_center` != ''",
	]

	if filters.get("cost_center"):
		cost_centers = get_filtered_cost_centers(filters)
		values["cost_centers"] = tuple(cost_centers)
		conditions.append("`tabGL Entry`.`cost_center` IN %(cost_centers)s")

	if filters.get("account"):
		accounts = get_accounts_with_children(filters.account) or [filters.account]
		values["accounts"] = tuple(accounts)
		conditions.append("`tabGL Entry`.`account` IN %(accounts)s")

	if filters.get("account_type"):
		values["account_type"] = filters.account_type
		if filters.account_type in ROOT_TYPES:
			conditions.append("acc.`root_type` = %(account_type)s")
		else:
			conditions.append("acc.`account_type` = %(account_type)s")

	if filters.get("voucher_type"):
		values["voucher_type"] = filters.voucher_type
		conditions.append("`tabGL Entry`.`voucher_type` = %(voucher_type)s")

	if filters.get("voucher_no"):
		values["voucher_no"] = filters.voucher_no
		conditions.append("`tabGL Entry`.`voucher_no` = %(voucher_no)s")

	if filters.get("project") and frappe.get_meta("GL Entry").has_field("project"):
		values["project"] = filters.project
		conditions.append("`tabGL Entry`.`project` = %(project)s")

	add_accounting_dimension_conditions(filters, conditions, values)
	add_finance_book_conditions(filters, conditions, values)

	if not cint(filters.get("show_cancelled_entries")):
		conditions.append("`tabGL Entry`.`is_cancelled` = 0")

	from frappe.desk.reportview import build_match_conditions

	match_conditions = build_match_conditions("GL Entry")
	if match_conditions:
		conditions.append(f"({match_conditions})")

	return conditions, values


def get_filtered_cost_centers(filters):
	if cint(filters.get("include_child_cost_centers")):
		return get_cost_centers_with_children(filters.cost_center)
	return [filters.cost_center]


def add_accounting_dimension_conditions(filters, conditions, values):
	gl_meta = frappe.get_meta("GL Entry")
	for dimension in get_accounting_dimensions(as_list=False):
		if dimension.document_type == "Finance Book" or not gl_meta.has_field(dimension.fieldname):
			continue

		dimension_values = normalize_filter_values(filters.get(dimension.fieldname))
		if not dimension_values:
			continue

		if frappe.get_cached_value("DocType", dimension.document_type, "is_tree"):
			dimension_values = get_dimension_with_children(dimension.document_type, dimension_values)

		values[dimension.fieldname] = tuple(dimension_values)
		conditions.append(f"`tabGL Entry`.`{dimension.fieldname}` IN %({dimension.fieldname})s")


def normalize_filter_values(value):
	if not value:
		return []

	if isinstance(value, str):
		try:
			parsed_value = frappe.parse_json(value)
		except Exception:
			return [value]
		if isinstance(parsed_value, str):
			return [parsed_value]
		return list(parsed_value or [])

	if isinstance(value, tuple):
		return list(value)

	if isinstance(value, list):
		return value

	return [value]


def get_zero_activity_cost_center_rows(filters, currency):
	cost_centers = get_filtered_cost_centers(filters)
	rows = frappe.get_list(
		"Cost Center",
		filters={"name": ["in", cost_centers], "company": filters.company},
		fields=["name", "parent_cost_center"],
		order_by="lft asc, name asc",
	)

	return [
		{
			"cost_center": row.name,
			"parent_cost_center": row.parent_cost_center,
			"total_debit": 0,
			"total_credit": 0,
			"net_balance": 0,
			"cost_spent": 0,
			"currency": currency,
		}
		for row in rows
	]


def add_finance_book_conditions(filters, conditions, values):
	if cint(filters.get("include_default_book_entries")):
		company_fb = frappe.get_cached_value("Company", filters.company, "default_finance_book")
		values["company_fb"] = company_fb or ""

		if filters.get("finance_book"):
			values["finance_book"] = filters.finance_book
			if company_fb and filters.finance_book != company_fb:
				frappe.throw(_("To use a different finance book, please uncheck 'Include Default FB Entries'"))
			conditions.append(
				"(`tabGL Entry`.`finance_book` IN (%(finance_book)s, '') OR `tabGL Entry`.`finance_book` IS NULL)"
			)
		elif company_fb:
			conditions.append(
				"(`tabGL Entry`.`finance_book` IN (%(company_fb)s, '') OR `tabGL Entry`.`finance_book` IS NULL)"
			)
		else:
			conditions.append("(`tabGL Entry`.`finance_book` IN ('') OR `tabGL Entry`.`finance_book` IS NULL)")
	elif filters.get("finance_book"):
		values["finance_book"] = filters.finance_book
		conditions.append(
			"(`tabGL Entry`.`finance_book` IN (%(finance_book)s, '') OR `tabGL Entry`.`finance_book` IS NULL)"
		)
	else:
		conditions.append("(`tabGL Entry`.`finance_book` IN ('') OR `tabGL Entry`.`finance_book` IS NULL)")


def get_report_summary(data, filters):
	currency = get_company_currency(filters.company)
	total_cost_spent = sum(flt(row.get("cost_spent")) for row in data)
	cost_centers = {row.get("cost_center") for row in data if row.get("cost_center")}

	if filters.get("view_mode") != ACCOUNTING_SUMMARY_VIEW:
		return [
			{
				"value": total_cost_spent,
				"label": _("Cost Spent"),
				"datatype": "Currency",
				"currency": currency,
				"indicator": "Blue",
			},
			{
				"value": len(cost_centers),
				"label": _("Cost Centers"),
				"datatype": "Int",
				"indicator": "Blue",
			},
		]

	debit_field = "total_debit"
	credit_field = "total_credit"
	total_debit = sum(flt(row.get(debit_field)) for row in data)
	total_credit = sum(flt(row.get(credit_field)) for row in data)

	return [
		{
			"value": total_debit,
			"label": _("Total Debit"),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Blue",
		},
		{
			"value": total_credit,
			"label": _("Total Credit"),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Orange",
		},
		{
			"value": total_debit - total_credit,
			"label": _("Net Movement"),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Green" if total_debit >= total_credit else "Red",
		},
		{
			"value": len(cost_centers),
			"label": _("Cost Centers"),
			"datatype": "Int",
			"indicator": "Blue",
		},
	]
