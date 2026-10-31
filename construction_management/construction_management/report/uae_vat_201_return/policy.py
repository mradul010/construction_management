"""Read-only application of explicitly approved, company-scoped recovery policies."""
from decimal import InvalidOperation

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime

from construction_management.construction_management.report.uae_vat_201_return import engine

FIELD = "custom_vat201_recovery_policies"
POLICY_FIELDS = ("policy_name", "enabled", "applies_to", "expense_account", "tax_category", "tax_template",
	"project", "cost_center", "valid_from", "valid_to", "recovery_percent", "payment_condition", "basis", "supporting_reference", "approved")


def validate(doc, previous=None):
	old = {r.name: r for r in previous.get(FIELD, [])} if previous else {}
	rows = doc.get(FIELD, [])
	manager = bool(set(frappe.get_roles()) & {"Accounts Manager", "System Manager"})
	if not manager and set(old) != {r.name for r in rows}:
		frappe.throw(_("Only Accounts Managers may change VAT recovery policies"), frappe.PermissionError)
	for row in rows:
		prior = old.get(row.name)
		changed = not prior or any(row.get(k) != prior.get(k) for k in POLICY_FIELDS)
		if changed and not manager:
			frappe.throw(_("Only Accounts Managers may change VAT recovery policies"), frappe.PermissionError)
		try:
			percent = engine.number(row.get("recovery_percent"))
		except (InvalidOperation, ValueError, TypeError):
			frappe.throw(_("Policy recovery percentage is invalid"))
		if not percent.is_finite() or not 0 <= percent <= 100:
			frappe.throw(_("Policy recovery percentage must be between 0 and 100"))
		if row.applies_to not in ("Purchase Invoice", "Expense Journal"):
			frappe.throw(_("Unsupported recovery policy source type"))
		if not row.valid_from or row.valid_to and getdate(row.valid_to) < getdate(row.valid_from):
			frappe.throw(_("Policy effective dates are invalid"))
		account = frappe.get_cached_doc("Account", row.expense_account)
		if account.company != doc.company or account.root_type != "Expense" or account.is_group:
			frappe.throw(_("Recovery policies require an exact expense posting account in this Company"))
		if row.applies_to == "Purchase Invoice" and not (row.tax_category or row.tax_template):
			frappe.throw(_("Purchase policies require a Tax Category or Purchase Tax Template as well as an expense account"))
		if row.applies_to == "Expense Journal" and (row.tax_category or row.tax_template):
			frappe.throw(_("Expense Journal policies cannot silently ignore invoice tax selectors"))
		if row.payment_condition not in ("Paid invoices only", "Paid or intended within required time"):
			frappe.throw(_("Select the approved policy payment condition"))
		for dt, key in (("Project", "project"), ("Cost Center", "cost_center"), ("Purchase Taxes and Charges Template", "tax_template")):
			if row.get(key) and frappe.get_cached_value(dt, row.get(key), "company") != doc.company:
				frappe.throw(_("Policy scope must belong to the configured Company"))
		if row.approved:
			if not row.basis or not row.supporting_reference:
				frappe.throw(_("Policy approval requires business-use basis and supporting policy evidence"))
			row.approved_by = frappe.session.user if changed else prior.approved_by
			row.approval_time = now_datetime() if changed else prior.approval_time
		else:
			row.approved_by = row.approval_time = None


def base_rows(source):
	if source["voucher_type"] == "Purchase Invoice":
		return source.get("tax_item_evidence", source.get("item_evidence", []))
	ids = set(source.get("base_row_references", []))
	return [r for r in source.get("journal_evidence", {}).get("document", {}).get("accounts", []) if r.get("name") in ids]


