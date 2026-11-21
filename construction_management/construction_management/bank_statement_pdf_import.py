"""Private PDF bank-statement preview and Bank Transaction import.

The parser is deliberately format-specific and modular. It supports the Mashreq
statement layout supplied for QATRA and never creates accounting entries.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation

import frappe
from frappe import _
from frappe.utils import getdate

MAX_FILE_SIZE = 20 * 1024 * 1024
MAX_TRANSACTIONS = 2000
MONEY = re.compile(r"^-?\(?\d[\d,]*(?:\.\d+)?\)?$")
DATE = re.compile(r"^(?:\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})$")
NOISE = (
	"The items and balance shown", "verified. Report any discrepancies", "of the statement date",
	"All charges, terms and conditions", "Please note that for foreign currency", "indicative only",
	"Mashreqbank PSC is regulated", "page",
)


def amount(value, *, allow_blank=False):
	if value in (None, "") and allow_blank:
		return Decimal("0")
	try:
		text = str(value).strip().replace(",", "")
		negative = text.startswith("(") and text.endswith(")")
		value = Decimal(text.strip("()"))
		return -value if negative else value
	except (InvalidOperation, ValueError, TypeError):
		raise ValueError("Invalid monetary amount")


def money(value):
	return str(amount(value).quantize(Decimal("0.01")))


def normalized(value):
	return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", str(value or "").upper())).strip()


def digest(*values):
	return hashlib.sha256("\x1f".join(str(value or "") for value in values).encode()).hexdigest()


class PDFTextExtractor:
	"""PyMuPDF primary extractor with pdfplumber fallback."""

	def extract(self, content):
		primary_error = None
		try:
			return self._pymupdf(content)
		except Exception as error:
			primary_error = str(error)
		try:
			return self._pdfplumber(content)
		except Exception:
			if primary_error and "password" in primary_error.lower():
				frappe.throw(_("The PDF is password-protected. Upload an unlocked statement."))
			frappe.throw(_("The PDF is corrupted or its text could not be extracted."))

	def _pymupdf(self, content):
		import pymupdf

		document = pymupdf.open(stream=content, filetype="pdf")
		if document.needs_pass:
			raise ValueError("Password-protected PDF")
		pages, texts = [], []
		for index, page in enumerate(document):
			text = page.get_text("text") or ""
			texts.append(text)
			words = [dict(page=index, x0=float(row[0]), x1=float(row[2]), top=float(row[1]), text=str(row[4]),
				width=float(page.rect.width), height=float(page.rect.height)) for row in page.get_text("words")]
			pages.append(words)
		return dict(engine="PyMuPDF", pages=pages, text="\n".join(texts))

	def _pdfplumber(self, content):
		import io
		import pdfplumber

		pages, texts = [], []
		with pdfplumber.open(io.BytesIO(content)) as document:
			if getattr(document, "is_encrypted", False):
				raise ValueError("Password-protected PDF")
			for index, page in enumerate(document.pages):
				text = page.extract_text() or ""
				texts.append(text)
				pages.append([dict(page=index, x0=float(row["x0"]), x1=float(row["x1"]), top=float(row["top"]), text=row["text"],
					width=float(page.width), height=float(page.height)) for row in page.extract_words()])
		return dict(engine="pdfplumber", pages=pages, text="\n".join(texts))


class MashreqQatraParser:
	name = "Mashreq QATRA account statement"

	def accepts(self, extracted):
		text = extracted["text"]
		statement = "Account Statement" in text or "Current Account Statement" in text or "Statement for Period" in text
		reference = "Reference Number" in text or re.search(r"Reference\s+no\b", text, re.I)
		return bool(statement and "Mashreq" in text and reference)

	def parse(self, extracted):
		text = extracted["text"]
		if len(text.strip()) < 100:
			frappe.throw(_("No extractable text was found. This appears to be a scanned PDF; OCR is not enabled."))
		opening = self._statement_balance(extracted["pages"], "Opening balance")
		closing = self._statement_balance(extracted["pages"], "Closing balance")
		opening = self._label_amount(text, "Opening balance") if opening is None else opening
		closing = self._label_amount(text, "Closing balance") if closing is None else closing
		currency_match = (re.search(r"Account Currency\s+([A-Z]{3})", text)
			or re.search(r"Account No\s*\n\d{8,}\s*\n([A-Z]{3})", text, re.I)
			or re.search(r"\n\d{8,}\s*\n([A-Z]{3})\s*\n", text))
		account_match = (re.search(r"Account Number[^\n]*\n(\d{8,})", text)
			or re.search(r"(\d{8,})\s*\nAccount Number", text)
			or re.search(r"Account No\s*\n(\d{8,})", text, re.I))
		currency = currency_match.group(1) if currency_match else None
		account_number = account_match.group(1) if account_match else None
		columns = self._columns(extracted["pages"])
		words = self._body_words(extracted["pages"])
		starts = [word for word in words if DATE.match(word["text"]) and word["x0"] < columns["description"]]
		rows = []
		previous = opening
		for index, start in enumerate(starts):
			end = starts[index + 1]["global_top"] - 14 if index + 1 < len(starts) else float("inf")
			end = min(end, (start["page"] + 1) * 1000)
			block = [word for word in words if start["global_top"] - 14 <= word["global_top"] < end]
			row = self._transaction(start, block, columns, previous, index + 1)
			rows.append(row)
			if row.get("balance") is not None:
				previous = amount(row["balance"])
		if not rows:
			frappe.throw(_("No transaction rows were detected in this PDF. Scanned statements require OCR."))
		if len(rows) > MAX_TRANSACTIONS:
			frappe.throw(_("The statement contains too many transactions for one import."))
		warnings = []
		if closing is not None and rows[-1].get("balance") is not None and amount(rows[-1]["balance"]) != closing:
			warnings.append(_("The extracted final running balance does not match the printed closing balance."))
		return dict(parser=self.name, extraction_engine=extracted["engine"], currency=currency,
			account_number=account_number, opening_balance=money(opening) if opening is not None else None,
			closing_balance=money(closing) if closing is not None else None, rows=rows, warnings=warnings)

	def _label_amount(self, text, label):
		match = re.search(re.escape(label) + r"\s+([\d,]+(?:\.\d+)?)", text, re.I)
		return amount(match.group(1)) if match else None

	def _statement_balance(self, pages, label):
		first, second = label.lower().split()
		for page in pages:
			for word in page:
				if word["text"].lower() != first:
					continue
				line = [item for item in page if abs(item["top"] - word["top"]) <= 2]
				if second not in {item["text"].strip(":").lower() for item in line}:
					continue
				values = [item for item in line if MONEY.match(item["text"])]
				if values:
					return amount(max(values, key=lambda item: item["x0"])["text"])
		return None

	def _columns(self, pages):
		all_words = [word for page in pages for word in page]
		for page in pages:
			for date in (word for word in page if word["text"].lower() == "date"):
				line = [word for word in page if abs(word["top"] - date["top"]) <= 2]
				labels = {word["text"].lower(): word for word in line}
				if all(label in labels for label in ("transaction", "debit", "credit", "balance")):
					return dict(date=date["x0"], description=labels["transaction"]["x0"],
						reference=labels.get("reference", {"x0": 227})["x0"],
						debit=labels["debit"]["x0"], credit=labels["credit"]["x0"],
						balance=labels["balance"]["x0"], page_width=date["width"])
		def x(label, fallback):
			word = next((word for word in all_words if word["text"].lower() == label.lower()), None)
			return word["x0"] if word else fallback
		return dict(date=x("Date", 29), description=x("Transaction", 100), reference=x("Reference", 227),
			debit=x("Debit", 333), credit=x("Credit", 412), balance=x("Balance", 500), page_width=595)

	def _body_words(self, pages):
		out = []
		for page_index, page in enumerate(pages):
			for word in page:
				if word["top"] > word["height"] - 110 or any(word["text"].startswith(prefix) for prefix in NOISE):
					continue
				row = dict(word)
				row["global_top"] = page_index * 1000 + word["top"]
				out.append(row)
		return sorted(out, key=lambda row: (row["global_top"], row["x0"]))

	def _transaction(self, start, block, columns, previous, index):
		line = [word for word in block if abs(word["global_top"] - start["global_top"]) <= 3]
		debit = self._column_amount(line, columns, "debit")
		credit = self._column_amount(line, columns, "credit")
		# Mashreq prints reversals as a negative value in the original column.
		# Bank Transaction expects positive deposit/withdrawal values.
		if debit < 0:
			credit, debit = credit - debit, Decimal("0")
		if credit < 0:
			debit, credit = debit - credit, Decimal("0")
		balances = [word for word in block if self._in_column(word, columns, "balance") and MONEY.match(word["text"])]
		balance_word = min(balances, key=lambda word: abs(word["global_top"] - start["global_top"])) if balances else None
		balance = amount(balance_word["text"]) if balance_word else None
		debit_left = columns["debit"] - 30
		ref_words = [word["text"] for word in line if columns["reference"] - 15 <= word["x0"] and self._center(word) < debit_left]
		reference = " ".join(ref_words).strip(" -")
		financial = [word for word in block if MONEY.match(word["text"]) and
			any(self._in_column(word, columns, key) for key in ("debit", "credit", "balance"))]
		excluded = {id(start), *(id(word) for word in financial),
			*(id(word) for word in balances)}
		description_words = [word["text"] for word in block if id(word) not in excluded and word["x0"] >= columns["description"] - 15]
		description = re.sub(r"\s+", " ", " ".join(description_words)).strip()
		description = re.sub(r"\s*Closing balance\s*$", "", description, flags=re.I).strip()
		problems = []
		if bool(debit) == bool(credit):
			problems.append("Exactly one debit or credit amount is required")
		if not description:
			problems.append("Description is missing")
		balance_mismatch = False
		if previous is not None and balance is not None and bool(debit) != bool(credit):
			expected = previous + credit - debit
			balance_mismatch = expected.quantize(Decimal("0.01")) != balance.quantize(Decimal("0.01"))
		if balance_mismatch:
			problems.append("Running balance mismatch")
		date = datetime.strptime(start["text"], "%d/%m/%Y").strftime("%Y-%m-%d") if "/" in start["text"] else start["text"]
		return dict(row_id=str(index), selected=1, date=date, value_date=None,
			description=description, reference=reference, withdrawal=money(debit), deposit=money(credit),
			balance=money(balance) if balance is not None else None, balance_mismatch=int(balance_mismatch),
			balance_reviewed=0, duplicate_reviewed=0, validation_status="; ".join(problems) or "Valid")

	def _center(self, word):
		return (word["x0"] + word.get("x1", word["x0"])) / 2

	def _in_column(self, word, columns, key):
		bounds = {
			"debit": (columns["debit"] - 30, columns["credit"] - 30),
			"credit": (columns["credit"] - 30, columns["balance"] - 35),
			"balance": (columns["balance"] - 35, columns["page_width"]),
		}
		left, right = bounds[key]
		return left <= self._center(word) < right

	def _column_amount(self, words, columns, key):
		values = [amount(word["text"]) for word in words if self._in_column(word, columns, key) and MONEY.match(word["text"])]
		return values[0] if len(values) == 1 else Decimal("0")


PARSERS = (MashreqQatraParser(),)


def setup():
	"""Add a PDF-specific lane without changing ERPNext's spreadsheet importer."""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields({"Bank Statement Import": [
		dict(fieldname="custom_import_source", label="Statement Import Format", fieldtype="Select",
			options="Spreadsheet / MT940\nPDF (QATRA Mashreq)", default="Spreadsheet / MT940",
			insert_after="bank", module="Construction Management"),
		dict(fieldname="custom_pdf_statement", label="Private PDF Bank Statement", fieldtype="Attach",
			insert_after="custom_import_source", depends_on="eval:doc.custom_import_source == 'PDF (QATRA Mashreq)'",
			module="Construction Management"),
		dict(fieldname="custom_extract_pdf", label="Extract PDF and Preview", fieldtype="Button",
			insert_after="custom_pdf_statement", depends_on="eval:doc.custom_import_source == 'PDF (QATRA Mashreq)'",
			module="Construction Management"),
	]})


