"""Evidence-backed suggestions and explicit, audited accountant decisions."""
import hashlib
import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, add_days


def control_movement_only(source, rule):
	return source["voucher_type"] in ("Journal Entry","Payment Entry") and rule.get("journal_treatment") in (
		"VAT settlement","VAT payment","VAT reclassification")


def fingerprint(source):
	keys = ("voucher_type", "voucher_no", "source_row", "posting_date", "base", "raw_vat",
		"tax_account", "reverse_charge", "is_return", "return_against", "source_emirate", "project",
		"gl_evidence", "item_evidence", "journal_evidence")
	return hashlib.sha256(json.dumps({k: source.get(k) for k in keys}, sort_keys=True, default=str).encode()).hexdigest()


def decision_fingerprint(source):
	"""Bind new approvals to recovery proposals and the exact amended document."""
	return hashlib.sha256((fingerprint(source) + json.dumps({key: source.get(key) for key in
		("recovery_source_amount", "reverse_recovery_percent")}, sort_keys=True, default=str)).encode()).hexdigest()


def enrich_journals(sources):
	from construction_management.construction_management.report.uae_vat_201_return.journal import match_journal, link_advance_evidence
	cache = {}
	account_catalog = {}
	for source in sources:
		if source["voucher_type"] not in ("Journal Entry", "Payment Entry"):
			continue
		key = (source["voucher_type"], source["voucher_no"])
		if key not in cache:
			doc = frappe.get_doc(*key)
			doc.check_permission("read")
			doc.apply_fieldlevel_read_permissions()
			files = frappe.get_list("File", filters={"attached_to_doctype": key[0], "attached_to_name": key[1]},
				fields=["name", "file_name", "file_url"], limit_page_length=0) if frappe.has_permission("File", "read") else []
			cache[key] = dict(document=doc.as_dict(), attachments=[dict(f) for f in files])
		source["journal_evidence"] = cache[key]
		doc = cache[key]["document"]
		source["remarks"] = doc.get("remark") or doc.get("remarks") or doc.get("user_remark")
		source["journal_category"] = "Unresolved"
	for (doctype, _name), evidence in cache.items():
		if doctype != "Journal Entry":
			continue
		doc = evidence["document"]
		company = doc["company"]
		if company not in account_catalog:
			account_catalog[company] = set(frappe.get_list("Account", filters={"company":company,"root_type":"Expense"}, pluck="name",limit_page_length=0))
		matching = [source for source in sources if source["voucher_type"] == doctype and source["voucher_no"] == doc["name"]]
		company_doc = frappe.get_cached_doc("Company", company)
		advance_accounts = {company_doc.get(field) for field in ("default_customer_advance_account", "default_advance_received_account") if company_doc.get(field)}
		match_journal(doc, matching, account_catalog[company], company_doc.default_currency, advance_accounts)
	companies = {e["document"]["company"] for e in cache.values()}
	for company in companies:
		advances = [s for s in sources if s.get("journal_category") == "Customer-advance output VAT" and
			s.get("journal_evidence", {}).get("document", {}).get("company") == company]
		if not advances:
			continue
		can_check_invoices = frappe.has_permission("Sales Invoice", "read")
		invoices = frappe.get_list("Sales Invoice", filters={"company":company,"docstatus":1},
			fields=["name","company","customer","vat_emirate"], limit_page_length=0) if can_check_invoices else []
		parents = [invoice.name for invoice in invoices]
		names = list({source["voucher_no"] for source in advances})
		allocations = frappe.get_all("Sales Invoice Advance", filters={"parent":["in",parents],"parenttype":"Sales Invoice",
			"reference_type":"Journal Entry","reference_name":["in",names]},
			fields=["parent","reference_type","reference_name","allocated_amount"],limit_page_length=0) if parents else []
		journals = frappe.get_list("Journal Entry", filters={"company":company,"docstatus":1}, pluck="name",limit_page_length=0)
		adjustments = frappe.get_all("Journal Entry Account", filters={"parent":["in",journals],"parenttype":"Journal Entry",
			"reference_type":"Journal Entry","reference_name":["in",names]}, fields=["parent","reference_name"],limit_page_length=0) if journals else []
		link_advance_evidence(advances, invoices, allocations, adjustments)
		if not can_check_invoices:
			for source in advances:
				source["journal_duplicate_risk"] = "Sales Invoice access is required to check customer-advance VAT overlap; source scope is incomplete"


