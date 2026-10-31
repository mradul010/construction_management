"""Automatic source-based VAT preparation, without a classification workflow."""
from decimal import InvalidOperation
from collections import defaultdict

import frappe
from frappe.utils import flt
from frappe.utils import getdate

from construction_management.construction_management.report.uae_vat_201_return import engine


PRELIMINARY = "Calculated from saved ERPNext records - incomplete return allocation"


def standard_purchase(source):
	return source.get("voucher_type") == "Purchase Invoice" and source.get("reverse_charge") != "Y" and bool(source.get("raw_vat"))


def allocate_saved_recovery(sources):
	"""Allocate the one saved AED amount once across disjoint posted VAT rows."""
	groups = defaultdict(dict)
	for source in sources:
		if standard_purchase(source):
			groups[source["voucher_no"]][source["source_row"]] = source
	for rows in groups.values():
		rows = sorted(rows.values(), key=lambda row: row["source_row"])
		try:
			saved = rows[0].get("recovery_source_amount")
			if saved in (None, ""):
				raise ValueError("Saved purchase VAT recovery amount is missing")
			saved = engine.number(saved)
			vats = [engine.number(row["raw_vat"]) for row in rows]
			total = sum(vats, engine.number(0))
			if not saved.is_finite() or not all(v.is_finite() for v in vats) or not total:
				raise ValueError("Saved purchase VAT recovery amount or recorded VAT is invalid")
			if any(v * total < 0 for v in vats) or saved * total < 0 or abs(saved) > abs(total):
				raise ValueError("Saved purchase VAT recovery has an invalid sign, exceeds recorded VAT, or needs mixed-sign tax-row allocation")
			cumulative, allocated = engine.number(0), engine.number(0)
			for row, vat in zip(rows, vats):
				cumulative += vat
				next_amount = engine.number(engine.money(saved * cumulative / total))
				row["recovery_allocated_amount"] = next_amount - allocated
				allocated = next_amount
		except (InvalidOperation, ValueError, TypeError) as error:
			for row in rows:
				row["recovery_calculation_issue"] = str(error)
	for source in sources:
		if standard_purchase(source):
			resolved = groups[source["voucher_no"]][source["source_row"]]
			for field in ("recovery_allocated_amount", "recovery_calculation_issue"):
				if field in resolved:
					source[field] = resolved[field]


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
			if source.get("reverse_charge") == "Y" or source.get("potential_reverse_charge"):
				return None, "No recorded VAT: the saved reverse-charge selection or foreign supplier address requires review of the original supply/import and reverse-charge obligation"
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
			if base_currency != "AED":
				return None, "Saved recovery is AED; source taxable base and VAT require evidenced Company-to-AED conversion"
			if source.get("recovery_calculation_issue"):
				return None, source["recovery_calculation_issue"]
			value = source.get("recovery_allocated_amount", source.get("recovery_source_amount"))
			if value in (None, ""):
				return None, "Purchase VAT recoverable amount is missing"
			try:
				amount = engine.number(value)
			except (InvalidOperation, ValueError, TypeError):
				return None, "Purchase VAT recoverable amount is invalid"
			vat = engine.number(source.get("raw_vat"))
			if not amount.is_finite() or not vat.is_finite() or not vat or amount * vat < 0 or abs(amount) > abs(vat):
				return None, "Purchase VAT recoverable amount must have the saved VAT sign and cannot exceed recorded VAT"
			if amount == 0:
				return None, None
			if source.get("vat_rows_count") != 1 and "recovery_allocated_amount" not in source:
				return None, "Purchase VAT recovery amount needs allocation across multiple VAT rows"
			recovery = amount / vat * 100
			evidence = "Saved recoverable_standard_rated_expenses on " + source["voucher_no"]
			box = "9"
	else:
		if dt == "Journal Entry":
			if source.get("journal_category") == "Customer-advance output VAT":
				if source.get("journal_duplicate_risk"):
					return None, source["journal_duplicate_risk"]
				box, error = sales_emirate_box(source)
				if error:
					return None, "Customer-advance output VAT: reporting VAT Emirate is missing or invalid on the transaction or an authoritative linked document"
				if flt(source.get("tax_rate")) != 5:
					return None, "Customer-advance output VAT rate does not establish standard-rated Emirate reporting"
				evidence = "Saved customer-advance base/generated VAT/receivable reconciliation: " + source["base_row_reference"]
			elif source.get("journal_invoice_linked"):
				return None, "Invoice-linked journal VAT is not an additional expense claim; verify settlement or duplicate invoice VAT"
			elif source.get("journal_match_issue"):
				return None, source["journal_match_issue"]
			elif source.get("journal_category") == "Recorded purchase VAT":
				return None, "Recorded purchase VAT reconciles to saved expense and generated tax rows; recovery entitlement is not configured"
			else:
				return None, "VAT journal purpose and tax treatment cannot be established from sufficient linked evidence"
		else:
			return None, "VAT journal purpose and tax treatment cannot be established from sufficient linked evidence"
	if base_currency != "AED":
		return None, "AED tax-point exchange evidence is required; Company base amounts are not AED"
	if source.get("base") is None:
		return None, "Saved taxable base requires allocation; VAT is not divided by 5% to invent it"
	return frappe._dict(box=box, tax_date=source["posting_date"],
		reason="Customer-advance output VAT" if dt=="Journal Entry" else "Saved invoice tax treatment", supporting_reference=evidence,
		recovery_confirmed=int(recovery is not None), recovery_percent=recovery or 0, override_base=0,
		is_adjustment=0), None


