"""Independent documentary filings, payments and explanations; never posts GL."""
from decimal import InvalidOperation

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime

from construction_management.construction_management.report.uae_vat_201_return import engine

DOCTYPES = ("vat_201_filed_value", "vat_201_filing", "vat_201_payment", "vat_201_filed_difference", "vat_201_tax_evidence")


def setup():
	for name in DOCTYPES:
		frappe.reload_doc("construction_management", "doctype", name)


def decimal_value(value):
	try:
		value = engine.number(value)
		if not value.is_finite():
			raise ValueError
		return value
	except (ValueError, TypeError, InvalidOperation):
		frappe.throw(_("A finite monetary amount is required"))


def manager(company):
	engine.access(company)
	if not set(frappe.get_roles()) & {"Accounts Manager", "System Manager"}:
		frappe.throw(_("Only Accounts Managers may approve filing evidence and payments"), frappe.PermissionError)


class EvidenceRecord(Document):
	def validate(self):
		manager(self.company)
		previous = self.get_doc_before_save()
		if previous and previous.docstatus == 1:
			frappe.throw(_("Submitted evidence is immutable; record a documented correction separately"))
		requires_evidence = self.doctype != "VAT 201 Filing" or self.docstatus == 1
		if requires_evidence and (not self.reason or not self.supporting_evidence):
			frappe.throw(_("Reason and supporting documentary evidence are required"))
		if requires_evidence:
			files = frappe.get_list("File", filters={"file_url": self.supporting_evidence}, fields=["name"], limit_page_length=1)
			if not files:
				frappe.throw(_("Attach accessible documentary evidence before submitting"))
		self.approved_by = self.approved_on = None

	def before_submit(self):
		manager(self.company)
		self.approved_by, self.approved_on = frappe.session.user, now_datetime()

	def before_cancel(self):
		frappe.throw(_("Submitted documentary records cannot be cancelled; record a correction separately"))

	def on_trash(self):
		if self.docstatus:
			frappe.throw(_("Submitted documentary history cannot be deleted"))


