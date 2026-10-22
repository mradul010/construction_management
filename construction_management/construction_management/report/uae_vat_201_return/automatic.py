"""Automatic source-based VAT preparation, without a classification workflow."""
import frappe
from frappe.utils import flt

from construction_management.construction_management.report.uae_vat_201_return import engine


PRELIMINARY = "PRELIMINARY - VERIFICATION REQUIRED"


def source_rule(source, base_currency):
	"""Return a calculation adapter only when source evidence establishes treatment."""
	dt = source["voucher_type"]
	box, recovery = None, None
	evidence = (source.get("verification_reference") or "").strip()
	if source.get("invoice_tax_difference") and source.get("reverse_charge") != "Y":
		return None, "Saved invoice VAT differs from active GL postings"
	if dt in ("Sales Invoice", "POS Invoice"):
		if source.get("treatment_hint") in ("Zero Rated", "Exempt") and not source.get("raw_vat"):
			box = "4" if source["treatment_hint"] == "Zero Rated" else "5"
			evidence = "Explicit saved source-item tax treatment: " + source["source_row"]
		elif source.get("tax_account") and flt(source.get("tax_rate")) == 5:
			emirate = source.get("verified_supply_emirate")
			if not (source.get("supply_verified") and evidence):
				# A field populated from company address is not transaction-specific evidence.
				meta = frappe.get_meta(dt).get_field("vat_emirate")
				if meta and not meta.fetch_from:
					emirate = source.get("source_emirate")
					evidence = "Saved transaction VAT Emirate: " + source["voucher_no"]
				else:
					return None, "Sales Emirate cannot be verified: saved VAT Emirate is company-address-derived"
			if emirate not in engine.get_emirates():
				return None, "Transaction-specific supply Emirate is missing or invalid"
			box = "1" + chr(97 + engine.get_emirates().index(emirate))
		else:
			return None, "Sales tax treatment is not supported by saved tax rows or explicit item flags"
	elif dt == "Purchase Invoice":
		if not source.get("tax_account") and not source.get("raw_vat"):
			return None, None  # No recorded input VAT; do not invent zero/exempt treatment.
		if source.get("recovery_verified") and evidence:
			recovery = flt(source.get("verified_recovery_percent"))
			if not 0 <= recovery <= 100:
				return None, "Documented recovery percentage is outside 0 to 100"
		else:
			# ERPNext's standard field records the recoverable VAT amount, not an expense base.
			amount = engine.number(source.get("recovery_source_amount"))
			vat = engine.number(source.get("raw_vat"))
			if not amount or not vat or amount * vat < 0 or abs(amount) > abs(vat) or source.get("vat_rows_count") != 1:
				return None, "Purchase VAT recovery entitlement is not established by saved recovery information"
			recovery = amount / vat * 100
			evidence = "Saved recoverable_standard_rated_expenses on " + source["voucher_no"]
		box = "9"
		if source.get("reverse_charge") == "Y":
			if not source.get("recovery_verified") or not source.get("verification_reference"):
				return None, "Reverse-charge VAT requires documented recovery; default percentages are not proof"
			vat = abs(engine.number(source.get("raw_vat")))
			gl_rows = source.get("gl_evidence", [])
			debits = sum((engine.number(g["debit"]) for g in gl_rows), engine.number(0))
			credits = sum((engine.number(g["credit"]) for g in gl_rows), engine.number(0))
			if not vat or source.get("vat_rows_count") != 1 or engine.money(debits-vat) or engine.money(credits-vat):
				return None, "Reverse-charge input and output GL evidence does not match the saved tax row"
			box = "3"
	else:
		return None, "VAT journal purpose and tax treatment cannot be established from sufficient linked evidence"
	if base_currency != "AED":
		return None, "AED tax-point exchange evidence is required; Company base amounts are not AED"
	if source.get("base") is None:
		return None, "Saved taxable base requires allocation; VAT is not divided by 5% to invent it"
	return frappe._dict(box=box, tax_date=source["posting_date"],
		reason="Automatic treatment from saved source evidence", supporting_reference=evidence,
		recovery_confirmed=int(recovery is not None), recovery_percent=recovery or 0, override_base=0,
		is_adjustment=0), None


