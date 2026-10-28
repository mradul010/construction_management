"""Trace final return contributions to recorded VAT without altering entitlement."""
from collections import defaultdict

import frappe

from construction_management.construction_management.report.uae_vat_201_return import engine


def recovery_exclusions(result):
	seen, total = set(), engine.number(0)
	for row in result.get("details", []):
		key = tuple(row.get(key) for key in ("voucher_type","voucher_no","source_row"))
		if key in seen or row.get("currency") != "AED" or row.get("recorded_vat_amount") is None or row.get("recoverable_vat_amount") is None:
			continue
		seen.add(key)
		total += engine.number(row["recorded_vat_amount"]) - engine.number(row["recoverable_vat_amount"])
	return engine.money(total)


def explain(result):
	exclusions = recovery_exclusions(result)
	for row in result["reconciliation"]:
		if row["description"] == "Input VAT":
			row["explanation"] = "Saved/reviewed recovery exclusions: AED " + str(exclusions) + ". Recorded ledger VAT is not automatically recoverable. Unknown journal recovery and tax-date timing are separate; see the voucher/account reconciliation register."
		elif row["description"] == "Output VAT":
			row["explanation"] = "Known return subtotal versus recorded output VAT (credit minus debit). Unallocated output and tax-date differences remain separate; see voucher/account references."
		elif not row.get("explanation"):
			row["explanation"] = "Raw accounting movement is labelled debit minus credit and does not itself establish VAT-return treatment."
	if exclusions:
		result["warnings"].append("Recorded VAT excluded by saved/reviewed recovery decisions: AED " + str(exclusions) +
			". This is a recovery difference from recorded tax, not missing source VAT; see reconciliation.")
	return result