class FilingRecord(EvidenceRecord):
	def validate(self):
		super().validate()
		if self.docstatus == 0:
			self.filing_status = "Draft"
		if not self.from_date or not self.to_date or getdate(self.from_date) > getdate(self.to_date):
			frappe.throw(_("A valid filing period is required"))
		if self.docstatus == 1 and (not self.fta_reference or not self.submission_date):
			frappe.throw(_("FTA reference and submission date are required before submitting"))
		if self.submission_date and getdate(self.submission_date) < getdate(self.to_date):
			frappe.throw(_("Submission date cannot precede the period end"))
		if self.docstatus == 1 and not self.filed_liability_known:
			frappe.throw(_("The filed Box 14 must be explicitly known; zero is a valid known value"))
		if self.filed_liability_known:
			decimal_value(self.filed_liability)
		if self.amount_due_known and decimal_value(self.amount_due) < 0:
			frappe.throw(_("Amount due cannot be negative"))
		known = {}
		for row in self.get("filed_values", []):
			key = (row.box, row.component)
			allowed = {"amount"} if row.box in ("4", "5", "12", "13", "14") else {"amount", "vat_amount"}
			if row.box in engine.OUTPUT[:7] + ["8", "9", "11"]:
				allowed.add("adjustment")
			if row.box not in engine.LABELS or row.component not in allowed or key in known:
				frappe.throw(_("Filed box components must be valid and unique"))
			known[key] = decimal_value(row.value)
			if not row.evidence_reference:
				frappe.throw(_("Each known filed value requires an evidence reference"))
		if ("14", "amount") in known and engine.money(known[("14", "amount")]) != engine.money(self.filed_liability):
			frappe.throw(_("Filed Box 14 values conflict"))
		if all((key, "amount") in known for key in ("12", "13")) and engine.money(known[("12", "amount")] - known[("13", "amount")]) != engine.money(self.filed_liability):
			frappe.throw(_("Known filed Boxes 12 and 13 do not reconcile to Box 14"))
		if self.correction_of:
			prior = linked_filing(self)
			if (str(prior.from_date), str(prior.to_date)) != (str(self.from_date), str(self.to_date)):
				frappe.throw(_("A correction must retain the original filing period"))
		self.calculation_snapshot = None

	def before_submit(self):
		super().before_submit()
		# Serialize same-company submissions to prevent parallel duplicate originals/corrections.
		frappe.db.sql("select name from `tabCompany` where name=%s for update", self.company)
		prior = frappe.get_all("VAT 201 Filing", filters={"company": self.company, "from_date": self.from_date,
			"to_date": self.to_date, "docstatus": 1}, fields=["name", "correction_of"])
		leaves = {row.name for row in prior} - {row.correction_of for row in prior if row.correction_of}
		if (leaves and leaves != {self.correction_of}) or (not leaves and self.correction_of):
			frappe.throw(_("Link the current submitted filing as Correction Of; existing filings are preserved"))
		period = filing_period(self.company, self.from_date, self.to_date, lock=True)
		liability = decimal_value(self.filed_liability)
		self.amount_due_known = 1
		self.amount_due = engine.money(max(liability, engine.number(0)))
		self.outstanding_amount = self.amount_due
		self.filing_status = "Recoverable" if liability < 0 else "Paid" if not liability else "Filed / Payment Pending"
		from construction_management.construction_management.report.uae_vat_201_return.automatic import build
		result = build(dict(company=self.company, from_date=self.from_date, to_date=self.to_date))
		self.calculation_snapshot = frappe.as_json({key: result.get(key) for key in
			("boxes", "ledger_summary", "tax_measures", "status", "calculated_at")})

	def on_submit(self):
		period = filing_period(self.company, self.from_date, self.to_date, lock=True)
		frappe.db.set_value("VAT 201 Filing Period", period.name, {
			"status": "Filed", "submission_date": self.submission_date,
			"filing_reference": self.fta_reference, "return_approved_by": self.approved_by,
			"return_approved_on": self.approved_on,
		}, update_modified=False)


def calculated_filing_values(result):
	"""Project the existing report boxes into the Filing child table without recalculation."""
	values = []
	for box in result.get("boxes", []):
		components = {"amount"} if box["box"] in ("4", "5", "12", "13", "14") else {"amount", "vat_amount"}
		if box["box"] in engine.OUTPUT[:7] + ["8", "9", "11"]:
			components.add("adjustment")
		for component in ("amount", "vat_amount", "adjustment"):
			if component in components:
				values.append(dict(box=box["box"], component=component, value=box[component],
					evidence_reference="Generated from UAE VAT 201 Return"))
	return values


def draft_result(doc, header):
	"""Build the statutory-form projection from the Filing's saved rows, not live recalculation."""
	boxes = engine.aggregate([])
	for row in doc.get("filed_values", []):
		if row.box in boxes and row.component in ("amount", "vat_amount", "adjustment"):
			boxes[row.box][row.component] = engine.money(row.value)
	header = dict(header, fta_reference=doc.get("fta_reference"),
		submission_date=str(doc.submission_date) if doc.get("submission_date") else None)
	return dict(header=header, boxes=list(boxes.values()), status=_("Draft VAT 201 Filing"),
		filed_comparison={}, report_view="Internal VAT Review")


@frappe.whitelist()
def preview(name):
	doc = frappe.get_doc("VAT 201 Filing", name)
	doc.check_permission("read")
	manager(doc.company)
	settings = engine.settings_for(doc.company)
	f = engine.normalize(dict(company=doc.company, from_date=doc.from_date, to_date=doc.to_date), settings)
	header = engine.taxpayer(doc.company, settings, f)
	from construction_management.construction_management.report.uae_vat_201_return.form_layout import form_html
	return form_html(draft_result(doc, header))