def build(filters=None):
	# The existing reader enforces source permissions, dates, signs and active GL.
	# Existing valid verified decisions remain usable; no review rows are written.
	result = engine.build(filters)
	settings = engine.settings_for(result["filters"].company)
	mappings = engine.account_mappings(settings.get("uae_vat_accounts", []))
	events = list(result["events"])
	issues, details = [], []
	seen = set()
	for source in result["reviews"]:
		key = tuple(source[k] for k in ("voucher_type", "voucher_no", "source_row"))
		if key in seen:
			continue
		seen.add(key)
		row = dict(source, currency=result["header"]["base_currency"], vat_box=None)
		if source.get("classification_status") in ("Rejected", "Needs Review") or source.get("requires_review") or source.get("review", "").startswith(("Duplicated", "Source evidence changed", "Outside VAT exclusion conflicts")):
			rule, problem = None, "Previous source verification is rejected, conflicting or no longer valid; verify source evidence"
			events = [e for e in events if tuple(e[k] for k in ("voucher_type", "voucher_no", "source_row")) != key]
		else:
			rule, problem = source_rule(source, result["header"]["base_currency"])
		if rule:
			side = "Input" if rule.box in engine.INPUT else "Output"
			if source.get("tax_account") and mappings.get(source["tax_account"]) not in (side,"Both"):
				problem = "VAT account is not mapped for this source's VAT side"
			else:
				calculation_rules = [rule]
				if rule.box == "3":
					calculation_rules.append(frappe._dict(dict(rule, box="10")))
				calculated = []
				for calculation_rule in calculation_rules:
					calculation_side = "Input" if calculation_rule.box in engine.INPUT else "Output"
					if source.get("tax_account") and mappings.get(source["tax_account"]) not in (calculation_side, "Both"):
						problem = "VAT account is not mapped for both reverse-charge sides"
						break
					event, problem = engine.apply_rule(source, calculation_rule, result["header"]["base_currency"], source_verified=True)
					if problem:
						break
					event["treatment"] = "Automatic source evidence"
					calculated.append(event)
				if not problem:
					events.extend(calculated)
		if problem:
			row.update(issue=problem, recommended_action=action_for(row), treatment="Needs Attention")
			issues.append(row)
		elif not rule:
			treatment = source.get("treatment_hint")
			row.update(treatment=(treatment + " purchase - no input claim") if treatment in ("Zero Rated", "Exempt") else "No recorded VAT - no input claim", vat_amount=0)
			details.append(row)
	for event in events:
		details.append(dict(event, vat_box=event["box"], treatment=event.get("treatment") or "Preserved verified source treatment"))
	for excluded in result.get("excluded", []):
		details.append(dict(excluded, vat_box=None, treatment="Documented non-return movement"))
	details.extend(issues)
	boxes = engine.aggregate(events)
	for rec in result["reconciliation"]:
		key = "12" if rec["description"]=="Output VAT" else "13" if rec["description"]=="Input VAT" else None
		if key:
			rec["report_amount"] = boxes[key]["amount"]
			rec["difference"] = engine.money(engine.number(rec["report_amount"])-engine.number(rec["ledger_amount"])) if rec["ledger_amount"] is not None else None
	# Remove obsolete workflow warnings; retain configuration, ledger and permissions issues.
	warnings = [w for w in result["warnings"] if not any(text in w for text in (
		"classification review", "Unapproved sources", "VAT differs from the posting-date ledger"))]
	if issues:
		warnings.append(f"{len(issues)} source rows need attention. Uncertain tax is excluded from payable calculation; this is not a nil return.")
	for rec in result["reconciliation"][:2]:
		if rec["difference"]:
			warnings.append(rec["description"]+" differs from the posting-date ledger; see Needs Attention and recovery/timing evidence")
	result.update(events=events, boxes=list(boxes.values()), reviews=issues, details=details,
		warnings=warnings, status=PRELIMINARY if issues or warnings else "Prepared - Not Filed")
	return result


def action_for(source):
	if source["voucher_type"] in ("Sales Invoice","POS Invoice"):
		return "Verify the supply-specific Emirate/tax point and record evidence at the source; do not use company address alone"
	if source["voucher_type"]=="Purchase Invoice":
		return "Verify original tax invoice and recovery eligibility; maintain the valid source recovery amount or documented recovery verification"
	return "Check original journal links, advance tax invoice/payment evidence and purpose; exclude settlements only with supporting evidence"
