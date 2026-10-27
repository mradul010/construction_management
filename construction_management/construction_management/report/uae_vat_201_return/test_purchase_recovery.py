import unittest
from unittest.mock import Mock, patch

import frappe
from construction_management.construction_management.report.uae_vat_201_return import purchase_recovery as recovery


class TestPurchaseRecovery(unittest.TestCase):
	def test_default_zero_requires_a_current_documented_manager_decision(self):
		from frappe.utils import escape_html
		doc = frappe._dict(name="PI", modified="2026-07-16 12:00:00", reverse_charge="N",
			recoverable_standard_rated_expenses=0)
		decision = dict(vat201_purchase_recovery=1, invoice="PI", field=recovery.FIELD,
			amount=0, reason="Reviewed: ineligible expense", invoice_modified=doc.modified)
		def comment(data):
			return frappe._dict(name="DECISION", reference_name="PI", owner="MANAGER",
				content="<pre>" + escape_html(frappe.as_json(data)) + "</pre>")
		with patch.object(frappe, "get_all", return_value=[]) as read:
			self.assertEqual(recovery.confirmed_zero_recovery([doc]), {})
			self.assertEqual(read.call_args.kwargs["filters"]["reference_name"], ["in", ["PI"]])
		with patch.object(frappe, "get_all", return_value=[comment(decision)]):
			self.assertEqual(recovery.confirmed_zero_recovery([doc]), {"PI": "DECISION"})
			with patch.object(frappe, "get_roles", return_value=["Accounts User"]):
				self.assertEqual(recovery.confirmed_zero_recovery([doc]), {})
		for changes in (dict(invoice="OTHER"), dict(amount=20), dict(reason=""),
			dict(invoice_modified="2026-07-15 12:00:00"), dict(field="other")):
			with patch.object(frappe, "get_all", return_value=[comment(dict(decision, **changes))]):
				self.assertEqual(recovery.confirmed_zero_recovery([doc]), {})
		with patch.object(frappe, "get_all", side_effect=AssertionError("No history read for populated amounts")):
			self.assertEqual(recovery.confirmed_zero_recovery([frappe._dict(doc, recoverable_standard_rated_expenses=20)]), {})

	def doc(self, **values):
		doc = Mock()
		doc.docstatus = 1
		doc.company = "TEST"
		doc.flags = frappe._dict(vat201_recovery_reason="Reviewed tax invoice")
		doc.get.side_effect = lambda key: dict(dict(reverse_charge="N", recoverable_standard_rated_expenses=20), **values).get(key)
		doc.get_doc_before_save.return_value = frappe._dict(recoverable_standard_rated_expenses=0)
		doc.taxes = [frappe._dict(account_head="VAT", base_tax_amount_after_discount_amount=77.88, add_deduct_tax="Add")]
		return doc

	def setUp(self):
		from construction_management.construction_management.report.uae_vat_201_return import engine
		self.enterContext(patch.object(frappe, "get_roles", return_value=["Accounts Manager"]))
		self.enterContext(patch.object(frappe, "get_cached_value", return_value="AED"))
		self.enterContext(patch.object(engine, "settings_for", return_value={"uae_vat_accounts": [frappe._dict(account="VAT", custom_vat201_side="Both")]}))
		self.original_validate_copy = recovery.validate_accounting_copy
		self.validate_copy = self.enterContext(patch.object(recovery, "validate_accounting_copy"))

	def test_manager_update_runs_normal_controller_validation(self):
		doc = self.doc()
		recovery.validate_update(doc)
		doc.check_permission.assert_called_once_with("write")
		self.validate_copy.assert_called_once_with(doc)

	def test_non_manager_and_missing_document_write_permission_are_denied(self):
		with patch.object(frappe, "get_roles", return_value=["Accounts User"]):
			with self.assertRaises(frappe.PermissionError):
				recovery.validate_update(self.doc())
		doc = self.doc()
		doc.check_permission.side_effect = frappe.PermissionError
		with self.assertRaises(frappe.PermissionError):
			recovery.validate_update(doc)

	def test_reason_required_and_amount_cannot_exceed_recorded_vat(self):
		doc = self.doc()
		doc.flags = frappe._dict()
		with self.assertRaises(frappe.ValidationError):
			recovery.validate_update(doc)
		for amount in (-1, 78):
			doc = self.doc(recoverable_standard_rated_expenses=amount)
			with self.assertRaises(frappe.ValidationError):
				recovery.validate_update(doc)
			doc.run_method.assert_not_called()

	def test_zero_partial_full_and_return_amounts(self):
		for amount in (0, 20, 77.88):
			doc = self.doc(recoverable_standard_rated_expenses=amount)
			doc.get_doc_before_save.return_value = frappe._dict(recoverable_standard_rated_expenses=1)
			recovery.validate_update(doc)
			self.validate_copy.assert_called_with(doc)
		doc = self.doc(recoverable_standard_rated_expenses=-20)
		doc.taxes[0].base_tax_amount_after_discount_amount = -77.88
		recovery.validate_update(doc)

	def test_unchanged_recovery_does_not_interfere_with_other_updates(self):
		doc = self.doc(recoverable_standard_rated_expenses=0)
		recovery.validate_update(doc)
		doc.run_method.assert_not_called()
		doc.check_permission.assert_not_called()

	def test_endpoint_rejects_blank_reason_stale_timestamp_or_unsubmitted_document(self):
		doc = self.doc()
		doc.modified = "2026-07-16 12:00:00"
		with patch.object(frappe, "get_doc", return_value=doc):
			with self.assertRaises(frappe.ValidationError):
				recovery.update_recovery("PI", 20, " ", doc.modified)
			with self.assertRaises(frappe.TimestampMismatchError):
				recovery.update_recovery("PI", 20, "TEST", "2026-07-15 12:00:00")
			doc.docstatus = 0
			with self.assertRaises(frappe.ValidationError):
				recovery.update_recovery("PI", 20, "TEST", doc.modified)
		doc.save.assert_not_called()

	def test_nonfinite_or_invalid_amounts_rejected(self):
		for amount in (None, "", "NaN", "Infinity", "abc"):
			with self.assertRaises(frappe.ValidationError):
				recovery.checked_amount(amount)

	def test_detached_validation_does_not_change_posting_values(self):
		candidate = frappe._dict(items=[], taxes=[], grand_total=100)
		candidate.run_method = Mock()
		doc = Mock()
		with patch.object(frappe, "get_doc", return_value=candidate):
			self.original_validate_copy(doc)
		candidate.run_method.assert_called_once_with("validate")
		doc.save.assert_not_called()

	def test_detached_accounting_recalculation_or_validation_error_blocks_update(self):
		candidate = frappe._dict(items=[], taxes=[], grand_total=100)
		candidate.run_method = Mock(side_effect=lambda method: candidate.update(grand_total=101))
		with patch.object(frappe, "get_doc", return_value=candidate):
			with self.assertRaises(frappe.ValidationError):
				self.original_validate_copy(Mock())
		candidate.run_method.side_effect = frappe.ValidationError("Controller rejected invoice")
		with patch.object(frappe, "get_doc", return_value=candidate):
			with self.assertRaises(frappe.ValidationError):
				self.original_validate_copy(Mock())