@frappe.whitelist()
def create_draft(filters):
	"""Create one reviewable filing draft per company/period, or return the existing record."""
	from construction_management.construction_management.report.uae_vat_201_return.automatic import build

	result = build(filters)
	header = result["header"]
	manager(header["company"])
	frappe.has_permission("VAT 201 Filing", "create", throw=True)
	# Serialize create-or-open requests for the same company.
	frappe.db.sql("select name from `tabCompany` where name=%s for update", header["company"])
	existing = frappe.get_list("VAT 201 Filing", filters={"company": header["company"],
		"from_date": header["from_date"], "to_date": header["to_date"], "docstatus": ["!=", 2]},
		fields=["name", "docstatus"], order_by="creation asc", limit_page_length=1)
	if existing:
		doc = frappe.get_doc("VAT 201 Filing", existing[0].name)
		doc.check_permission("read")
		return dict(name=doc.name, created=False, docstatus=doc.docstatus)
	box14 = next(box for box in result["boxes"] if box["box"] == "14")["amount"]
	doc = frappe.get_doc(dict(doctype="VAT 201 Filing", company=header["company"],
		from_date=header["from_date"], to_date=header["to_date"],
		filed_liability_known=1, filed_liability=box14,
		amount_due_known=1, amount_due=max(0, box14),
		filed_values=calculated_filing_values(result),
		notes=_("Draft generated from UAE VAT 201 Return for review. Add the FTA reference, submission date and supporting evidence before submitting.")))
	doc.insert()
	return dict(name=doc.name, created=True, docstatus=doc.docstatus)


def linked_filing(doc):
	filing = frappe.get_doc("VAT 201 Filing", doc.get("filing") or doc.get("correction_of"))
	filing.check_permission("read")
	if filing.company != doc.company or filing.docstatus != 1:
		frappe.throw(_("Select a submitted filing in this Company"))
	return filing


def filing_period(company, from_date, to_date, lock=False):
	settings = engine.settings_for(company)
	matches = [row for row in settings.get("custom_vat201_periods", [])
		if getdate(row.from_date) == getdate(from_date) and getdate(row.to_date) == getdate(to_date)]
	if len(matches) != 1:
		frappe.throw(_("The filing must match one configured VAT reporting period for this Company"))
	if lock:
		frappe.db.sql("select name from `tabVAT 201 Filing Period` where name=%s for update", matches[0].name)
	return matches[0]


def submitted_payment_total(filing_name, exclude=None):
	filters = {"filing": filing_name, "docstatus": 1}
	if exclude:
		filters["name"] = ["!=", exclude]
	rows = frappe.get_all("VAT 201 Payment", filters=filters, pluck="payment_amount")
	return sum((decimal_value(value) for value in rows), engine.number(0))


def payment_state(filing, paid=None):
	paid = submitted_payment_total(filing.name) if paid is None else engine.number(paid)
	due = decimal_value(filing.amount_due) if filing.amount_due_known else engine.number(0)
	outstanding = max(due - paid, engine.number(0))
	liability = decimal_value(filing.filed_liability) if filing.filed_liability_known else engine.number(0)
	status = "Recoverable" if liability < 0 else "Paid" if not outstanding else "Partially Paid" if paid else "Filed / Payment Pending"
	return engine.money(outstanding), status


def sync_filing_payment_status(filing_name):
	filing = frappe.get_doc("VAT 201 Filing", filing_name)
	outstanding, status = payment_state(filing)
	frappe.db.set_value("VAT 201 Filing", filing.name,
		{"outstanding_amount": outstanding, "filing_status": status}, update_modified=False)
	return outstanding, status