def import_document(name, company, bank_account):
	if not name:
		return None
	doc = frappe.get_doc("Bank Statement Import", name)
	doc.check_permission("write")
	if doc.company != company or doc.bank_account != bank_account:
		frappe.throw(_("The Bank Statement Import company or bank account does not match this PDF preview"))
	return doc


def permissions(company, bank_account, *, importing=False):
	frappe.has_permission("Bank Statement Import", "read", throw=True)
	for action in (("create", "submit") if importing else ("read",)):
		frappe.has_permission("Bank Transaction", action, throw=True)
	account = frappe.get_doc("Bank Account", bank_account)
	account.check_permission("read")
	if account.company != company:
		frappe.throw(_("The selected Bank Account does not belong to the selected Company"))
	ledger = frappe.get_cached_doc("Account", account.account)
	return account, ledger.account_currency


def private_pdf(file_url):
	name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not name:
		frappe.throw(_("Select an uploaded PDF statement"))
	file = frappe.get_doc("File", name)
	file.check_permission("read")
	if not file.is_private:
		frappe.throw(_("Bank statement PDFs must be uploaded as private files"))
	if not (file.file_name or "").lower().endswith(".pdf"):
		frappe.throw(_("Only PDF bank statements are supported"))
	content = file.get_content()
	if isinstance(content, str):
		content = content.encode()
	if len(content) > MAX_FILE_SIZE:
		frappe.throw(_("The PDF exceeds the 20 MB upload limit"))
	if not content.startswith(b"%PDF-"):
		frappe.throw(_("The uploaded file is not a valid PDF"))
	return file, content