def suggest(source, mappings, rules=()):
	"""A suggested box is not an approval or proof of input-tax entitlement."""
	dt = source["voucher_type"]
	box, reasons = None, []
	if dt not in ("Sales Invoice", "POS Invoice", "Purchase Invoice"):
		evidence = source.get("journal_evidence", {})
		doc = evidence.get("document", {})
		reasons.append("REVIEW REQUIRED: journal/payment business purpose, taxable base, tax point and VAT side need supporting evidence; not classified by debit/credit")
		if not evidence.get("attachments"):
			reasons.append("No accessible supporting attachments")
		refs = [(r.get("reference_type"), r.get("reference_name")) for r in doc.get("accounts", []) if r.get("reference_name")]
		if not refs:
			reasons.append("No structured invoice references")
		if source.get("base_row_reference"):
			reasons.append("Generator base row identified: " + source["base_row_reference"] + "; amount is evidence, not approval of VAT eligibility")
		if source.get("project_conflict"):
			reasons.append(source["project_conflict"])
	elif source.get("invoice_tax_difference"):
		reasons.append("Invoice tax rows do not reconcile with GL; resolve the source difference")
	elif source.get("tax_account") and source["tax_account"] not in mappings:
		reasons.append("Tax account is not mapped as VAT; verify VAT versus other tax")
	elif dt in ("Sales Invoice", "POS Invoice"):
		from erpnext.regional.report.uae_vat_201.uae_vat_201 import get_emirates
		if source.get("treatment_hint") in ("Zero Rated", "Exempt") and not source.get("raw_vat"):
			box = "4" if source["treatment_hint"] == "Zero Rated" else "5"
			reasons.append("Source item explicitly marked " + source["treatment_hint"] + "; confirm supporting treatment and tax point")
		elif source.get("tax_account") and source.get("source_emirate") in get_emirates() and flt(source.get("tax_rate")) == 5:
			box = "1" + chr(97 + get_emirates().index(source["source_emirate"]))
			reasons.append("Emirate box uses the saved invoice VAT Emirate")
		elif source.get("tax_account") and flt(source.get("tax_rate")) == 5:
			reasons.append("VAT Emirate is missing or invalid; select a valid UAE Emirate on the source invoice")
		else:
			reasons.append("No sufficient standard-rated/zero/exempt supply evidence")
	else:
		if source.get("tax_account") and source.get("raw_vat"):
			box = "10" if source.get("reverse_charge") == "Y" else "9"
			reasons.append("Potential input VAT from submitted purchase tax row; recoverability and tax point require explicit review")
			if source.get("reverse_charge") == "Y":
				reasons.append("Reverse charge uses the saved standard recovery percentage and requires matching Box 3 output/GL evidence")
			if not source.get("source_tax_id"):
				reasons.append("Supplier TRN not recorded on invoice; verify original tax invoice")
			if source.get("reverse_charge") != "Y" and source.get("recovery_source_amount") in (None, ""):
				reasons.append("Recoverable Standard Rated Expenses (AED) is missing")
			elif source.get("reverse_charge") != "Y" and not flt(source.get("recovery_source_amount")):
				reasons.append("Saved recoverable VAT amount is zero; recovery is pending approval unless a valid reviewed decision exists")
		else:
			reasons.append("Untaxed purchase item: missing VAT does not prove zero-rated/exempt treatment or entitlement")
	if source.get("base") is None:
		reasons.append("Reviewed taxable-base allocation required")
	if source.get("is_return"):
		reasons.append("Return preserves signed source tax; verify original treatment: " + (source.get("return_against") or "original voucher not linked"))
		original = [r for r in rules if r.get("approved") and r.voucher_type == dt and r.voucher_no == source.get("return_against")]
		if len({r.box for r in original}) == 1 and not (dt in ("Sales Invoice", "POS Invoice") and source.get("tax_account") and flt(source.get("tax_rate")) == 5):
			box = original[0].box
			reasons.append("Suggested box inherited from approved original voucher; confirm matching tax line")
	return box, "; ".join(reasons)