def validate_accounting_settlement(doc):
	if doc.accounting_voucher_type not in ("Payment Entry", "Journal Entry") or not doc.accounting_voucher:
		frappe.throw(_("Link a submitted Payment Entry or Journal Entry before submitting the VAT payment"))
	voucher = frappe.get_doc(doc.accounting_voucher_type, doc.accounting_voucher)
	voucher.check_permission("read")
	if voucher.company != doc.company or voucher.docstatus != 1:
		frappe.throw(_("Payment accounting must be submitted in this Company"))
	if getdate(voucher.posting_date) != getdate(doc.payment_date):
		frappe.throw(_("Payment date must match the linked accounting voucher posting date"))
	account = frappe.get_cached_doc("Account", doc.bank_account)
	if account.company != doc.company or account.is_group or account.account_type not in ("Bank", "Cash"):
		frappe.throw(_("Select a leaf Bank or Cash account in the filing Company"))
	settings = engine.settings_for(doc.company)
	vat_accounts = set(engine.account_mappings(settings.get("uae_vat_accounts", [])))
	entries = frappe.get_all("GL Entry", filters={"company": doc.company, "voucher_type": doc.accounting_voucher_type,
		"voucher_no": doc.accounting_voucher, "is_cancelled": 0}, fields=["name", "account", "debit", "credit"])
	vat_debit = sum((engine.number(row.debit) - engine.number(row.credit) for row in entries if row.account in vat_accounts), engine.number(0))
	bank_credit = sum((engine.number(row.credit) - engine.number(row.debit) for row in entries if row.account == doc.bank_account), engine.number(0))
	amount = decimal_value(doc.payment_amount)
	if engine.money(vat_debit) != engine.money(amount) or engine.money(bank_credit) != engine.money(amount):
		frappe.throw(_("The accounting voucher must debit configured VAT control account(s) and credit the selected bank account by the payment amount"))
	return voucher


class PaymentRecord(EvidenceRecord):
	def validate(self):
		super().validate()
		parent = linked_filing(self)
		self.company = parent.company
		self.from_date, self.to_date = parent.from_date, parent.to_date
		if decimal_value(self.payment_amount) <= 0:
			frappe.throw(_("Payment amount must be positive"))
		if not self.payment_date or not self.payment_reference:
			frappe.throw(_("Actual payment date and reference are required"))
		if self.docstatus == 1 or self.accounting_voucher:
			validate_accounting_settlement(self)

	def before_submit(self):
		super().before_submit()
		frappe.db.sql("select name from `tabCompany` where name=%s for update", self.company)
		frappe.db.sql("select name from `tabVAT 201 Filing` where name=%s for update", self.filing)
		if frappe.db.exists("VAT 201 Payment", {"company": self.company, "payment_reference": self.payment_reference, "docstatus": 1}):
			frappe.throw(_("This payment reference is already recorded"))
		if frappe.db.exists("VAT 201 Payment", {"accounting_voucher_type": self.accounting_voucher_type,
			"accounting_voucher": self.accounting_voucher, "docstatus": 1}):
			frappe.throw(_("This accounting voucher is already linked to a submitted VAT payment"))
		parent = linked_filing(self)
		paid = submitted_payment_total(parent.name, exclude=self.name)
		outstanding, status = payment_state(parent, paid)
		self.outstanding_before_payment = outstanding
		if decimal_value(self.payment_amount) > engine.number(outstanding):
			frappe.throw(_("Payment amount cannot exceed the outstanding VAT liability"))

	def on_submit(self):
		sync_filing_payment_status(self.filing)

	def before_cancel(self):
		manager(self.company)
		if self.accounting_voucher and frappe.db.get_value(self.accounting_voucher_type, self.accounting_voucher, "docstatus") == 1:
			frappe.throw(_("Cancel the linked accounting voucher before cancelling this VAT payment record"))

	def on_cancel(self):
		sync_filing_payment_status(self.filing)


@frappe.whitelist()
def payment_context(filing):
	doc = frappe.get_doc("VAT 201 Filing", filing)
	doc.check_permission("read")
	if doc.docstatus != 1:
		frappe.throw(_("Submit the VAT filing before recording payment"))
	outstanding, status = payment_state(doc)
	return dict(company=doc.company, filing=doc.name, from_date=doc.from_date, to_date=doc.to_date,
		outstanding_amount=outstanding, filing_status=status)