def account_matches(statement_number, account):
	if not statement_number:
		return True
	candidates = {re.sub(r"\D", "", str(account.get(field) or "")) for field in ("bank_account_no", "iban")}
	return statement_number in candidates or any(value.endswith(statement_number) for value in candidates if value)


def duplicate_checks(rows, bank_account):
	dates = [row["date"] for row in rows if row.get("date")]
	existing = frappe.get_all("Bank Transaction", filters={"bank_account": bank_account,
		"date": ["between", [min(dates), max(dates)]] if dates else ["is", "set"], "docstatus": ["<", 2]},
		fields=["name", "date", "deposit", "withdrawal", "description", "reference_number", "transaction_id"])
	by_id = {row.transaction_id: row for row in existing if row.transaction_id}
	fallback_counts = Counter()
	for row in rows:
		base = (row["date"], row["reference"], row["deposit"], row["withdrawal"], normalized(row["description"]))
		fallback_counts[base] += 1
		row["transaction_id"] = "PDF-" + digest(bank_account, *base, fallback_counts[base])[:32]
		row["duplicate_status"] = ""
		row["existing_transaction"] = None
		if row["transaction_id"] in by_id:
			row["duplicate_status"], row["existing_transaction"] = "Duplicate", by_id[row["transaction_id"]].name
			row["selected"] = 0
			continue
		for prior in existing:
			same_amount = money(prior.deposit) == row["deposit"] and money(prior.withdrawal) == row["withdrawal"]
			if str(prior.date) == row["date"] and same_amount and row["reference"] and str(prior.reference_number or "").strip() == row["reference"]:
				row["duplicate_status"], row["existing_transaction"] = "Duplicate", prior.name
				row["selected"] = 0
				break
			if str(prior.date) == row["date"] and same_amount and normalized(prior.description) == normalized(row["description"]):
				row["duplicate_status"], row["existing_transaction"] = "Possible duplicate", prior.name
				break
		if row["duplicate_status"]:
			row["validation_status"] += ("; " if row["validation_status"] != "Valid" else "") + row["duplicate_status"]


