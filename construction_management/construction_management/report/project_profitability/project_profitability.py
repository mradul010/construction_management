from collections import defaultdict
from decimal import Decimal

import frappe
from frappe import _
from frappe.desk.reportview import build_match_conditions
from frappe.desk.query_report import get_report_doc
from frappe.utils import add_days, add_months, cint, flt, formatdate, getdate, today
from erpnext import get_company_currency
from erpnext.accounts.utils import get_fiscal_year
from erpnext.accounts.report.general_ledger.general_ledger import get_accounts_with_children
from erpnext.accounts.report.financial_statements import get_cost_centers_with_children


METRICS = {"Income": "income", "Expenses": "expenses", "Gross Profit": "gross_profit", "Net Profit": "net_profit"}
AMOUNTS = ("income", "direct_expenses", "indirect_expenses", "unclassified_expenses")


def normalize(filters):
	filters = frappe._dict(frappe.parse_json(filters) or {})
	frappe.has_permission("GL Entry", "read", throw=True)
	get_report_doc("Project Profitability")
	if not filters.company:
		frappe.throw(_("Company is mandatory"))
	frappe.get_doc("Company", filters.company).check_permission("read")
	if filters.fiscal_year:
		fy = frappe.get_doc("Fiscal Year", filters.fiscal_year)
		if fy.disabled or (fy.companies and filters.company not in [c.company for c in fy.companies]):
			frappe.throw(_("Fiscal Year is not available for this company"))
	else:
		fy_name = get_fiscal_year(filters.get("to_date") or today(), company=filters.company)[0]
		fy = frappe.get_doc("Fiscal Year", fy_name)
	filters.from_date = getdate(filters.get("from_date") or filters.get("start_date") or fy.year_start_date)
	filters.to_date = getdate(filters.get("to_date") or filters.get("end_date") or fy.year_end_date)
	if filters.from_date > filters.to_date:
		frappe.throw(_("From Date must be before To Date"))
	filters.period_type = filters.get("period_type") or "Monthly"
	filters.view_type = filters.get("view_type") or "Summary"
	filters.metric = filters.get("metric") or "Net Profit"
	if filters.period_type not in ("Monthly", "Quarterly", "Yearly") or filters.metric not in METRICS:
		frappe.throw(_("Invalid period type or metric"))
	if filters.view_type not in ("Summary", "Detailed Accounts", "Cost Center Breakdown", "Timesheet Profitability"):
		frappe.throw(_("Invalid view type"))
	filters.include_default_book_entries = cint(filters.get("include_default_book_entries", 1))
	return filters


def get_periods(filters):
	periods = []
	cursor = filters.from_date
	while cursor <= filters.to_date:
		fy, start, end = get_fiscal_year(cursor, company=filters.company)
		start, end = getdate(start), getdate(end)
		if filters.period_type == "Yearly":
			stop, label = end, _("FY {0}").format(fy)
		else:
			months = 1 if filters.period_type == "Monthly" else 3
			index = 0
			while getdate(add_months(start, (index + 1) * months)) <= cursor:
				index += 1
			stop = min(getdate(add_days(add_months(start, (index + 1) * months), -1)), end)
			label = formatdate(cursor, "MMM yyyy") if months == 1 else _("{0} Q{1}").format(fy, index + 1)
		periods.append(frappe._dict(key=f"period_{len(periods)}", label=label, from_date=cursor, to_date=min(stop, filters.to_date)))
		cursor = getdate(add_days(periods[-1].to_date, 1))
	return periods


def account_classes(accounts):
	by_name = {a.name: a for a in accounts}
	result = {}
	for account in accounts:
		if account.root_type == "Income":
			result[account.name] = "income"
			continue
		node, seen = account, set()
		classification = "unclassified_expenses"
		while node and node.name not in seen:
			seen.add(node.name)
			if node.get("custom_profitability_classification"):
				classification = "direct_expenses" if node.custom_profitability_classification == "Direct" else "indirect_expenses"
				break
			if node.account_type == "Cost of Goods Sold":
				classification = "direct_expenses"
				break
			node = by_name.get(node.parent_account)
		result[account.name] = classification
	return result