def resolve(source, settings, base_currency):
	"""No default entitlement: return a normal engine rule only for a unique match."""
	if source["voucher_type"] not in ("Purchase Invoice", "Journal Entry") or not source.get("raw_vat"):
		return None, None
	if source.get("reverse_charge") == "Y":
		return None, "Reverse-charge recovery requires its existing specific evidence or approved decision"
	if source.get("journal_invoice_linked") or source.get("journal_duplicate_risk") or source.get("journal_match_issue"):
		return None, source.get("journal_duplicate_risk") or source.get("journal_match_issue") or "Invoice-linked journal VAT cannot be claimed again"
	if source["voucher_type"] == "Journal Entry" and source.get("journal_category") != "Recorded purchase VAT":
		return None, None
	if source.get("invoice_tax_difference"):
		return None, "Source VAT does not reconcile with active GL postings"
	if source.get("base") is None or base_currency != "AED":
		return None, "Source taxable-base allocation or AED tax-point exchange evidence is missing"
	items = base_rows(source)
	if not items:
		return None, "Expense classification is missing from source rows"
	type_name = "Purchase Invoice" if source["voucher_type"] == "Purchase Invoice" else "Expense Journal"
	matches = []
	for row in settings.get(FIELD, []):
		if not row.get("enabled") or not row.get("approved") or not row.get("approved_by") or not row.get("approval_time") or row.get("applies_to") != type_name:
			continue
		if not row.get("valid_from") or getdate(source["posting_date"]) < getdate(row.valid_from) or row.get("valid_to") and getdate(source["posting_date"]) > getdate(row.valid_to):
			continue
		if not row.get("expense_account") or not all((item.get("expense_account") or item.get("account")) == row.expense_account for item in items):
			continue
		if any(row.get(key) and not all(item.get(key) == row.get(key) for item in items) for key in ("project", "cost_center")):
			continue
		if type_name == "Purchase Invoice":
			if not (row.get("tax_category") or row.get("tax_template")) or any(row.get(k) and row.get(k) != source.get(k) for k in ("tax_category", "tax_template")):
				continue
		elif row.get("tax_category") or row.get("tax_template"):
			continue
		matches.append(row)
	if len(matches) > 1:
		return None, "Recovery policies conflict for this source"
	row = matches[0] if matches else None
	try:
		saved = engine.number(source.get("recovery_source_amount")) if type_name == "Purchase Invoice" else engine.number(0)
	except (InvalidOperation, ValueError, TypeError):
		return None, "Saved recovery amount is invalid"
	if not saved.is_finite():
		return None, "Saved recovery amount is invalid"
	vat = engine.number(source["raw_vat"])
	if saved and (saved * vat < 0 or abs(saved) > abs(vat) or source.get("vat_rows_count") != 1):
		return None, "Saved recovery amount has conflicting sign, limit or multi-row allocation"
	if not row and not saved:
		if type_name == "Expense Journal":
			return None, "Recovery not specified in source."
		return None, "No approved recovery policy matches the source expense/tax classification; default zero is not an explicit recovery decision"
	try:
		percent = engine.number(row.recovery_percent) if row else saved / vat * 100
	except (InvalidOperation, ValueError, TypeError):
		return None, "Matched policy has an invalid recovery percentage"
	if not percent.is_finite() or not 0 <= percent <= 100:
		return None, "Matched policy has an invalid recovery percentage"
	if row and saved and engine.money(vat * percent / 100) != engine.money(saved):
		return None, "Saved explicit recovery amount conflicts with the applicable policy"
	if type_name == "Purchase Invoice":
		if source.get("purchase_country") != "United Arab Emirates":
			return None, "Domestic policy requires a saved UAE supplier country/address; import/reverse-charge treatment needs clarification"
		if percent and not (source.get("bill_no") and source.get("bill_date") and len(str(source.get("source_tax_id") or "").strip()) == 15 and str(source.get("source_tax_id")).strip().isdigit()):
			return None, "Policy recovery requires the saved supplier tax invoice number/date and valid supplier TRN"
		if percent and row and row.payment_condition == "Paid invoices only" and (source.get("outstanding_amount") is None or engine.money(source["outstanding_amount"])):
			return None, "Matched policy only covers paid invoices; the source has an outstanding balance"
	elif percent:
		# The approved reusable rule supplies the eligibility basis. A matched
		# expense group need not repeat it in per-journal bill/attachment fields.
		if row.payment_condition == "Paid invoices only":
			return None, "Journal payment condition requires an explicit supported decision; invoice paid status is not available"
	if not row:
		return frappe._dict(box="9", tax_date=source["posting_date"], reason="Explicit saved AED recovery amount on the submitted invoice",
			supporting_reference=source["voucher_no"], recovery_confirmed=1, recovery_percent=float(percent), override_base=0, is_adjustment=0,
			treatment_source="Saved source recovery amount"), None
	return frappe._dict(box="9", tax_date=source["posting_date"], reason=row.basis, supporting_reference=row.supporting_reference,
		recovery_confirmed=1, recovery_percent=float(percent), override_base=0, is_adjustment=0,
		treatment_source="Company-approved policy", policy_id=row.name, policy_name=row.policy_name, policy_approved_by=row.approved_by, policy_approval_time=row.approval_time), None