def apply(result, settings):
	if "ledger_entries" not in result:
		result["audit_rows"] = []
		return explain(result)
	mappings = engine.account_mappings(settings.get("uae_vat_accounts", []))
	sources = result.get("sources", [])
	by_gl = {(row["voucher_type"],row["voucher_no"],row["source_row"]):row for row in sources if "debit" in row}
	issues = {(row["voucher_type"],row["voucher_no"],row["source_row"]):row for row in result["reviews"]}
	excluded = {(row["voucher_type"],row["voucher_no"],row["source_row"]):row for row in result.get("excluded", [])}
	groups = defaultdict(lambda: dict(entries=[], sources=[], events=[], details=[]))
	for collection, field in ((result["ledger_entries"],"entries"),(sources,"sources"),(result["events"],"events"),(result["details"],"details")):
		for row in collection:
			account = row.get("tax_account") or row.get("account")
			if account:
				groups[(row["voucher_type"],row["voucher_no"],account)][field].append(row)
	rows = []
	totals = {key:engine.number(0) for key in ("Output","Input","Unallocated","Control")}
	available = {key:True for key in totals}
	for (doctype, voucher, account), group in sorted(groups.items()):
		if account not in mappings:
			continue
		rates = {event["aed_exchange_rate"] for event in group["events"] if event.get("aed_exchange_rate")}
		factor = engine.number(1) if result["header"]["base_currency"] == "AED" else engine.number(next(iter(rates))) if len(rates)==1 else None
		balances = {side:engine.number(0) for side in totals}
		debit = sum((engine.number(entry["debit"]) for entry in group["entries"]),engine.number(0))
		credit = sum((engine.number(entry["credit"]) for entry in group["entries"]),engine.number(0))
		for entry in group["entries"]:
			key = (doctype,voucher,entry["name"])
			if key in excluded:
				balances["Control"] += engine.number(entry["debit"])-engine.number(entry["credit"])
				continue
			source = by_gl.get(key, {})
			role = source.get("journal_vat_role")
			if role in ("Output","Input"):
				balances[role] += (engine.number(entry["credit"])-engine.number(entry["debit"])) * (1 if role=="Output" else -1)
			else:
				for side, amount in engine.ledger_sides(frappe._dict(entry),mappings,result.get("source_headers",{}),group["events"]):
					balances[side] += amount
		for side, value in balances.items():
			if factor is None and value:
				available[side] = False
			elif factor is not None:
				totals[side] += value*factor
		included = {}
		for side in ("Output", "Input"):
			included[side] = engine.money(sum(engine.number(event["vat_amount"]) + engine.number(event["adjustment"])
				for event in group["events"] if (event["box"] in engine.INPUT) == (side == "Input")))
		unresolved = [issues[(doctype,voucher,source["source_row"])] for source in group["sources"] if (doctype,voucher,source["source_row"]) in issues]
		posting_dates = sorted({str(row["posting_date"]) for row in group["sources"] if row.get("posting_date")})
		tax_dates = sorted({str(row["tax_date"]) for row in group["events"] if row.get("tax_date")})
		gl_refs = {entry["name"] for entry in group["entries"]}
		gl_refs.update(entry["name"] for source in group["sources"] for entry in source.get("gl_evidence", []))
		differences = {source.get("invoice_tax_difference") for source in group["sources"] if source.get("invoice_tax_difference") is not None}
		categories = sorted({source.get("journal_category") for source in group["sources"] if source.get("journal_category")})
		if any(source.get("journal_duplicate_risk") or source.get("journal_invoice_linked") for source in unresolved):
			categories.append("Duplicate-linked/settlement overlap excluded pending review")
		if any((doctype,voucher,source["source_row"]) in excluded for source in group["sources"]):
			categories.append("Documented settlement/transfer - no return claim")
		if tax_dates and (set(tax_dates)!=set(posting_dates)):
			categories.append("Tax-date/posting-date timing difference")
		if not differences and group["sources"] and all(source.get("generated_tax_rows") and not source.get("journal_match_issue") for source in group["sources"]):
			differences = {0}
		def converted(side):
			return engine.money(balances[side]*factor) if factor is not None else (0 if not balances[side] else None)
		rows.append(dict(voucher_type=doctype,voucher_no=voucher,vat_account=account,
			posting_dates=", ".join(posting_dates),tax_dates=", ".join(tax_dates),source_rows=", ".join(sorted({source["source_row"] for source in group["sources"]})),
			base_rows=", ".join(sorted({ref for source in group["sources"] for ref in source.get("base_row_references",[])})),
			gl_rows=", ".join(sorted(gl_refs)), raw_debit=float(debit),raw_credit=float(credit),raw_movement=float(debit-credit),raw_currency=result["header"]["base_currency"],
			recorded_output=converted("Output"),recorded_input=converted("Input"),unallocated_gl=converted("Unallocated"),control_movement=converted("Control"),
			claimed_output=included["Output"],claimed_input=included["Input"],known_nonclaimed=recovery_exclusions(dict(details=group["details"])),
			source_to_gl_difference=next(iter(differences)) if len(differences)==1 else None,
			category="; ".join(categories) or "Invoice VAT",
			issue="; ".join(sorted({source.get("issue", "Source evidence unresolved") for source in unresolved})),currency="AED"))
	boxes = {box["box"]:box for box in result["boxes"]}
	reconciliation = []
	for side, box in (("Output","12"),("Input","13")):
		ledger = engine.money(totals[side]) if available[side] else None
		reconciliation.append(dict(description=side+" VAT",report_amount=boxes[box]["amount"],ledger_amount=ledger,
			difference=engine.money(engine.number(boxes[box]["amount"])-engine.number(ledger)) if ledger is not None else None,currency="AED"))
	for side, label in (("Unallocated","Unallocated tax-account ledger (debit - credit)"),("Control","Documented settlements/transfers (debit - credit)")):
		reconciliation.append(dict(description=label,report_amount=None,ledger_amount=engine.money(totals[side]) if available[side] else None,difference=None,currency="AED"))
	reconciliation.append(dict(description="Mapped VAT control account movement (debit - credit)",report_amount=None,
		ledger_amount=result.get("control_movement"),difference=None,currency="AED"))
	result.update(audit_rows=rows,reconciliation=reconciliation)
	result["warnings"] = [warning for warning in result["warnings"] if "differs from the posting-date ledger" not in warning and "Tax-account postings remain unallocated" not in warning]
	for row in reconciliation[:2]:
		if row["difference"]:
			result["warnings"].append(row["description"] + " return-to-recorded-ledger difference AED " + str(row["difference"]) + "; see traceable recovery/allocation/timing explanations")
	if totals["Unallocated"] or not available["Unallocated"]:
		result["warnings"].append("Some VAT ledger treatment remains unallocated; see the voucher/account reconciliation register")
	return explain(result)