def build(filters=None, settings_override=None):
	# The existing reader enforces source permissions, dates, signs and active GL.
	# Existing valid verified decisions remain usable; no review rows are written.
	result = engine.build(filters, settings_override=settings_override)
	# Saved source recovery supersedes historical report-only purchase approvals.
	# Keep those audit records intact; only replace their calculated contributions.
	if "sources" in result:
		for field in ("events", "reviews", "excluded", "timing_events"):
			result[field] = [row for row in result.get(field, []) if not standard_purchase(row)]
		result["reviews"].extend(dict(row) for row in result["sources"] if standard_purchase(row)
			and getdate(result["filters"].from_date) <= getdate(row["posting_date"]) <= getdate(result["filters"].to_date))
	settings = settings_override if settings_override is not None else engine.settings_for(result["filters"].company)
	result["settings_name"] = settings.get("name")
	result["calculated_at"] = str(frappe.utils.now_datetime())
	mappings = engine.account_mappings(settings.get("uae_vat_accounts", []))
	allocate_saved_recovery([row for row in result["reviews"] if mappings.get(row.get("tax_account")) in ("Input", "Both")])
	events = []
	issues, details = [], []
	# Saved invoice Emirate also governs any retained historical standard-rated event.
	for event in result["events"]:
		event = dict(event)
		event["treatment_source"] = "Manual approved override"
		if event["voucher_type"] == "Purchase Invoice" and event["box"] == "9" and not event.get("adjustment"):
			# engine events have passed approval, fingerprint and recovery checks.
			# Do not overwrite an approved allocation with a default invoice zero.
			event["treatment"] = "Standard-rated purchase"
		if event.get("recoverable_vat_amount") == 0 and event.get("box") in engine.INPUT:
			details.append(dict(event, vat_box="", treatment="Verified non-recoverable VAT", recovery_status="Verified non-recoverable"))
			continue
		if event["voucher_type"] in ("Sales Invoice", "POS Invoice") and event["box"] in engine.OUTPUT[:7]:
			box, error = sales_emirate_box(event)
			if error:
				issues.append(dict(event, issue=error, recommended_action=action_for(event), treatment="Recorded sales VAT", vat_box=None))
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
		if not standard_purchase(source) and (source.get("classification_status") in ("Rejected", "Needs Review") or source.get("requires_review") or source.get("review", "").startswith(("Duplicated", "Source evidence changed", "Outside VAT exclusion conflicts"))):
			rule, problem = None, "Previous source verification is rejected, conflicting or no longer valid; verify source evidence"
			events = [e for e in events if tuple(e[k] for k in ("voucher_type", "voucher_no", "source_row")) != key]
		else:
			if source.get("journal_category") == "Recorded purchase VAT":
				from construction_management.construction_management.report.uae_vat_201_return.policy import resolve
				rule, problem = resolve(source, settings, result["header"]["base_currency"])
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
					if calculation_rule.get("treatment_source"):
						event.update(treatment_source=calculation_rule.treatment_source, policy_id=calculation_rule.get("policy_id"),
							policy_name=calculation_rule.get("policy_name"), policy_approved_by=calculation_rule.get("policy_approved_by"),
							policy_approval_time=calculation_rule.get("policy_approval_time"),
							recovery_basis=("Policy: " + calculation_rule.policy_name + " (" + calculation_rule.policy_id + ")") if calculation_rule.get("policy_id") else "Saved explicit invoice recovery amount (AED)",
							treatment="Policy-derived purchase recovery" if calculation_rule.get("policy_id") else "Saved source recovery decision")
						if not event["recoverable_vat_amount"]:
							details.append(dict(event, vat_box="", treatment="Policy-derived non-recoverable VAT"))
							continue
						calculated.append(event)
						continue
					if calculation_rule.box in engine.INPUT:
						if source.get("reverse_charge") == "Y":
							basis = "Saved Recoverable Reverse Charge (%): " + str(source.get("reverse_recovery_percent"))
						else:
							basis = "Saved Recoverable Standard Rated Expenses (AED): " + str(engine.money(source.get("recovery_source_amount")))
						event["recovery_basis"] = basis
						event["treatment"] = "Reverse-charge purchase" if source.get("reverse_charge") == "Y" else "Standard-rated purchase"
						if standard_purchase(source):
							event["treatment_source"] = "Saved source recovery amount"
					elif calculation_rule.box == "3":
						event["treatment"] = "Recorded reverse-charge output VAT; input recovery does not reduce output liability"
					else:
						event["treatment"] = "Customer-advance output VAT" if source.get("journal_vat_role") == "Output" else "Saved sales VAT Emirate and tax row" if calculation_rule.box in engine.OUTPUT[:7] else "Saved source-item " + str(source.get("treatment_hint") or "VAT treatment")
					calculated.append(event)
				if not problem:
					events.extend(calculated)
		if problem:
			row.update(issue=problem, recommended_action=action_for(row), treatment="Recorded source transaction")
			if row.get("journal_category") == "Recorded purchase VAT":
				row["treatment"] = "Recorded expense JV VAT"
			elif row.get("journal_category") == "Customer-advance output VAT":
				row["treatment"] = "Customer-advance output VAT"
			elif row.get("potential_reverse_charge") and not row.get("tax_account") and not row.get("raw_vat"):
				row["treatment"] = "No recorded VAT - supply/import treatment requires review"
			issues.append(row)
		elif not rule:
			if is_zero_claim(source):
				details.append(zero_claim_detail(row))
				continue
			treatment = source.get("treatment_hint")
			row.update(treatment=(treatment + " purchase - no input claim") if treatment in ("Zero Rated", "Exempt") else "No recorded VAT - no input claim", vat_amount=0)
			details.append(row)
	for event in events:
		event["treatment"] = transaction_label(event)
		details.append(dict(event, vat_box=event["box"], treatment=event.get("treatment") or event.get("recovery_basis") or "Preserved verified source treatment"))
	for excluded in result.get("excluded", []):
		details.append(dict(excluded, vat_box=None, treatment="Documented non-return movement"))
	for event in result.get("timing_events", []):
		details.append(dict(event, vat_box="", treatment="Approved tax-date timing difference - outside this return period",
			remarks="Approved tax/reporting date: " + str(event.get("tax_date")) + "; not included in this period's claim"))
	details.extend(issues)
	for row in details:
		if row.get("recoverable_vat_amount") is not None:
			full = engine.number(row.get("recorded_vat_amount"))
			claim = engine.number(row["recoverable_vat_amount"])
			row["recovery_status"] = ("Policy-derived zero" if not claim else "Policy-derived full" if claim == full else "Policy-derived partial") if row.get("policy_id") else ("Saved source zero" if not claim else "Saved source full" if claim == full else "Saved source partial") if row.get("treatment_source") == "Saved source recovery amount" else "Verified non-recoverable" if not claim else "Verified fully recoverable" if claim == full else "Verified partially recoverable"
		elif row.get("journal_vat_role") == "Input" or row["voucher_type"] == "Purchase Invoice" and row.get("raw_vat"):
			row["recovery_status"] = "Not specified in source"
		elif row["voucher_type"] == "Purchase Invoice":
			row["recovery_status"] = "No recorded VAT"
		row["treatment"] = transaction_label(row)
		if row.get("issue") and row.get("journal_vat_role") == "Output" and not row.get("journal_duplicate_risk") and row.get("source_emirate") not in engine.get_emirates():
			row["issue"] = "Output not allocated to an Emirate"
		if row.get("potential_reverse_charge") and not row.get("raw_vat"):
			row["issue"] = "No recorded VAT; import/reverse-charge treatment is not established in source."
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
	# A recorded-versus-claim difference is expected for saved partial/zero recovery;
	# the linked bridge explains it without turning it into a recovery exception.
	result.update(events=events, boxes=list(boxes.values()), reviews=issues, details=details, warnings=warnings)
	from construction_management.construction_management.report.uae_vat_201_return import reconciliation, calendar
	reconciliation.apply(result, settings)
	from construction_management.construction_management.report.uae_vat_201_return.completeness import apply
	apply(result, settings)
	result["calendar_issues"] = calendar.validate(result["header"], settings) if result["header"].get("from_date") else []
	result["warnings"].extend(result["calendar_issues"])
	result["warnings"] = list(dict.fromkeys(result["warnings"]))
	groups = {}
	for source in issues:
		key = (source["issue"], source.get("recommended_action"))
		group = groups.setdefault(key, dict(issue=key[0], action=key[1], count=0, vouchers=set()))
		group["count"] += 1
		group["vouchers"].add(source["voucher_no"])
	result["review_summary"] = [dict(group, vouchers=sorted(group["vouchers"])) for group in groups.values()]
	result["calculation_description"] = "Calculated from saved ERPNext records"
	result["return_complete"] = not issues and not result.get("scope_incomplete") and not result["warnings"]
	result["status"] = PRELIMINARY if not result["return_complete"] else result["calculation_description"]
	return result