def get_scope(filters):
	projects = frappe.get_list("Project", filters={"company": filters.company}, fields=["name", "project_name", "customer"], limit_page_length=0)
	if filters.project:
		projects = [p for p in projects if p.name == filters.project]
	if filters.customer:
		projects = [p for p in projects if p.customer == filters.customer]
	accounts = frappe.get_list("Account", filters={"company": filters.company, "root_type": ["in", ["Income", "Expense"]], "report_type": "Profit and Loss"},
		fields=["name", "parent_account", "root_type", "account_type", "is_group", "lft", "custom_profitability_classification"], limit_page_length=0)
	selected = {a.name for a in accounts if not a.is_group}
	if filters.account:
		selected.intersection_update(get_accounts_with_children(filters.account) or [])
	return projects, accounts, selected


def read_entries(filters, projects, accounts, raw=False, include_special=False):
	if not accounts or ((filters.project or filters.customer) and not projects):
		return []
	values = dict(company=filters.company, from_date=filters.from_date, to_date=filters.to_date,
		accounts=tuple(accounts), projects=tuple(p.name for p in projects) or ("",))
	conditions = ["`tabGL Entry`.company=%(company)s", "`tabGL Entry`.docstatus=1", "`tabGL Entry`.is_cancelled=0",
		"`tabGL Entry`.posting_date BETWEEN %(from_date)s AND %(to_date)s", "`tabGL Entry`.account IN %(accounts)s"]
	if not include_special:
		conditions.append("`tabGL Entry`.voucher_type != 'Period Closing Voucher'")
		if not frappe.get_single_value("Accounts Settings", "ignore_is_opening_check_for_reporting"):
			conditions.append("COALESCE(`tabGL Entry`.is_opening, 'No') != 'Yes'")
	# Untagged postings are reported separately, never allocated to a selected project.
	conditions.append("(`tabGL Entry`.project IN %(projects)s OR COALESCE(`tabGL Entry`.project, '')='')")
	if filters.cost_center:
		frappe.get_doc("Cost Center", filters.cost_center).check_permission("read")
		allowed = frappe.get_list("Cost Center", filters={"company": filters.company, "name": ["in", get_cost_centers_with_children([filters.cost_center])]}, pluck="name", limit_page_length=0)
		if not allowed:
			return []
		values["centers"] = tuple(allowed) or ("",)
		conditions.append("`tabGL Entry`.cost_center IN %(centers)s")
	company_fb = frappe.get_cached_value("Company", filters.company, "default_finance_book") or ""
	if filters.include_default_book_entries and filters.finance_book and company_fb and filters.finance_book != company_fb:
		frappe.throw(_("Uncheck Include Default FB Entries to use another Finance Book"))
	values["book"] = filters.finance_book or (company_fb if filters.include_default_book_entries else "")
	conditions.append("(COALESCE(`tabGL Entry`.finance_book, '') IN (%(book)s, ''))")
	match = build_match_conditions("GL Entry")
	if match:
		conditions.append(f"({match})")
	if raw:
		select = "name, posting_date, project, cost_center, account, voucher_type, voucher_no, debit, credit, is_opening"
		group = "ORDER BY posting_date, creation"
	else:
		select = "posting_date, project, cost_center, account, SUM(debit-credit) AS balance, COUNT(*) AS entries"
		group = "GROUP BY posting_date, project, cost_center, account"
	return frappe.db.sql(f"SELECT {select} FROM `tabGL Entry` WHERE {' AND '.join(conditions)} {group}", values, as_dict=True)


def money(value, currency):
	return flt(value, frappe.get_precision("GL Entry", "debit", currency=currency))


def totals(entries, classes, currency):
	result = {key: Decimal(0) for key in AMOUNTS}
	unclassified = False
	for entry in entries:
		key = classes[entry.account]
		balance = Decimal(str(entry.balance))
		result[key] += -balance if key == "income" else balance
		unclassified |= key == "unclassified_expenses"
	result = {k: money(v, currency) for k, v in result.items()}
	result["expenses"] = money(sum(result[k] for k in AMOUNTS[1:]), currency)
	result["gross_profit"] = None if unclassified else money(result["income"] - result["direct_expenses"], currency)
	result["net_profit"] = money(result["income"] - result["expenses"], currency)
	result["margin"] = flt(result["net_profit"] / result["income"] * 100, 2) if result["income"] else 0
	return result


def currency_column(key, label):
	return {"fieldname": key, "label": _(label), "fieldtype": "Currency", "options": "currency", "width": 155}


