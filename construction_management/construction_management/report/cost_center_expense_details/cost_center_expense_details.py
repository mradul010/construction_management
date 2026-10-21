import frappe
from frappe import _
from frappe.desk.query_report import get_report_doc
from frappe.utils import cint, flt

from construction_management.construction_management.report.cost_center_transaction_analysis import (
	cost_center_transaction_analysis as source,
)


def execute(filters=None):
	get_report_doc("Cost Center Expense Details")
	get_report_doc("Cost Center Transaction Analysis")
	frappe.has_permission("GL Entry", "read", throw=True)
	filters = frappe._dict(frappe.parse_json(filters) or {})
	filters.view_mode = source.DETAIL_VIEW
	# QueryReport omits unchecked checks; do not restore the parent's checked defaults.
	filters.setdefault("include_child_cost_centers", 0)
	filters.setdefault("include_default_book_entries", 0)
	if filters.get("account_type") == "All":
		filters.account_type = ""
	source.validate_filters(filters)
	frappe.get_doc("Company", filters.company).check_permission("read")
	if filters.cost_center:
		frappe.get_doc("Cost Center", filters.cost_center).check_permission("read")

	# Reuse the parent selection including account metadata, dimensions and books.
	selected = source.get_detail_data(filters)
	data = []
	for row in selected:
		if cint(row.gl_docstatus) != 1 or cint(row.is_cancelled):
			continue
		data.append(dict(row, net_cost=row.cost_spent))
	project_ids = {row["project"] for row in data if row.get("project")}
	project_names = {
		project.name: project.project_name
		for project in frappe.get_list(
			"Project", filters={"name": ["in", sorted(project_ids)]},
			fields=["name", "project_name"], limit_page_length=0,
		)
	} if project_ids else {}
	for row in data:
		row["project_name"] = project_names.get(row.get("project")) or row.get("project")
	currency = source.get_company_currency(filters.company)
	precision = frappe.get_precision("GL Entry", "debit", currency=currency)
	parent_total = flt(sum(flt(r.cost_spent) for r in selected), precision)
	total = flt(sum(flt(r["net_cost"]) for r in data), precision)
	if parent_total != total:
		frappe.throw(_(
			"Cost details cannot reconcile with the parent selection because it contains draft or "
			"cancelled postings. Review the source filters."
		))
	summary = [
		{"label": _("Cost Center"), "value": filters.cost_center or _("All Selected Cost Centers"), "datatype": "Data"},
		{"label": _("Total Cost Spent"), "value": total, "datatype": "Currency", "currency": currency},
		{"label": _("Transaction Count"), "value": len(data), "datatype": "Int"},
	]
	message = None
	if filters.get("account_type") != "Expense":
		message = _(
			"This view preserves the source report's Account Type scope ({0}); "
			"explicitly selected non-expense costs are not reclassified."
		).format(frappe.utils.escape_html(filters.get("account_type") or _("All")))
	return get_columns(filters), data, message, None, summary


def get_columns(filters):
	columns = [
		{"fieldname": "project_name", "label": _("Project Name"), "fieldtype": "Data", "width": 220, "align": "left"},
		{"fieldname": "cost_center", "label": _("Cost Center"), "fieldtype": "Link", "options": "Cost Center", "width": 200, "align": "left"},
		{"fieldname": "posting_date", "label": _("Posting Date"), "fieldtype": "Date", "width": 120, "align": "center"},
	]
	for key, label in (("debit", "Debit"), ("credit", "Credit"), ("net_cost", "Net Cost")):
		columns.append({"fieldname": key, "label": _(label), "fieldtype": "Currency", "options": "currency", "width": 130, "align": "right", "precision": 2})
	columns.extend([
		{"fieldname": "voucher_type", "label": _("Voucher Type"), "fieldtype": "Link", "options": "DocType", "width": 150, "align": "left"},
		{"fieldname": "voucher_no", "label": _("Voucher Number"), "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 200, "align": "left"},
		{"fieldname": "remarks", "label": _("Remarks"), "fieldtype": "Data", "width": 300, "align": "left"},
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Project", "hidden": 1},
		{"fieldname": "account", "label": _("Expense Account") if filters.get("account_type") == "Expense" else _("Account"), "fieldtype": "Link", "options": "Account", "hidden": 1},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Data", "hidden": 1},
	])
	return columns
