import unittest
from unittest.mock import patch

import frappe

from construction_management.construction_management.report.cost_center_expense_details import (
	cost_center_expense_details as report,
)


class TestExpenseDetails(unittest.TestCase):
	def setUp(self):
		self.filters = dict(company="QBC", from_date="2026-09-21", to_date="2026-10-21")
		self.enterContext(patch.object(report, "get_report_doc"))
		self.enterContext(patch.object(frappe, "has_permission"))
		self.enterContext(patch.object(frappe, "get_doc"))
		self.enterContext(patch.object(frappe, "get_system_settings", return_value="Banker's Rounding"))
		self.enterContext(patch.object(frappe, "get_precision", return_value=2))
		self.enterContext(patch.object(report.source, "get_company_currency", return_value="AED"))
		self.rows = self.enterContext(patch.object(report.source, "get_detail_data", return_value=[]))

	def test_expense_default_and_negative_reversal(self):
		self.rows.return_value = [frappe._dict(gl_docstatus=1, is_cancelled=0, cost_spent=x) for x in (100, -25)]
		columns, rows, _, _, summary = report.execute(self.filters)
		self.assertEqual(self.rows.call_args.args[0].account_type, "Expense")
		self.assertEqual([r["net_cost"] for r in rows], [100, -25])
		self.assertEqual(summary[1]["value"], 75)
		voucher = next(c for c in columns if c["fieldname"] == "voucher_no")
		self.assertEqual((voucher["fieldtype"], voucher["options"]), ("Dynamic Link", "voucher_type"))

	def test_explicit_capitalized_scope_preserved(self):
		self.filters["account_type"] = "Asset"
		columns, _, message, _, _ = report.execute(self.filters)
		self.assertEqual(self.rows.call_args.args[0].account_type, "Asset")
		self.assertTrue(message)
		self.assertEqual(next(c for c in columns if c["fieldname"] == "account")["label"], "Account")

	def test_visible_column_order_width_alignment_and_currency_precision(self):
		columns = report.get_columns(frappe._dict(account_type="Expense"))
		visible = [c for c in columns if not c.get("hidden")]
		self.assertEqual(
			[(c["fieldname"], c["width"], c["align"]) for c in visible],
			[("project_name", 220, "left"), ("cost_center", 200, "left"),
			 ("posting_date", 120, "center"), ("debit", 130, "right"),
			 ("credit", 130, "right"), ("net_cost", 130, "right"),
			 ("voucher_type", 150, "left"), ("voucher_no", 200, "left"),
			 ("remarks", 300, "left")],
		)
		for column in visible[3:6]:
			self.assertEqual((column["fieldtype"], column["options"], column["precision"]), ("Currency", "currency", 2))

	def test_project_names_preserve_ids_and_amounts_with_fallback(self):
		projects = ("PROJ-0015", "PROJ-0016", "PROJ-MISSING", None)
		self.rows.return_value = [
			frappe._dict(project=project, gl_docstatus=1, is_cancelled=0, cost_spent=1500)
			for project in projects
		]
		with patch.object(frappe, "get_list", return_value=[
			frappe._dict(name="PROJ-0015", project_name="Emerald Hills Villa 95"),
			frappe._dict(name="PROJ-0016", project_name=""),
		]) as lookup:
			columns, rows, _, _, summary = report.execute(self.filters)
		lookup.assert_called_once()
		self.assertEqual([r["project"] for r in rows], list(projects))
		self.assertEqual([r["project_name"] for r in rows], ["Emerald Hills Villa 95", "PROJ-0016", "PROJ-MISSING", None])
		self.assertEqual(summary[1]["value"], 6000)
		self.assertEqual(summary[2]["value"], 4)
		self.assertEqual(next(c for c in columns if c["fieldname"] == "project")["hidden"], 1)
		self.assertEqual(next(c for c in columns if c["fieldname"] == "project_name")["label"], "Project Name")

	def test_omitted_unchecked_filters_stay_disabled_and_all_is_explicit(self):
		self.filters["account_type"] = "All"
		report.execute(self.filters)
		filters = self.rows.call_args.args[0]
		self.assertEqual(filters.include_child_cost_centers, 0)
		self.assertEqual(filters.include_default_book_entries, 0)
		self.assertEqual(filters.account_type, "")

	def test_draft_or_cancelled_amount_cannot_silently_disappear(self):
		for status, cancelled in ((0, 0), (1, 1)):
			self.rows.return_value = [frappe._dict(gl_docstatus=status, is_cancelled=cancelled, cost_spent=10)]
			with patch.object(frappe, "throw", side_effect=frappe.ValidationError), self.assertRaises(frappe.ValidationError):
				report.execute(self.filters)

	def test_route_preserves_scope_without_generated_accounts(self):
		center = frappe._dict(company="QBC", check_permission=lambda *args: None)
		self.filters.update(project="PROJ-0016", include_child_cost_centers=1, include_default_book_entries=0)
		with patch("frappe.desk.query_report.get_report_doc"), patch.object(frappe, "get_doc", return_value=center), patch.object(report.source, "get_accounting_dimensions", return_value=[]):
			filters = report.source.get_expense_detail_filters(self.filters, "Concrete - QBC", "GLE-1")["filters"]
		self.assertEqual(filters["include_child_cost_centers"], 0)
		self.assertEqual(filters["gl_entry"], "GLE-1")
		self.assertEqual(filters["account"], "")
		self.assertEqual(filters["project"], "PROJ-0016")
		self.assertEqual(filters["include_default_book_entries"], 0)
		self.assertEqual(frappe.parse_json(filters["parent_filters"])["include_child_cost_centers"], 1)