def settlement_exclusions(company, from_date, to_date, settings=None):
	"""Classify linked VAT settlement GL rows as control movements, never current-period input VAT."""
	payments = frappe.get_all("VAT 201 Payment", filters={"company": company, "docstatus": 1,
		"payment_date": ["between", [from_date, to_date]]},
		fields=["name", "filing", "payment_date", "payment_amount", "accounting_voucher_type", "accounting_voucher"])
	if not payments:
		return []
	settings = settings or engine.settings_for(company)
	vat_accounts = set(engine.account_mappings(settings.get("uae_vat_accounts", [])))
	rows = []
	for payment in payments:
		if not payment.accounting_voucher or frappe.db.get_value(payment.accounting_voucher_type, payment.accounting_voucher, "docstatus") != 1:
			continue
		entries = frappe.get_all("GL Entry", filters={"company": company, "voucher_type": payment.accounting_voucher_type,
			"voucher_no": payment.accounting_voucher, "is_cancelled": 0, "account": ["in", list(vat_accounts)]},
			fields=["name", "posting_date", "voucher_type", "voucher_no", "account", "debit", "credit"])
		for entry in entries:
			rows.append(dict(entry, source_row=entry.name, tax_account=entry.account, box="Outside VAT", amount=0,
				vat_amount=0, adjustment=0, reason="VAT 201 payment settlement", supporting_reference=payment.name,
				company=company, currency="AED", tax_date=str(entry.posting_date)))
	return rows


class DifferenceRecord(EvidenceRecord):
	def validate(self):
		super().validate()
		filing = linked_filing(self)
		entry = frappe.get_doc("GL Entry", self.gl_entry)
		entry.check_permission("read")
		if (entry.company, entry.voucher_type, entry.voucher_no, entry.docstatus, entry.is_cancelled) != (self.company, self.voucher_type, self.voucher_no, 1, 0):
			frappe.throw(_("The reconciliation item must reference an active GL row of this Company and voucher"))
		if not getdate(filing.from_date) <= getdate(entry.posting_date) <= getdate(filing.to_date):
			frappe.throw(_("GL row is outside this filing's posting period"))
		settings = engine.settings_for(self.company)
		if entry.account not in engine.account_mappings(settings.get("uae_vat_accounts", [])):
			frappe.throw(_("Select a configured VAT control account GL row"))
		if abs(decimal_value(self.difference)) > abs(decimal_value(entry.credit) - decimal_value(entry.debit)):
			frappe.throw(_("Explained difference cannot exceed the referenced VAT movement"))
		decimal_value(self.vat_amount)
		self.posting_date = entry.posting_date

	def before_submit(self):
		super().before_submit()
		frappe.db.sql("select name from `tabCompany` where name=%s for update", self.company)
		if frappe.db.exists("VAT 201 Filed Difference", {"filing": self.filing, "gl_entry": self.gl_entry, "docstatus": 1}):
			frappe.throw(_("This GL row already has a submitted filed-difference explanation"))