def transaction_label(row):
	if row.get("journal_category") == "Recorded purchase VAT":
		return "Recorded expense JV VAT"
	if row.get("journal_category") == "Customer-advance output VAT":
		return "Customer-advance output VAT"
	if row["voucher_type"] == "Purchase Invoice":
		if row.get("is_return") or engine.number(row.get("raw_vat")) < 0:
			return "Purchase return"
		if not row.get("raw_vat"):
			return "No recorded VAT"
		return "Saved recoverable input VAT" if row.get("recoverable_vat_amount") else "Recorded standard-rated purchase"
	return row.get("treatment") or "Recorded source transaction"


def is_zero_claim(source):
	return (source.get("voucher_type") == "Purchase Invoice" and source.get("reverse_charge") != "Y"
		and source.get("recovery_allocated_amount", source.get("recovery_source_amount")) not in (None, "")
		and engine.number(source.get("recovery_allocated_amount", source.get("recovery_source_amount"))) == 0 and bool(source.get("raw_vat")))


def zero_claim_detail(source):
	return dict(source, box=None, vat_box=None, amount=0, vat_amount=0, adjustment=0,
		invoice_taxable_amount=source.get("invoice_taxable_amount", source.get("base")),
		recorded_vat_amount=source.get("recorded_vat_amount", source.get("raw_vat")),
		recoverable_vat_amount=0, treatment="No input VAT claimed",
		treatment_source="Saved source recovery amount",
		recovery_basis="Saved Recoverable Standard Rated Expenses (AED): " + str(engine.money(source.get("recovery_source_amount"))))