def annotate_reviews(reviews, settings, mappings):
	rows = settings.get("custom_vat201_classifications", [])
	by_source = {}
	for row in rows:
		by_source.setdefault((row.voucher_type, row.voucher_no, row.source_row), []).append(row)
	for source in reviews:
		box, reason = suggest(source, mappings, rows)
		saved = by_source.get((source["voucher_type"], source["voucher_no"], source["source_row"]), [])
		record = saved[0] if len(saved) == 1 else None
		source.update(suggested_box=box, classification_status=record.get("review_status") if record else "Pending Review",
			classification_id=record.name if record else None, origin=record.get("origin") if record else "System Derived",
			system_reason=reason, source_fingerprint=fingerprint(source))
		source["journal_treatment"] = record.get("journal_treatment") if record else source.get("journal_category")
		if record and record.approved:
			source["classification_status"] = "Needs Review"
		if record and record.get("requires_review"):
			source["requires_review"] = True
			source["review"] = record.get("source_review_reason") or "Source evidence requires renewed verification"


def manager_access(company):
	from construction_management.construction_management.report.uae_vat_201_return.engine import access, settings_for
	access(company)
	if not set(frappe.get_roles()) & {"Accounts Manager", "System Manager"}:
		frappe.throw(_("Only Accounts Managers may maintain VAT classifications"), frappe.PermissionError)
	doc = settings_for(company)
	if not doc.get("name"):
		frappe.throw(_("Configure UAE VAT Settings for this Company first"))
	doc.check_permission("write")
	return doc


@frappe.whitelist()
def sync_reviews(filters):
	from construction_management.construction_management.report.uae_vat_201_return.engine import build
	f = frappe._dict(frappe.parse_json(filters))
	doc = manager_access(f.company)
	result = build(f)
	existing = {(r.voucher_type, r.voucher_no, r.source_row): r for r in doc.custom_vat201_classifications}
	created = updated = 0
	for source in result["reviews"]:
		key = (source["voucher_type"], source["voucher_no"], source["source_row"])
		if key in existing:
			record = existing[key]
			if record.get("origin")=="System Derived" and not record.approved and record.get("review_status")!="Rejected" and not any(record.get(k) for k in ("reason","review_remarks","supporting_reference","recovery_confirmed","override_base")):
				if source["voucher_type"] in ("Journal Entry","Payment Entry") and not record.get("journal_treatment"):
					record.journal_treatment = "Unresolved"
					updated += 1
				if record.source_fingerprint != fingerprint(source) or record.system_reason != source["system_reason"]:
					record.source_fingerprint = fingerprint(source)
					record.source_evidence = frappe.as_json(source)
					record.system_reason = source["system_reason"]
					updated += 1
			continue
		doc.append("custom_vat201_classifications", dict(voucher_type=key[0], voucher_no=key[1], source_row=key[2],
			box=source.get("suggested_box"), tax_date=source["posting_date"], origin="System Derived", review_status="Pending Review",
			journal_treatment="Unresolved" if source["voucher_type"] in ("Journal Entry","Payment Entry") else None,
			system_reason=source["system_reason"], source_fingerprint=fingerprint(source),
			source_evidence=frappe.as_json(source), approved=0))
		existing[key] = doc.custom_vat201_classifications[-1]
		created += 1
	if created or updated:
		doc.save()
	return dict(created=created, updated=updated, pending=len(result["reviews"]))


@frappe.whitelist()
def review_source(filters, voucher_type, voucher_no, source_row, classification_id=None):
	from construction_management.construction_management.report.uae_vat_201_return.engine import build, settings_for
	result = build(filters)
	key = (voucher_type, voucher_no, source_row)
	sources = result["reviews"] + result["events"] + result.get("excluded", []) + result.get("timing_events", [])
	matching = [s for s in sources if tuple(s[k] for k in ("voucher_type", "voucher_no", "source_row")) == key]
	source = next((s for s in matching if s.get("classification_id")==classification_id), None) if classification_id else None
	source = source or next(iter(matching), None)
	if not source:
		frappe.throw(_("This source is outside the current permitted report scope"))
	doc = settings_for(result["filters"].company)
	records = [r.as_dict() for r in doc.custom_vat201_classifications if (r.voucher_type,r.voucher_no,r.source_row) == key]
	for record in records:
		# Return fresh permission-checked evidence, not historic manager-only snapshots.
		record.pop("source_evidence", None)
	return dict(source=source, records=records, decision_fingerprint=decision_fingerprint(source))


