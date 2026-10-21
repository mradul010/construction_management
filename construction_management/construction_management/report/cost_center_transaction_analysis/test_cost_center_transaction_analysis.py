import unittest
from unittest.mock import patch

import frappe

from construction_management.construction_management.report.cost_center_transaction_analysis import (
	cost_center_transaction_analysis as report,
)


class TestLedgerDrilldown(unittest.TestCase):
	def setUp(self):
		self.filters = dict(company="QBC", from_date="2026-09-20", to_date="2026-10-20", project="PROJ-0016")
		self.center = frappe._dict(company="QBC", is_group=0)
		self.center.check_permission = lambda *args: None
		self.account_query = self.enterContext(patch.object(report.frappe, "get_list", return_value=["Expense - QBC"]))
		self.enterContext(patch.object(report.frappe, "has_permission"))
		self.enterContext(patch.object(report.frappe, "get_doc", return_value=self.center))
		self.enterContext(patch.object(report, "get_company_currency", return_value="AED"))
		self.enterContext(patch.object(report, "get_accounting_dimensions", return_value=[]))

	def test_no_generated_accounts_and_explicit_empty_route_token(self):
		result = report.get_general_ledger_filters(self.filters, "Concrete - QBC")
		filters = result["filters"]
		self.account_query.assert_not_called()
		self.assertEqual(filters["cost_center"], ["Concrete - QBC"])
		self.assertEqual(filters["project"], ["PROJ-0016"])
		self.assertEqual(filters["account"], "[]")
		self.assertEqual(frappe.parse_json(filters["account"]), [])
		for key in ("company", "from_date", "to_date"):
			self.assertEqual(filters[key], self.filters[key])
		self.assertEqual(filters["presentation_currency"], "AED")
		self.assertTrue(any("Account Type" in warning for warning in result["warnings"]))

	def test_finance_book_cancelled_entries_and_voucher(self):
		self.filters.update(finance_book="Local Book", include_default_book_entries=0, show_cancelled_entries=1, voucher_no="JV-1")
		filters = report.get_general_ledger_filters(self.filters, "Concrete - QBC")["filters"]
		for key in ("finance_book", "include_default_book_entries", "show_cancelled_entries", "voucher_no"):
			self.assertEqual(filters[key], self.filters[key])

	def test_group_and_unsupported_voucher_type_warn(self):
		self.center.is_group = 1
		self.filters["voucher_type"] = "Journal Entry"
		self.assertEqual(len(report.get_general_ledger_filters(self.filters, "Group - QBC")["warnings"]), 3)

	def test_only_explicit_account_is_passed_without_expanding_children(self):
		self.filters["account"] = "Expense - QBC"
		with patch.object(report.frappe.db, "get_value", return_value="QBC"), patch.object(report, "get_accounts_with_children") as expand:
			result = report.get_general_ledger_filters(self.filters, "Concrete - QBC")
			self.assertEqual(result["filters"]["account"], ["Expense - QBC"])
			expand.assert_not_called()
		self.account_query.assert_not_called()
