import unittest
from unittest.mock import Mock, patch

import frappe

from construction_management.construction_management import bank_statement_pdf_import as pdf_import


def word(page, x, top, text, width=595, height=842):
	return dict(page=page, x0=x, top=top, text=text, width=width, height=height)


class TestMashreqPDFParser(unittest.TestCase):
	def extracted(self):
		text = """Account Statement
Mashreq
Reference Number Debit Credit Balance
019102096113
Account Number
Account Currency AED
Opening balance 1,000.00
Closing balance 950.00
"""
		page1 = [
			word(0, 29, 80, "Date"), word(0, 100, 80, "Transaction"), word(0, 227, 80, "Reference"),
			word(0, 333, 80, "Debit"), word(0, 412, 80, "Credit"), word(0, 500, 80, "Balance"),
			word(0, 100, 100, "Supplier"), word(0, 145, 100, "Payment"),
			word(0, 29, 110, "2026-06-01"), word(0, 100, 110, "Invoice"), word(0, 227, 110, "REF-1"),
			word(0, 333, 110, "100.00"), word(0, 100, 123, "continued"), word(0, 500, 130, "900.00"),
			word(0, 25, 740, "The"), word(0, 40, 740, "items"),
		]
		page2 = [
			word(1, 29, 70, "Date"), word(1, 333, 70, "Debit"), word(1, 412, 70, "Credit"), word(1, 500, 70, "Balance"),
			word(1, 100, 100, "Customer"), word(1, 145, 100, "Receipt"),
			word(1, 29, 110, "2026-06-02"), word(1, 100, 110, "Project"), word(1, 227, 110, "REF-2"),
			word(1, 412, 110, "50.00"), word(1, 100, 123, "retention"), word(1, 500, 130, "950.00"),
		]
		return dict(engine="PyMuPDF", text=text, pages=[page1, page2])

	def test_multi_page_repeated_headers_and_multiline_descriptions(self):
		result = pdf_import.MashreqQatraParser().parse(self.extracted())
		self.assertEqual((result["opening_balance"], result["closing_balance"], result["currency"]), ("1000.00", "950.00", "AED"))
		self.assertEqual(len(result["rows"]), 2)
		self.assertEqual((result["rows"][0]["withdrawal"], result["rows"][1]["deposit"]), ("100.00", "50.00"))
		self.assertIn("continued", result["rows"][0]["description"])
		self.assertIn("retention", result["rows"][1]["description"])
		self.assertTrue(all(row["validation_status"] == "Valid" for row in result["rows"]))

	def test_single_page_and_missing_reference_are_supported(self):
		extracted = self.extracted()
		extracted["pages"] = [extracted["pages"][0]]
		extracted["text"] = extracted["text"].replace("Closing balance 950.00", "Closing balance 900.00")
		extracted["pages"][0] = [word for word in extracted["pages"][0] if word["text"] != "REF-1"]
		result = pdf_import.MashreqQatraParser().parse(extracted)
		self.assertEqual(len(result["rows"]), 1)
		self.assertEqual(result["rows"][0]["reference"], "")
		self.assertEqual(result["rows"][0]["validation_status"], "Valid")

	def test_balance_mismatch_is_never_silently_skipped(self):
		extracted = self.extracted()
		next(word for word in extracted["pages"][1] if word["text"] == "950.00")["text"] = "951.00"
		result = pdf_import.MashreqQatraParser().parse(extracted)
		self.assertEqual(len(result["rows"]), 2)
		self.assertIn("Running balance mismatch", result["rows"][1]["validation_status"])

	def test_scanned_or_unsupported_pdf_fails_clearly(self):
		with self.assertRaises(frappe.ValidationError):
			pdf_import.MashreqQatraParser().parse(dict(engine="PyMuPDF", text="", pages=[]))

	def test_amount_parsing_uses_decimal(self):
		self.assertEqual(pdf_import.amount("1,234.56"), pdf_import.Decimal("1234.56"))
		self.assertEqual(pdf_import.amount("(12.50)"), pdf_import.Decimal("-12.50"))

	def test_invalid_rows_require_review_but_valid_review_can_proceed(self):
		row = dict(row_id="1", date="2026-06-01", description="Payment", deposit="0", withdrawal="100", balance="899")
		clean, balance = pdf_import.validate_import_row(row, pdf_import.Decimal("1000"))
		self.assertIn("Running balance mismatch requires explicit review", clean["problems"])
		row["balance_reviewed"] = 1
		clean, balance = pdf_import.validate_import_row(row, pdf_import.Decimal("1000"))
		self.assertFalse(clean["problems"])

	def test_duplicate_ids_are_stable_and_identical_looking_rows_remain_separate(self):
		rows = [dict(row_id=str(index), date="2026-06-01", reference="", deposit="0.00", withdrawal="100.00",
			description="Same cash withdrawal", selected=1, validation_status="Valid") for index in (1, 2)]
		with patch.object(frappe, "get_all", return_value=[]):
			pdf_import.duplicate_checks(rows, "BANK")
		self.assertNotEqual(rows[0]["transaction_id"], rows[1]["transaction_id"])
		self.assertTrue(all(not row["duplicate_status"] for row in rows))

	def test_existing_reference_duplicate_is_blocked_and_fallback_is_warning(self):
		prior = frappe._dict(name="BT-1", date="2026-06-01", deposit=0, withdrawal=100,
			description="Same cash withdrawal", reference_number="REF-1", transaction_id=None)
		row = dict(row_id="1", date="2026-06-01", reference="REF-1", deposit="0.00", withdrawal="100.00",
			description="Same cash withdrawal", selected=1, validation_status="Valid")
		with patch.object(frappe, "get_all", return_value=[prior]):
			pdf_import.duplicate_checks([row], "BANK")
		self.assertEqual((row["duplicate_status"], row["selected"]), ("Duplicate", 0))
		row.update(reference="", selected=1, validation_status="Valid")
		with patch.object(frappe, "get_all", return_value=[prior]):
			pdf_import.duplicate_checks([row], "BANK")
		self.assertEqual((row["duplicate_status"], row["selected"]), ("Possible duplicate", 1))

	def test_statement_account_matching_accepts_account_number_or_iban(self):
		account = frappe._dict(bank_account_no="019102096113", iban="AE630330000019102096113")
		self.assertTrue(pdf_import.account_matches("019102096113", account))
		self.assertFalse(pdf_import.account_matches("999999999", account))

	def test_confirmed_import_uses_standard_bank_transaction_lifecycle(self):
		preview = dict(company="SYNTHETIC", bank_account="BANK", currency="AED", opening_balance="1000.00", row_ids=["1"], data_import="IMPORT-1")
		rows = [dict(row_id="1", selected=1, date="2026-06-01", description="Supplier payment", reference="REF-1",
			deposit="0", withdrawal="100", balance="900", balance_reviewed=0, duplicate_reviewed=0,
			transaction_id="PDF-TEST", duplicate_status="")]
		doc = frappe._dict(name="BT-1", insert=Mock(), submit=Mock())
		with patch.object(frappe.cache, "get_value", return_value=preview), patch.object(frappe.cache, "delete_value"), \
			patch.object(pdf_import, "permissions"), patch.object(pdf_import, "import_document"), patch.object(pdf_import, "duplicate_checks"), \
			patch.object(frappe.db, "sql"), patch.object(frappe.db, "get_value", return_value=None), \
			patch.object(frappe.db, "savepoint"), patch.object(frappe.db, "set_value") as status, patch.object(frappe, "get_doc", return_value=doc):
			result = pdf_import.import_transactions("TOKEN", frappe.as_json(rows))
		self.assertEqual(result["counts"], {"imported": 1, "skipped": 0, "failed": 0})
		self.assertEqual(result["data_import_status"], "Success")
		self.assertEqual(status.call_args.args[3], "Success")
		doc.insert.assert_called_once()
		doc.submit.assert_called_once()

	def test_duplicate_is_rechecked_under_lock_before_insert(self):
		preview = dict(company="SYNTHETIC", bank_account="BANK", currency="AED", opening_balance="1000.00", row_ids=["1"], data_import=None)
		rows = [dict(row_id="1", selected=1, date="2026-06-01", description="Supplier payment", reference="REF-1",
			deposit="0", withdrawal="100", balance="900", balance_reviewed=0, duplicate_reviewed=0,
			transaction_id="PDF-TEST", duplicate_status="")]
		def preserve_id(items, bank):
			items[0]["transaction_id"] = "PDF-TEST"
		with patch.object(frappe.cache, "get_value", return_value=preview), patch.object(frappe.cache, "delete_value"), \
			patch.object(pdf_import, "permissions"), patch.object(pdf_import, "import_document"), \
			patch.object(pdf_import, "duplicate_checks", side_effect=preserve_id), patch.object(frappe.db, "sql"), \
			patch.object(frappe.db, "get_value", return_value="BT-EXISTING"), patch.object(frappe.db, "savepoint"), \
			patch.object(frappe, "get_doc") as get_doc:
			result = pdf_import.import_transactions("TOKEN", frappe.as_json(rows))
		self.assertEqual(result["counts"], {"imported": 0, "skipped": 1, "failed": 0})
		get_doc.assert_not_called()