def compare(result, filing=None, payments=(), explanations=()):
	"""Pure comparison: omitted boxes and unverified payment remain unknown."""
	calculated = next(b["amount"] for b in result["boxes"] if b["box"] == "14")
	gl = result.get("ledger_summary", {}).get("period_net_credit") if result.get("header", {}).get("base_currency") == "AED" else None
	out = dict(calculated_liability=calculated, gl_net_movement=gl, filed_liability=None,
		amount_due=None, payment_amount=None, outstanding_balance=None, payment_status="Unknown / Not Verified",
		filing_status="No submitted filing evidence", gl_less_filed=None, calculated_less_filed=None,
		explained_difference=None, unexplained_difference=None, known_values=[], explanations=list(explanations))
	if not filing:
		return out
	get = filing.get
	liability = get("filed_liability") if get("filed_liability_known") else None
	out.update(filing=get("name"), filing_status="Submitted", fta_reference=get("fta_reference"),
		submission_date=str(get("submission_date")), filed_liability=liability,
		amount_due=get("amount_due") if get("amount_due_known") else None)
	known = {(r["box"], r["component"]): r["value"] for r in get("filed_values", [])}
	if liability is not None:
		known[("14", "amount")] = liability
	for box in result["boxes"]:
		for component in ("amount", "vat_amount", "adjustment"):
			filed = known.get((box["box"], component))
			out["known_values"].append(dict(box=box["box"], component=component, calculated=box[component], filed=filed,
				difference=engine.money(engine.number(box[component])-engine.number(filed)) if filed is not None else None))
	if liability is not None:
		out["calculated_less_filed"] = engine.money(engine.number(calculated)-engine.number(liability))
		if gl is not None:
			out["gl_less_filed"] = engine.money(engine.number(gl)-engine.number(liability))
			out["explained_difference"] = engine.money(sum((engine.number(r["difference"]) for r in explanations), engine.number(0)))
			out["unexplained_difference"] = engine.money(engine.number(out["gl_less_filed"])-engine.number(out["explained_difference"]))
			out["difference_status"] = "Unexplained filed-return difference" if out["unexplained_difference"] else "Reconciled by recorded evidence"
	paid = sum((engine.number(p["payment_amount"]) for p in payments), engine.number(0))
	out["payment_amount"] = engine.money(paid) if payments else None
	if out["amount_due"] is not None:
		balance = engine.number(out["amount_due"]) - paid
		if liability is not None and engine.number(liability) < 0:
			status = "Recoverable"
		elif balance <= 0:
			status = "Paid"
		elif paid:
			status = "Partially Paid"
		else:
			status = "Payment Pending"
		out.update(outstanding_balance=engine.money(max(balance, engine.number(0))), payment_status=status)
	elif payments:
		out["payment_status"] = "Payment evidenced; amount due unknown"
	if get("calculation_snapshot"):
		snapshot = frappe.parse_json(get("calculation_snapshot"))
		old = next((b["amount"] for b in snapshot.get("boxes", []) if b["box"] == "14"), None)
		out["calculation_change_since_recording"] = engine.money(engine.number(calculated)-engine.number(old)) if old is not None else None
	return out


def attach_comparison(result):
	header = result.get("header", {})
	result["filed_comparison"] = compare(result)
	if not all(header.get(k) for k in ("company", "from_date", "to_date")):
		return
	if not frappe.db.exists("DocType", "VAT 201 Filing"):
		result["filed_comparison"]["filing_status"] = "Filing register migration required"
		return
	if not frappe.has_permission("VAT 201 Filing", "read"):
		result["filed_comparison"]["filing_status"] = "Filing evidence access restricted"
		return
	rows = frappe.get_list("VAT 201 Filing", filters={"company": header["company"], "from_date": header["from_date"], "to_date": header["to_date"], "docstatus": 1}, fields=["name", "correction_of"], limit_page_length=0)
	superseded = {row.correction_of for row in rows if row.correction_of}
	current = [row for row in rows if row.name not in superseded]
	if len(current) != 1:
		if current:
			result["filed_comparison"]["filing_status"] = "Conflicting submitted filings; review required"
		return
	filing = frappe.get_doc("VAT 201 Filing", current[0].name)
	filing.check_permission("read")
	by_name = {row.name: row for row in rows}
	chain, cursor = [], filing.name
	while cursor and cursor not in chain and cursor in by_name:
		chain.append(cursor)
		cursor = by_name[cursor].correction_of
	def children(dt):
		if not frappe.has_permission(dt, "read"):
			return []
		rows = frappe.get_list(dt, filters={"company": header["company"], "filing": ["in", chain] if dt == "VAT 201 Payment" else filing.name, "docstatus": 1}, fields=["*"], limit_page_length=0)
		if dt == "VAT 201 Payment":
			rows = [row for row in rows if row.get("accounting_voucher") and
				frappe.db.get_value(row.accounting_voucher_type, row.accounting_voucher, "docstatus") == 1]
		return rows
	result["filed_comparison"] = compare(result, filing.as_dict(), children("VAT 201 Payment"), children("VAT 201 Filed Difference"))