def summary(result):
	rows = result["rows"]
	return dict(total_transactions=len(rows), valid_transactions=sum(row["validation_status"] == "Valid" for row in rows),
		possible_duplicates=sum(row.get("duplicate_status") == "Possible duplicate" for row in rows),
		duplicates=sum(row.get("duplicate_status") == "Duplicate" for row in rows),
		invalid_transactions=sum(row["validation_status"] != "Valid" and not row.get("duplicate_status") for row in rows),
		total_deposits=money(sum((amount(row["deposit"]) for row in rows), Decimal("0"))),
		total_withdrawals=money(sum((amount(row["withdrawal"]) for row in rows), Decimal("0"))))


@frappe.whitelist()
def extract_preview(company, bank_account, file_url, data_import=None):
	account, account_currency = permissions(company, bank_account)
	import_document(data_import, company, bank_account)
	file, content = private_pdf(file_url)
	extracted = PDFTextExtractor().extract(content)
	if len(extracted["text"].strip()) < 100:
		frappe.throw(_("No extractable text was found. This appears to be a scanned PDF; OCR is not enabled."))
	parser = next((parser for parser in PARSERS if parser.accepts(extracted)), None)
	if not parser:
		frappe.throw(_("This text-based PDF layout is not yet supported. No transactions were imported."))
	result = parser.parse(extracted)
	if result["currency"] and result["currency"] != account_currency:
		frappe.throw(_("Statement currency {0} does not match Bank Account currency {1}").format(result["currency"], account_currency))
	if not account_matches(result["account_number"], account):
		frappe.throw(_("The statement account number does not match the selected Bank Account"))
	duplicate_checks(result["rows"], bank_account)
	result.update(company=company, bank_account=bank_account, currency=result["currency"] or account_currency,
		file_name=file.file_name, file_digest=digest(content), summary=summary(result), data_import=data_import)
	token = uuid.uuid4().hex
	frappe.cache.set_value("bank_pdf_preview:" + token, dict(company=company, bank_account=bank_account,
		currency=result["currency"], file_digest=result["file_digest"], opening_balance=result["opening_balance"],
		row_ids=[row["row_id"] for row in result["rows"]], data_import=data_import), expires_in_sec=3600)
	result["preview_token"] = token
	return result


