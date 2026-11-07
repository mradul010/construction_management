"""Run VAT unittest fixtures with site metadata; never creates accounting fixtures.

Usage: bench --site <site> execute
construction_management.construction_management.report.uae_vat_201_return.test_runner.run
Use an isolated test site for broader Frappe integration and accounting tests.
"""
import unittest
from pathlib import Path

import frappe


def run():
	from construction_management.construction_management.report.uae_vat_201_return import automatic
	package = "construction_management.construction_management.report.uae_vat_201_return"
	suite = unittest.TestSuite()
	for path in sorted(Path(automatic.__file__).parent.glob("test_*.py")):
		if path.stem != "test_runner":
			suite.addTests(unittest.defaultTestLoader.loadTestsFromName(package + "." + path.stem))
	try:
		result = unittest.TextTestRunner(verbosity=1).run(suite)
		if not result.wasSuccessful():
			raise AssertionError(f"VAT tests failed: {len(result.failures)} failures, {len(result.errors)} errors")
		return dict(tests=result.testsRun, failures=0, errors=0, skipped=len(result.skipped))
	finally:
		frappe.db.rollback()
