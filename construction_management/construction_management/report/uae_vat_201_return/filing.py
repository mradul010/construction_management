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
		if not self.reason or not self.supporting_evidence:
			frappe.throw(_("Reason and supporting documentary evidence are required"))
		files = frappe.get_list("File", filters={"file_url": self.supporting_evidence}, fields=["name"], limit_page_length=1)
		if not files:
			frappe.throw(_("Attach accessible documentary evidence before saving"))
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
		if not self.from_date or not self.to_date or getdate(self.from_date) > getdate(self.to_date):
			frappe.throw(_("A valid filing period is required"))
		if not self.submission_date or getdate(self.submission_date) < getdate(self.to_date):
			frappe.throw(_("Submission date cannot precede the period end"))
		if not self.filed_liability_known:
			frappe.throw(_("The filed Box 14 must be explicitly known; zero is a valid known value"))
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
		from construction_management.construction_management.report.uae_vat_201_return.automatic import build
		result = build(dict(company=self.company, from_date=self.from_date, to_date=self.to_date))
		self.calculation_snapshot = frappe.as_json({key: result.get(key) for key in
			("boxes", "ledger_summary", "tax_measures", "status", "calculated_at")})


def linked_filing(doc):
	filing = frappe.get_doc("VAT 201 Filing", doc.get("filing") or doc.get("correction_of"))
	filing.check_permission("read")
	if filing.company != doc.company or filing.docstatus != 1:
		frappe.throw(_("Select a submitted filing in this Company"))
	return filing


class PaymentRecord(EvidenceRecord):
	def validate(self):
		super().validate()
		linked_filing(self)
		if decimal_value(self.payment_amount) <= 0:
			frappe.throw(_("Payment amount must be positive"))
		if not self.payment_date or not self.payment_reference:
			frappe.throw(_("Actual payment date and reference are required"))
		if self.accounting_voucher:
			if self.accounting_voucher_type not in ("Payment Entry", "Journal Entry"):
				frappe.throw(_("Select a payment or journal voucher"))
			voucher = frappe.get_doc(self.accounting_voucher_type, self.accounting_voucher)
			voucher.check_permission("read")
			if voucher.company != self.company or voucher.docstatus != 1:
				frappe.throw(_("Payment accounting must be submitted in this Company"))

	def before_submit(self):
		super().before_submit()
		frappe.db.sql("select name from `tabCompany` where name=%s for update", self.company)
		if frappe.db.exists("VAT 201 Payment", {"company": self.company, "payment_reference": self.payment_reference, "docstatus": 1}):
			frappe.throw(_("This payment reference is already recorded"))


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
	if payments:
		paid = sum((engine.number(p["payment_amount"]) for p in payments), engine.number(0))
		out["payment_amount"] = engine.money(paid)
		if out["amount_due"] is not None:
			balance = engine.number(out["amount_due"]) - paid
			out.update(outstanding_balance=engine.money(balance), payment_status="Paid" if balance == 0 else "Overpaid" if balance < 0 else "Partially Paid")
		else:
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
		return frappe.get_list(dt, filters={"company": header["company"], "filing": ["in", chain] if dt == "VAT 201 Payment" else filing.name, "docstatus": 1}, fields=["*"], limit_page_length=0)
	result["filed_comparison"] = compare(result, filing.as_dict(), children("VAT 201 Payment"), children("VAT 201 Filed Difference"))