def execute(filters=None):
	filters = normalize(filters)
	if filters.view_type == "Timesheet Profitability":
		from hrms.hr.report.project_profitability.project_profitability import execute as timesheets
		return timesheets(frappe._dict(filters, start_date=filters.from_date, end_date=filters.to_date))
	periods = get_periods(filters)
	projects, accounts, selected = get_scope(filters)
	classes = account_classes(accounts)
	entries = read_entries(filters, projects, selected)
	currency = get_company_currency(filters.company)
	mapped = [e for e in entries if e.project]
	unmapped = [e for e in entries if not e.project]
	columns = [{"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Project", "width": 140, "hidden": 1},
		{"fieldname": "project_name", "label": _("Project Name"), "fieldtype": "Data", "width": 230}]
	if filters.view_type != "Summary":
		columns += [{"fieldname": "label", "label": _("Account / Cost Center"), "fieldtype": "Data", "width": 320}]
	for key, label in (("income", "Total Income"), ("direct_expenses", "Direct Expenses"), ("gross_profit", "Gross Profit/Loss"),
		("indirect_expenses", "Indirect Expenses"), ("unclassified_expenses", "Unclassified Expenses"), ("expenses", "Total Expenses"), ("net_profit", "Net Profit/Loss")):
		columns.append(currency_column(key, label))
	columns += [{"fieldname": "margin", "label": _("Net Profit Margin %"), "fieldtype": "Percent", "width": 140}]
	columns += [currency_column(p.key, p.label) for p in periods] + [currency_column("total", "Total")]
	columns += [{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1}]
	groups = defaultdict(list)
	for entry in mapped:
		groups[entry.project].append(entry)
	rows = []
	metric = METRICS[filters.metric]
	def make_row(project, subset, **extra):
		row = dict(project=project.name if project else None, project_name=project.project_name if project else _("Grand Total"), currency=currency, **extra)
		row.update(totals(subset, classes, currency))
		row["total"] = row[metric]
		row["_periods"] = {p.key: {"from_date": str(p.from_date), "to_date": str(p.to_date)} for p in periods}
		for period in periods:
			row[period.key] = totals([e for e in subset if period.from_date <= e.posting_date <= period.to_date], classes, currency)[metric]
		return row
	account_map = {a.name: a for a in accounts}
	for project in projects:
		subset = groups.get(project.name)
		if not subset:
			continue
		rows.append(make_row(project, subset, indent=0, is_group=filters.view_type != "Summary"))
		if filters.view_type == "Detailed Accounts":
			for key in AMOUNTS:
				section = [e for e in subset if classes[e.account] == key]
				if not section:
					continue
				rows.append(make_row(project, section, label=_(key.replace("_", " ").title()), indent=1, _category=key))
				# Only leaf postings are summed. Ancestor labels retain the actual CoA path.
				for account in sorted({e.account for e in section}, key=lambda a: account_map[a].lft):
					path, node = [], account_map[account]
					while node:
						path.append(node.name)
						node = account_map.get(node.parent_account)
					rows.append(make_row(project, [e for e in section if e.account == account], label=" / ".join(reversed(path)), account=account, indent=2))
		elif filters.view_type == "Cost Center Breakdown":
			for center in sorted({e.cost_center or "" for e in subset}):
				section = [e for e in subset if (e.cost_center or "") == center]
				rows.append(make_row(project, section, label=center or _("No Cost Center"), cost_center=center, _exact_center=True, indent=1))
				for account in sorted({e.account for e in section}):
					rows.append(make_row(project, [e for e in section if e.account == account], label=account, account=account, cost_center=center, _exact_center=True, indent=2))
	if rows:
		rows.append(make_row(None, mapped, _grand_total=True))
	message = []
	if not mapped:
		message.append(_("No accounting transactions found for the selected company, project and period."))
		if unmapped:
			message.append(_("Income/Expense entries exist without a Project mapping; these are excluded from project totals."))
		else:
			count = frappe.get_list("GL Entry", filters={"company": filters.company, "posting_date": ["between", [filters.from_date, filters.to_date]], "docstatus": 1, "is_cancelled": 0}, pluck="name", limit_page_length=1)
			message.append(_("No submitted GL entries in this company and period.") if not count else _("GL entries exist, but no accessible Income/Expense entries match the selected Project, Account, Cost Center or Finance Book filters."))
	if any(classes[e.account] == "unclassified_expenses" for e in mapped):
		message.append(_("Some expenses are unclassified. Configure Project Profitability Classification on the Account or its parent. Gross profit is unavailable until all expenses are classified; net profit includes all expenses."))
	unmapped_totals = totals(unmapped, classes, currency)
	summary = [{"label": _("Unmapped Income (excluded)"), "value": unmapped_totals["income"], "datatype": "Currency", "currency": currency},
		{"label": _("Unmapped Expenses (excluded)"), "value": unmapped_totals["expenses"], "datatype": "Currency", "currency": currency}]
	return columns, rows, "<br>".join(message), None, summary, True


