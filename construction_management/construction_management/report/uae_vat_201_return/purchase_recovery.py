"""Audited updates to the existing, non-posting purchase VAT recovery amount."""
from decimal import Decimal, InvalidOperation

import frappe
from frappe import _
from frappe.utils import escape_html, get_datetime

FIELD = "recoverable_standard_rated_expenses"


def confirmed_zero_recovery(docs):
	"""Use a documented manager decision, not the localization's default zero."""
	from bs4 import BeautifulSoup
	parents = {doc.name: doc for doc in docs if doc.get(FIELD) == 0 and doc.get("reverse_charge") != "Y"}
	if not parents:
		return {}
	# Read audit comments only after their source parents passed report permissions.
	comments = frappe.get_all("Comment", filters={"reference_doctype": "Purchase Invoice",
		"reference_name": ["in", list(parents)], "comment_type": "Info", "content": ["like", "%vat201_purchase_recovery%"]},
		fields=["name", "reference_name", "content", "owner"], order_by="creation desc", limit_page_length=0)
	confirmed = {}
	for comment in comments:
		for block in BeautifulSoup(comment.content or "", "html.parser").find_all("pre"):
			try:
				data = frappe.parse_json(block.get_text())
				parent = parents[comment.reference_name]
				if not isinstance(data, dict) or data.get("vat201_purchase_recovery") != 1:
					continue
				if (data.get("invoice") != parent.name or data.get("field") != FIELD or
					data.get("amount") != 0 or not data.get("reason") or not data.get("invoice_modified") or
					not parent.get("modified") or get_datetime(data["invoice_modified"]) != get_datetime(parent.modified)):
					continue
				if set(frappe.get_roles(comment.owner)) & {"Accounts Manager", "System Manager"}:
					confirmed[parent.name] = comment.name
			except (TypeError, ValueError, KeyError):
				continue
	return confirmed


def setup():
	"""Use supported metadata customization, without changing core or running migrate."""
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter
	field = frappe.get_meta("Purchase Invoice").get_field(FIELD)
	if not field or field.fieldtype != "Currency":
		frappe.throw(_("Expected Recoverable Standard Rated Expenses to be a Currency amount"))
	if not field.allow_on_submit:
		make_property_setter("Purchase Invoice", FIELD, "allow_on_submit", "1", "Check")
	frappe.clear_cache(doctype="Purchase Invoice")


def check_manager(doc):
	if not set(frappe.get_roles()) & {"Accounts Manager", "System Manager"}:
		frappe.throw(_("Only Accounts Managers or System Managers may update submitted VAT recovery"), frappe.PermissionError)
	doc.check_permission("write")
	if doc.docstatus != 1:
		frappe.throw(_("VAT recovery updates require a submitted Purchase Invoice"))


def checked_amount(value):
	try:
		amount = Decimal(str(value))
	except (InvalidOperation, ValueError, TypeError):
		frappe.throw(_("Enter a valid recoverable VAT amount in AED"))
	if not amount.is_finite():
		frappe.throw(_("Enter a finite recoverable VAT amount in AED"))
	return amount


def validate_update(doc, method=None):
	previous = doc.get_doc_before_save()
	if not previous or doc.get(FIELD) == previous.get(FIELD):
		return
	check_manager(doc)
	if not (doc.flags.get("vat201_recovery_reason") or "").strip():
		frappe.throw(_("Use Update VAT Recovery and provide a reason for the audit trail"))
	if doc.get("reverse_charge") == "Y":
		frappe.throw(_("Standard-rated recovery amount is not applicable to reverse-charge invoices"))
	if frappe.get_cached_value("Company", doc.company, "default_currency") != "AED":
		frappe.throw(_("This recovery update requires an AED Company"))
	from construction_management.construction_management.report.uae_vat_201_return.engine import account_mappings, settings_for
	accounts = account_mappings(settings_for(doc.company).get("uae_vat_accounts", []))
	vat = sum((checked_amount(row.base_tax_amount_after_discount_amount or 0) *
		(-1 if row.get("add_deduct_tax") == "Deduct" else 1) for row in doc.taxes
		if accounts.get(row.account_head) in ("Input", "Both")), Decimal(0))
	amount = checked_amount(doc.get(FIELD))
	if amount * vat < 0 or abs(amount) > abs(vat):
		frappe.throw(_("Recoverable VAT must have the recorded VAT sign and cannot exceed its amount"))
	validate_accounting_copy(doc)


def posting_values(doc):
	header = ("company", "supplier", "credit_to", "currency", "conversion_rate", "posting_date", "is_return",
		"net_total", "base_net_total", "total_taxes_and_charges", "base_total_taxes_and_charges", "grand_total",
		"base_grand_total", "rounded_total", "base_rounded_total", "outstanding_amount", "paid_amount", "write_off_amount")
	items = ("item_code", "expense_account", "qty", "rate", "amount", "net_amount", "base_net_amount", "cost_center", "project")
	taxes = ("account_head", "charge_type", "rate", "tax_amount", "base_tax_amount", "tax_amount_after_discount_amount",
		"base_tax_amount_after_discount_amount", "add_deduct_tax", "category", "total", "base_total")
	return ([doc.get(key) for key in header],
		[[row.get(key) for key in items] for row in doc.get("items", [])],
		[[row.get(key) for key in taxes] for row in doc.get("taxes", [])])


def validate_accounting_copy(doc):
	# Full validation recalculates display-only flags on older submitted invoices.
	# Validate a detached candidate, require identical posting values, then let the
	# actual document pass normal update-after-submit checks without ignore flags.
	candidate = frappe.get_doc(doc.as_dict())
	before = posting_values(candidate)
	candidate.run_method("validate")
	if posting_values(candidate) != before:
		frappe.throw(_("Invoice validation recalculates accounting values. VAT recovery cannot be updated without accounting review"))


@frappe.whitelist(methods=["POST"])
def update_recovery(invoice, amount, reason, modified):
	doc = frappe.get_doc("Purchase Invoice", invoice)
	check_manager(doc)
	if not isinstance(reason, str) or not reason.strip():
		frappe.throw(_("A reason is required for the VAT recovery audit trail"))
	if not modified or get_datetime(modified) != get_datetime(doc.modified):
		frappe.throw(_("Invoice changed. Reload it before updating VAT recovery"), frappe.TimestampMismatchError)
	field = doc.meta.get_field(FIELD)
	if not field or field.fieldtype != "Currency" or not field.allow_on_submit:
		frappe.throw(_("VAT recovery update metadata is not configured"))
	new_amount = checked_amount(amount)
	precision = doc.precision(FIELD)
	if new_amount != new_amount.quantize(Decimal(1).scaleb(-precision)):
		frappe.throw(_("Recoverable VAT must use the field's currency precision"))
	old_amount = doc.get(FIELD)
	doc.set(FIELD, float(new_amount))
	doc.flags.vat201_recovery_reason = reason.strip()
	doc.save(ignore_version=False)
	decision = dict(vat201_purchase_recovery=1, invoice=doc.name, field=FIELD,
		amount=doc.get(FIELD), reason=reason.strip(), invoice_modified=str(doc.modified))
	doc.add_comment("Info", _("VAT recovery (AED): {0} to {1}. Reason: {2}").format(
		escape_html(str(old_amount)), escape_html(str(doc.get(FIELD))), escape_html(reason.strip()))
		+ "<pre>" + escape_html(frappe.as_json(decision)) + "</pre>")
	return {"invoice": doc.name, "recoverable_amount": doc.get(FIELD), "modified": doc.modified}
