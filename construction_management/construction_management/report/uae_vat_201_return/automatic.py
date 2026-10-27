"""Automatic source-based VAT preparation, without a classification workflow."""
from decimal import InvalidOperation

import frappe
from frappe.utils import flt

from construction_management.construction_management.report.uae_vat_201_return import engine


PRELIMINARY = "PRELIMINARY - VERIFICATION REQUIRED"


def sales_emirate_box(source):
	emirate = source.get("source_emirate")
	if emirate not in engine.get_emirates():
		return None, "VAT Emirate is missing or invalid"
	return "1" + chr(97 + engine.get_emirates().index(emirate)), None


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
			box, error = sales_emirate_box(source)
			if error:
				return None, error
			evidence = "Saved transaction VAT Emirate: " + source["voucher_no"]
		else:
			return None, "Sales tax treatment is not supported by saved tax rows or explicit item flags"
	elif dt == "Purchase Invoice":
		if not source.get("tax_account") and not source.get("raw_vat"):
			return None, None  # No recorded input VAT; do not invent zero/exempt treatment.
		if source.get("reverse_charge") == "Y":
			percent = source.get("reverse_recovery_percent")
			if percent in (None, ""):
				return None, "Reverse-charge recovery percentage is missing"
			try:
				recovery = engine.number(percent)
			except (InvalidOperation, ValueError, TypeError):
				return None, "Reverse-charge recovery percentage is invalid"
			if not recovery.is_finite() or not 0 <= recovery <= 100:
				return None, "Reverse-charge recovery percentage is outside 0 to 100"
			evidence = "Saved recoverable_reverse_charge on " + source["voucher_no"]
			vat = abs(engine.number(source.get("raw_vat")))
			gl_rows = source.get("gl_evidence", [])
			debits = sum((engine.number(g["debit"]) for g in gl_rows), engine.number(0))
			credits = sum((engine.number(g["credit"]) for g in gl_rows), engine.number(0))
			if not vat or source.get("vat_rows_count") != 1 or engine.money(debits-vat) or engine.money(credits-vat):
				return None, "Reverse-charge input and output GL evidence does not match the saved tax row"
			box = "3"
		else:
			# This standard Currency field contains recoverable VAT in AED, not a % or flag.
			value = source.get("recovery_source_amount")
			if value in (None, ""):
				return None, "Purchase VAT recoverable amount is missing"
			try:
				amount = engine.number(value)
			except (InvalidOperation, ValueError, TypeError):
				return None, "Purchase VAT recoverable amount is invalid"
			vat = engine.number(source.get("raw_vat"))
			if not amount.is_finite() or not vat.is_finite() or not vat or amount * vat < 0 or abs(amount) > abs(vat):
				return None, "Purchase VAT recoverable amount must have the saved VAT sign and cannot exceed recorded VAT"
			if amount == 0 and not source.get("zero_recovery_decision"):
				return None, "Purchase recovery configuration is incomplete: the UAE recovery amount is default zero; eligible recovery or an intentional zero decision has not been recorded"
			if source.get("vat_rows_count") != 1:
				return None, "Purchase VAT recovery amount needs allocation across multiple VAT rows"
			recovery = amount / vat * 100
			evidence = "Saved recoverable_standard_rated_expenses on " + source["voucher_no"]
			box = "9"
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
	events = []
	issues, details = [], []
	# Saved invoice Emirate also governs any retained historical standard-rated event.
	for event in result["events"]:
		event = dict(event)
		if event["voucher_type"] in ("Sales Invoice", "POS Invoice") and event["box"] in engine.OUTPUT[:7]:
			box, error = sales_emirate_box(event)
			if error:
				issues.append(dict(event, issue=error, recommended_action=action_for(event), treatment="Needs Attention", vat_box=None))
				continue
			event.update(box=box, emirate=event["source_emirate"], classification=engine.LABELS[box])
		events.append(event)
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
					if calculation_rule.box in engine.INPUT:
						if source.get("reverse_charge") == "Y":
							basis = "Saved Recoverable Reverse Charge (%): " + str(source.get("reverse_recovery_percent"))
						else:
							basis = "Saved Recoverable Standard Rated Expenses (AED): " + str(engine.money(source.get("recovery_source_amount")))
						event["recovery_basis"] = basis
						event["treatment"] = "Reverse-charge purchase" if source.get("reverse_charge") == "Y" else "Standard-rated purchase"
					elif calculation_rule.box == "3":
						event["treatment"] = "Recorded reverse-charge output VAT; input recovery does not reduce output liability"
					else:
						event["treatment"] = "Saved sales VAT Emirate and tax row" if calculation_rule.box in engine.OUTPUT[:7] else "Saved source-item " + str(source.get("treatment_hint") or "VAT treatment")
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
		details.append(dict(event, vat_box=event["box"], treatment=event.get("treatment") or event.get("recovery_basis") or "Preserved verified source treatment"))
	for excluded in result.get("excluded", []):
		details.append(dict(excluded, vat_box=None, treatment="Documented non-return movement"))
	details.extend(issues)
	for row in details:
		row["display_remarks"] = detail_remarks(row)
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


def detail_remarks(row):
	parts = [row.get("remarks") or (row.get("reason") if row.get("recoverable_vat_amount") is None else "") or ""]
	if row.get("issue"):
		parts.append(row["issue"])
	elif row.get("recoverable_vat_amount") is not None:
		claim = engine.money(row["recoverable_vat_amount"])
		parts.append("Recoverable VAT: AED {:.2f}. {}".format(claim, row.get("recovery_basis") or "Reviewed recovery allocation"))
	return "; ".join(part for part in parts if part)


def action_for(source):
	if source["voucher_type"] in ("Sales Invoice","POS Invoice"):
		return "Check the saved VAT Emirate on the source invoice and select a valid UAE Emirate when Emirate classification is required; review any other source issue shown"
	if source["voucher_type"]=="Purchase Invoice":
		return "An Accounts Manager must determine eligibility from the original tax invoice and populate Recoverable Standard Rated Expenses (AED) with the eligible VAT amount, or record intentional zero recovery and its reason through Update VAT Recovery. Recorded VAT alone does not establish entitlement"
	return "Check original journal links, advance tax invoice/payment evidence and purpose; exclude settlements only with supporting evidence"