@frappe.whitelist()
def decide(filters, voucher_type, voucher_no, source_row, action, values=None, classification_id=None, expected_fingerprint=None):
	from construction_management.construction_management.report.uae_vat_201_return.engine import apply_rule
	f = frappe._dict(frappe.parse_json(filters))
	doc = manager_access(f.company)
	if action not in ("Save", "Approve", "Reject"):
		frappe.throw(_("Invalid VAT review action"))
	source = review_source(filters, voucher_type, voucher_no, source_row, classification_id)["source"]
	if expected_fingerprint and expected_fingerprint != decision_fingerprint(source):
		frappe.throw(_("Source evidence changed while the review dialog was open. Reload and review the current source."))
	record = next((r for r in doc.custom_vat201_classifications if r.name == classification_id and
		(r.voucher_type,r.voucher_no,r.source_row) == (voucher_type,voucher_no,source_row)), None)
	if classification_id and not record:
		frappe.throw(_("Classification does not belong to this source"))
	if not record:
		existing = [r for r in doc.custom_vat201_classifications if (r.voucher_type,r.voucher_no,r.source_row) == (voucher_type,voucher_no,source_row)]
		if existing and not classification_id:
			frappe.throw(_("Select the existing classification before saving this source decision"))
		record = doc.append("custom_vat201_classifications", dict(voucher_type=voucher_type,voucher_no=voucher_no,source_row=source_row,origin="Manual"))
	values = frappe._dict(frappe.parse_json(values) or {})
	allowed = ("box","tax_date","recovery_confirmed","recovery_percent","override_base","taxable_base_aed",
		"aed_exchange_rate","is_adjustment","adjustment_type","reason","supporting_reference","review_remarks","journal_treatment")
	for field in allowed:
		if field in values:
			record.set(field, values[field])
	if action == "Reject" and not record.get("review_remarks"):
		frappe.throw(_("Rejection requires review remarks; rejection does not exclude the source from reconciliation"))
	record.source_fingerprint = decision_fingerprint(source)
	record.source_evidence = frappe.as_json(source)
	record.approved = int(action == "Approve")
	record.review_status = "Approved" if record.approved else "Rejected" if action == "Reject" else "Pending Review"
	if record.approved:
		if not record.tax_date or not record.reason or not record.supporting_reference:
			frappe.throw(_("Approval requires tax date, reason and supporting evidence"))
		if source.get("tax_account") and record.box == "Outside VAT":
			from construction_management.construction_management.report.uae_vat_201_return.engine import account_mappings
			if source["tax_account"] in account_mappings(doc.uae_vat_accounts) and not control_movement_only(source,record):
				frappe.throw(_("A mapped VAT posting cannot be excluded as Outside VAT"))
		elif source.get("tax_account"):
			from construction_management.construction_management.report.uae_vat_201_return.engine import account_mappings, INPUT
			side = "Input" if record.box in INPUT else "Output"
			if account_mappings(doc.uae_vat_accounts).get(source["tax_account"]) not in (side,"Both"):
				frappe.throw(_("VAT account is not mapped for the selected VAT side"))
		candidate = frappe._dict(record.as_dict(), approved_by=frappe.session.user)
		_event, error = apply_rule(source, candidate, frappe.get_cached_value("Company", f.company, "default_currency"))
		if error:
			frappe.throw(_(error))
	doc.save()
	return dict(name=record.name, status=record.review_status)


@frappe.whitelist()
def fill_provisional_due_dates(company):
	doc = manager_access(company)
	changed = 0
	for period in doc.custom_vat201_periods:
		if period.due_date:
			continue
		period.due_date = add_days(getdate(period.to_date), 28)
		period.due_date_basis = "Provisional (28 days)"
		changed += 1
	if changed:
		doc.save()
	return dict(updated=changed)


@frappe.whitelist()
def set_return_status(filters, status, submission_date=None, filing_reference=None):
	from construction_management.construction_management.report.uae_vat_201_return.engine import normalize
	f = frappe._dict(frappe.parse_json(filters))
	doc = manager_access(f.company)
	if status not in ("Draft","Needs Review","Ready for Approval","Approved","Filed"):
		frappe.throw(_("Invalid VAT return status"))
	f = normalize(f, doc)
	period = next((p for p in doc.custom_vat201_periods if getdate(p.from_date)==f.from_date and getdate(p.to_date)==f.to_date), None)
	if not period:
		frappe.throw(_("Return status requires an exact configured filing period"))
	period.status = status
	if status == "Filed":
		period.submission_date, period.filing_reference = submission_date, filing_reference
	doc.save()
	return dict(status=period.status)