def validate_import_row(row, previous):
	problems = []
	try:
		date = str(getdate(row.get("date")))
	except Exception:
		date = None
		problems.append("Invalid transaction date")
	try:
		deposit, withdrawal = amount(row.get("deposit"), allow_blank=True), amount(row.get("withdrawal"), allow_blank=True)
		if deposit < 0 or withdrawal < 0 or bool(deposit) == bool(withdrawal):
			problems.append("Exactly one positive deposit or withdrawal is required")
	except ValueError:
		deposit = withdrawal = Decimal("0")
		problems.append("Invalid transaction amount")
	description = re.sub(r"\s+", " ", str(row.get("description") or "")).strip()
	if not description:
		problems.append("Description is required")
	try:
		balance = amount(row.get("balance")) if row.get("balance") not in (None, "") else None
	except ValueError:
		balance = None
		problems.append("Invalid running balance")
	mismatch = previous is not None and balance is not None and (previous + deposit - withdrawal).quantize(Decimal("0.01")) != balance.quantize(Decimal("0.01"))
	if mismatch and not int(row.get("balance_reviewed") or 0):
		problems.append("Running balance mismatch requires explicit review")
	return dict(row, date=date, deposit=money(deposit), withdrawal=money(withdrawal), description=description,
		balance=money(balance) if balance is not None else None, problems=problems), balance if balance is not None else previous


