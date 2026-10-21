import unittest
from datetime import date
from unittest.mock import patch

import frappe
from construction_management.construction_management.report.project_profitability import project_profitability as report


class TestProjectProfitability(unittest.TestCase):
	def test_expense_classification_inherits_without_guessing(self):
		accounts = [
			frappe._dict(name="COGS", root_type="Expense", account_type="Cost of Goods Sold"),
			frappe._dict(name="Materials", root_type="Expense", parent_account="COGS"),
			frappe._dict(name="Admin", root_type="Expense", custom_profitability_classification="Indirect"),
			frappe._dict(name="Fees", root_type="Expense", parent_account="Admin"),
			frappe._dict(name="Unknown", root_type="Expense"),
			frappe._dict(name="Income", root_type="Income"),
		]
		classes = report.account_classes(accounts)
		self.assertEqual(classes["Materials"], "direct_expenses")
		self.assertEqual(classes["Fees"], "indirect_expenses")
		self.assertEqual(classes["Unknown"], "unclassified_expenses")
		self.assertEqual(classes["Income"], "income")
		accounts[1].custom_profitability_classification = "Indirect"
		self.assertEqual(report.account_classes(accounts)["Materials"], "indirect_expenses")

	def test_april_fiscal_periods_are_contiguous_and_clipped(self):
		def fiscal(day, **kwargs):
			year = day.year if day.month >= 4 else day.year - 1
			return str(year), date(year, 4, 1), date(year + 1, 3, 31)
		with patch.object(report, "get_fiscal_year", side_effect=fiscal):
			for kind, count in (("Monthly", 24), ("Quarterly", 8), ("Yearly", 2)):
				filters = frappe._dict(company="Example", from_date=date(2025, 4, 1), to_date=date(2027, 3, 31), period_type=kind)
				periods = report.get_periods(filters)
				self.assertEqual(len(periods), count)
				self.assertEqual(periods[0].from_date, filters.from_date)
				self.assertEqual(periods[-1].to_date, filters.to_date)
				for previous, current in zip(periods, periods[1:]):
					self.assertEqual((current.from_date - previous.to_date).days, 1)
				if kind == "Quarterly":
					self.assertEqual(periods[0].to_date, date(2025, 6, 30))
				filters.from_date, filters.to_date = date(2025, 5, 10), date(2025, 8, 16)
				clipped = report.get_periods(filters)
				self.assertEqual(clipped[0].from_date, filters.from_date)
				self.assertEqual(clipped[-1].to_date, filters.to_date)

	def test_signs_profits_zero_income_and_currency_precision(self):
		classes = {"I": "income", "D": "direct_expenses", "N": "indirect_expenses", "U": "unclassified_expenses"}
		entries = [frappe._dict(account="I", balance=-100), frappe._dict(account="D", balance=40), frappe._dict(account="N", balance=10)]
		with patch.object(report.frappe, "get_precision", return_value=3):
			values = report.totals(entries, classes, "TEST")
			self.assertEqual((values["income"], values["gross_profit"], values["net_profit"], values["margin"]), (100, 60, 50, 50))
			self.assertEqual(report.totals([frappe._dict(account="D", balance="1.2344")], classes, "TEST")["expenses"], 1.234)
			self.assertEqual(report.totals(entries[1:], classes, "TEST")["margin"], 0)
			entries.append(frappe._dict(account="U", balance=5))
			values = report.totals(entries, classes, "TEST")
			self.assertIsNone(values["gross_profit"])
			self.assertEqual(values["net_profit"], 45)

	def test_empty_scope_never_reads_unrestricted_gl(self):
		with patch.object(report.frappe.db, "sql") as sql:
			self.assertEqual(report.read_entries(frappe._dict(project="Hidden"), [], ["Account"]), [])
			self.assertEqual(report.read_entries(frappe._dict(), [], []), [])
			sql.assert_not_called()

	def test_drilldown_checks_existing_report_access(self):
		with patch.object(report.frappe, "has_permission"), patch.object(report, "get_report_doc", side_effect=frappe.PermissionError):
			with self.assertRaises(frappe.PermissionError):
				report.drilldown({"company": "Example"}, {"project": "Hidden"})