def detail_remarks(row):
	parts = [row.get("remarks") or (row.get("reason") if row.get("recoverable_vat_amount") is None else "") or ""]
	if row.get("voucher_type") == "Journal Entry" and row.get("journal_category") == "Recorded purchase VAT":
		parts.extend(["Project: " + str(row.get("project") or "not saved"),
			"Cost Center: " + str(row.get("cost_center") or "not saved")])
		if row.get("journal_expense_accounts"):
			parts.append("Expense: " + ", ".join(row["journal_expense_accounts"]))
		if row.get("journal_grouped_allocation"):
			parts.append("Reconciled group total; no one-to-one expense/tax allocation asserted")
	if row.get("voucher_type") == "Purchase Invoice":
		parts = ["Supplier invoice: {}; Bill date: {}".format(row.get("bill_no") or "not saved", row.get("bill_date") or "not saved")]
		trn = str(row.get("source_tax_id") or "").strip()
		if len(trn) != 15 or not trn.isdigit():
			parts.append("Source quality: supplier TRN is missing or invalid (saved recovery unchanged)")
	if row.get("journal_source_note"):
		parts.append(row["journal_source_note"])
	if row.get("issue"):
		parts.append(row["issue"])
	elif row.get("recoverable_vat_amount") is not None:
		claim = engine.money(row["recoverable_vat_amount"])
		basis = row.get("recovery_basis") or "Reviewed recovery allocation"
		if "Saved Recoverable Standard Rated Expenses" in basis:
			basis = "saved invoice recovery amount"
		parts.append("Recoverable VAT: AED {:.2f}; {}".format(claim, basis))
		if row.get("recorded_vat_amount") is not None:
			parts.append("Recorded VAT not claimed: AED {:.2f}".format(engine.money(engine.number(row["recorded_vat_amount"]) - engine.number(claim))))
	return "; ".join(part for part in parts if part)


def action_for(source):
	if source.get("journal_category") == "Customer-advance output VAT":
		return "Review the saved transaction/explicitly linked tax document for the reporting VAT Emirate and any invoice or advance-adjustment overlap; cheque text, Customer address and project name are not authoritative links"
	if source["voucher_type"] in ("Sales Invoice","POS Invoice"):
		return "Check the saved VAT Emirate on the source invoice and select a valid UAE Emirate when Emirate classification is required; review any other source issue shown"
	if source["voucher_type"]=="Purchase Invoice":
		if source.get("potential_reverse_charge") and not source.get("tax_account") and not source.get("raw_vat"):
			return "Review the original supplier tax invoice, nature/place of supply and customs/import evidence to establish any output VAT obligation before considering input recovery; foreign address alone does not decide the treatment"
		return "Review the saved Recoverable Standard Rated Expenses (AED), tax rows and accounting evidence; recorded VAT alone does not establish entitlement"
	if source.get("journal_category") == "Recorded purchase VAT":
		return "Saved expense, generated tax and GL rows establish recorded VAT, not recovery entitlement."
	return "Check original journal links, advance tax invoice/payment evidence and purpose; exclude settlements only with supporting evidence"