@frappe.whitelist()
def fiscal_dates(company, fiscal_year=None):
	frappe.has_permission("GL Entry", "read", throw=True)
	frappe.get_doc("Company", company).check_permission("read")
	name = fiscal_year or get_fiscal_year(today(), company=company)[0]
	fy = frappe.get_doc("Fiscal Year", name)
	if fy.disabled or (fy.companies and company not in [c.company for c in fy.companies]):
		frappe.throw(_("Fiscal Year is not available for this company"))
	return dict(fiscal_year=name, from_date=fy.year_start_date, to_date=fy.year_end_date)


@frappe.whitelist()
def drilldown(filters, context):
	filters = normalize(filters)
	context = frappe._dict(frappe.parse_json(context))
	projects, accounts, selected = get_scope(filters)
	if context.project:
		projects = [p for p in projects if p.name == context.project]
		filters.project = context.project
	classes = account_classes(accounts)
	if context.account:
		selected.intersection_update([context.account])
	metric = METRICS.get(context.get("metric"), context.get("fieldname"))
	if metric == "income":
		selected = {a for a in selected if classes[a] == "income"}
	elif metric in AMOUNTS[1:]:
		selected = {a for a in selected if classes[a] == metric}
	elif metric == "expenses":
		selected = {a for a in selected if classes[a] != "income"}
	elif metric == "gross_profit":
		selected = {a for a in selected if classes[a] in ("income", "direct_expenses")}
	if context.category:
		selected = {a for a in selected if classes[a] == context.category}
	if context.from_date:
		filters.from_date = max(filters.from_date, getdate(context.from_date))
		filters.to_date = min(filters.to_date, getdate(context.to_date))
	if filters.from_date > filters.to_date:
		frappe.throw(_("Invalid drill-down period"))
	all_entries = read_entries(filters, projects, selected, raw=True, include_special=True)
	entries = read_entries(filters, projects, selected, raw=True)
	entries = [e for e in entries if e.project]
	if context.get("exact_center"):
		entries = [e for e in entries if (e.cost_center or "") == (context.cost_center or "")]
		all_entries = [e for e in all_entries if (e.cost_center or "") == (context.cost_center or "")]
	# GL always expands group Cost Centers and includes special opening entries.
	# An exact transaction breakdown is available when its standard filters cannot reproduce scope.
	center = context.cost_center if context.get("exact_center") else filters.cost_center
	group = center and frappe.get_cached_value("Cost Center", center, "is_group")
	opening = frappe.get_list("GL Entry", filters={"company": filters.company, "project": ["in", [p.name for p in projects]], "account": ["in", sorted(selected)], "is_opening": "Yes", "is_cancelled": 0}, pluck="name", limit_page_length=1) if selected and projects else []
	if not projects or not selected or (context.get("exact_center") and (not center or group)) or opening or len(entries) != len([e for e in all_entries if e.project]):
		return {"entries": entries, "breakdown": True, "currency": get_company_currency(filters.company)}
	ledger_filters = {
		"company": filters.company, "from_date": str(filters.from_date), "to_date": str(filters.to_date),
		"project": [p.name for p in projects], "cost_center": [center] if center else [], "account": sorted(selected),
		"finance_book": filters.finance_book or "", "include_default_book_entries": filters.include_default_book_entries,
		"show_cancelled_entries": 0, "disable_opening_balance_calculation": 1, "show_opening_entries": 1,
		"categorize_by": "", "presentation_currency": get_company_currency(filters.company),
		"voucher_no": "", "against_voucher_no": "", "party_type": "", "party": [], "ignore_err": 0, "ignore_cr_dr_notes": 0,
		"show_net_values_in_party_account": 0,
		"include_dimensions": 1,
	}
	from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_accounting_dimensions
	for fieldname in get_accounting_dimensions():
		ledger_filters[fieldname] = []
	return {"breakdown": False, "filters": ledger_filters}