@frappe.whitelist()
def import_transactions(preview_token, rows):
	preview = frappe.cache.get_value("bank_pdf_preview:" + preview_token)
	if not preview:
		frappe.throw(_("The PDF preview has expired. Extract the statement again before importing."))
	permissions(preview["company"], preview["bank_account"], importing=True)
	import_document(preview.get("data_import"), preview["company"], preview["bank_account"])
	rows = frappe.parse_json(rows)
	if not isinstance(rows, list) or len(rows) > MAX_TRANSACTIONS:
		frappe.throw(_("Invalid PDF transaction selection"))
	row_ids = [str(row.get("row_id")) for row in rows]
	if len(row_ids) != len(set(row_ids)) or set(row_ids) != set(preview["row_ids"]):
		frappe.throw(_("The preview rows do not match the extracted statement"))
	validated, previous = [], amount(preview["opening_balance"]) if preview.get("opening_balance") else None
	for row in rows:
		clean, previous = validate_import_row(row, previous)
		validated.append(clean)
	# Serialize imports for this account. A repeated or concurrent confirmation
	# must see transactions committed by the first request before inserting.
	frappe.db.sql("select name from `tabBank Account` where name=%s for update", preview["bank_account"])
	duplicate_checks(validated, preview["bank_account"])
	result = dict(imported=[], skipped=[], failed=[])
	for row in validated:
		if not int(row.get("selected") or 0):
			result["skipped"].append(dict(row_id=row["row_id"], reason="Not selected"))
			continue
		if row["problems"]:
			result["failed"].append(dict(row_id=row["row_id"], reason="; ".join(row["problems"])))
			continue
		if row.get("duplicate_status") == "Duplicate":
			result["skipped"].append(dict(row_id=row["row_id"], reason="Duplicate", existing=row.get("existing_transaction")))
			continue
		if row.get("duplicate_status") == "Possible duplicate" and not int(row.get("duplicate_reviewed") or 0):
			result["failed"].append(dict(row_id=row["row_id"], reason="Possible duplicate requires explicit review"))
			continue
		savepoint = "bank_pdf_" + re.sub(r"\W", "", str(row["row_id"]))
		frappe.db.savepoint(savepoint)
		try:
			existing = frappe.db.get_value("Bank Transaction", {"bank_account": preview["bank_account"],
				"transaction_id": row["transaction_id"], "docstatus": ["<", 2]}, "name")
			if existing:
				result["skipped"].append(dict(row_id=row["row_id"], reason="Duplicate", existing=existing))
				continue
			doc = frappe.get_doc(dict(doctype="Bank Transaction", date=row["date"], bank_account=preview["bank_account"],
				currency=preview["currency"], description=row["description"], reference_number=row.get("reference"),
				transaction_id=row["transaction_id"], deposit=row["deposit"], withdrawal=row["withdrawal"]))
			doc.insert()
			doc.submit()
			result["imported"].append(doc.name)
		except Exception as error:
			frappe.db.rollback(save_point=savepoint)
			result["failed"].append(dict(row_id=row["row_id"], reason=str(error)))
	frappe.cache.delete_value("bank_pdf_preview:" + preview_token)
	result["counts"] = {key: len(result[key]) for key in ("imported", "skipped", "failed")}
	if preview.get("data_import"):
		status = "Partial Success" if result["failed"] and result["imported"] else "Error" if result["failed"] else "Success"
		frappe.db.set_value("Bank Statement Import", preview["data_import"], "status", status, update_modified=True)
		result["data_import_status"] = status
	return result
