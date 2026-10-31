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
	return result


def apply(result, settings):
	if "ledger_entries" not in result:
		result["audit_rows"] = []
		return explain(result)
	mappings = engine.account_mappings(settings.get("uae_vat_accounts", []))
	sources = result.get("sources", [])
	by_gl = {(row["voucher_type"],row["voucher_no"],row["source_row"]):row for row in sources if "debit" in row}
	for source in sources:
		for gl_row in source.get("journal_group_gl_rows", []):
			by_gl[(source["voucher_type"],source["voucher_no"],gl_row)] = source
	issues = {(row["voucher_type"],row["voucher_no"],row["source_row"]):row for row in result["reviews"]}
	excluded = {(row["voucher_type"],row["voucher_no"],row["source_row"]):row for row in result.get("excluded", [])}
	groups = defaultdict(lambda: dict(entries=[], sources=[], events=[], details=[], timing=[]))
	for collection, field in ((result["ledger_entries"],"entries"),(sources,"sources"),(result["events"],"events"),(result["details"],"details"),(result.get("timing_events",[]),"timing")):
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
		rates = {event["aed_exchange_rate"] for event in group["events"] + group["timing"] if event.get("aed_exchange_rate")}
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
		tax_dates = sorted({str(row["tax_date"]) for row in group["events"] + group["timing"] if row.get("tax_date")})
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
	bridge(result)
	for side, description in (("input", "Recovery not specified in source."), ("output", "Output not allocated to an Emirate")):
		selected = [source for source in result["reviews"] if source.get("issue") == description]
		if selected:
			values = [source.get("recorded_vat_amount") for source in selected]
			amount = engine.money(sum(engine.number(value) for value in values)) if all(value is not None for value in values) else None
			reconciliation.append(dict(description=description, report_amount=None, ledger_amount=amount,
				difference=None, currency="AED", explanation="; ".join(sorted({source["voucher_no"] for source in selected}))))
	result["warnings"] = [warning for warning in result["warnings"] if "differs from the posting-date ledger" not in warning and "Tax-account postings remain unallocated" not in warning]
	for row in reconciliation[:2]:
		if row["difference"] and any(result.get("tax_measures",{}).get(field) for field in ("pending_output","pending_input","residual_output","residual_input")):
			result["warnings"].append(row["description"] + " return-to-recorded-ledger difference AED " + str(row["difference"]) + "; see traceable recovery/allocation/timing explanations")
	if totals["Unallocated"] or not available["Unallocated"]:
		result["warnings"].append("Some VAT ledger treatment remains unallocated; see the voucher/account reconciliation register")
	return explain(result)


def bridge(result):
	"""Partition recorded tax once into return, pending, exclusion and timing."""
	reviews = {(r["voucher_type"], r["voucher_no"], r["source_row"]): r for r in result["reviews"]}
	breakdown = defaultdict(lambda: defaultdict(lambda: engine.number(0)))
	for row in result["audit_rows"]:
		key = (row["voucher_type"], row["voucher_no"], row["vat_account"])
		pending = {"output": engine.number(0), "input": engine.number(0)}
		seen = set()
		for source in result.get("sources", []):
			identity = (source["voucher_type"], source["voucher_no"], source["source_row"])
			if identity in seen or identity not in reviews or (identity[0], identity[1], source.get("tax_account")) != key:
				continue
			seen.add(identity)
			side = "output" if source.get("journal_vat_role") == "Output" or identity[0] in ("Sales Invoice", "POS Invoice") else "input" if source.get("journal_vat_role") == "Input" or identity[0] == "Purchase Invoice" else None
			if side and result["header"]["base_currency"] == "AED":
				value = source.get("recorded_vat_amount")
				if value is None:
					value = engine.number(source.get("raw_vat")) * (-1 if side == "output" and "debit" in source else 1)
				pending[side] += engine.number(value)
		for side in ("output", "input"):
			recorded = row["recorded_" + side]
			claimed = row["claimed_" + side]
			nonclaimed = row["known_nonclaimed"] if side == "input" else 0
			row["pending_" + side] = engine.money(pending[side]) if recorded is not None else None
			remaining = engine.number(recorded) - engine.number(claimed) - engine.number(nonclaimed) - pending[side] if recorded is not None else None
			timing = remaining if "timing difference" in row["category"] and not row["issue"] else engine.number(0)
			row["timing_" + side] = engine.money(timing) if timing is not None else None
			row["residual_" + side] = engine.money(remaining - timing) if remaining is not None else None
		row["classification_difference"] = engine.money(engine.number(row["raw_credit"]) - engine.number(row["raw_debit"]) -
			engine.number(row["recorded_output"]) + engine.number(row["recorded_input"]) + engine.number(row["control_movement"]) + engine.number(row["unallocated_gl"])) if row["raw_currency"] == "AED" else None
		for field in ("raw_debit", "raw_credit", "recorded_output", "recorded_input", "claimed_output", "claimed_input",
			"pending_output", "pending_input", "known_nonclaimed", "timing_output", "timing_input", "residual_output", "residual_input", "classification_difference"):
			if row[field] is not None:
				breakdown[(row["voucher_type"],row["category"])][field] += engine.number(row[field])
	result["recorded_breakdown"] = [dict(voucher_type=kind, category=category, **{k:engine.money(v) for k,v in values.items()}) for (kind,category),values in sorted(breakdown.items())]
	def total(field):
		values = [row[field] for row in result["audit_rows"]]
		return engine.money(sum(engine.number(value) for value in values)) if all(value is not None for value in values) else None
	result["tax_measures"] = {field:total(field) for field in ("recorded_output", "recorded_input", "claimed_output", "claimed_input",
		"pending_output", "pending_input", "known_nonclaimed", "timing_output", "timing_input", "residual_output", "residual_input", "classification_difference")}
	m = result["tax_measures"]
	result["measure_labels"] = dict(recorded_output="Recorded Output VAT", recorded_input="Recorded Net Input VAT",
		claimed_output="Output Allocated to Return", claimed_input="Recoverable Input VAT from Saved Sources / Supported Journal Treatment",
		pending_output="Output Pending Return Allocation", pending_input="Input Pending Recovery Verification",
		known_nonclaimed="Input VAT Unclaimed per Saved Recovery / Supported Decisions", input_not_claimed="Recorded Input VAT Less Current Return Claim (includes pending items)",
		timing_output="Output Tax-date Timing Difference",timing_input="Input Tax-date Timing Difference",
		residual_output="Unexplained Output Residual",residual_input="Unexplained Input Residual",classification_difference="GL-to-recorded-tax Unexplained Residual",
		recorded_net_movement="Recorded Output Less Net Input (credit movement)")
	m["recorded_net_movement"] = engine.money(engine.number(m["recorded_output"]) - engine.number(m["recorded_input"])) if m["recorded_output"] is not None and m["recorded_input"] is not None else None
	m["input_not_claimed"] = engine.money(engine.number(m["recorded_input"]) - engine.number(m["claimed_input"])) if m["recorded_input"] is not None and m["claimed_input"] is not None else None
	opening = sum((engine.number(g["debit"]) - engine.number(g["credit"]) for g in result.get("opening_entries", [])), engine.number(0))
	debit, credit = total("raw_debit"), total("raw_credit")
	closing = opening + engine.number(debit) - engine.number(credit)
	result["ledger_summary"] = dict(currency=result["header"]["base_currency"], opening_debit=engine.money(max(opening,0)), opening_credit=engine.money(max(-opening,0)),
		period_debit=debit, period_credit=credit, period_net_credit=engine.money(engine.number(credit)-engine.number(debit)),
		closing_debit=engine.money(max(closing,0)), closing_credit=engine.money(max(-closing,0)))
	for field in ("residual_output", "residual_input", "classification_difference"):
		if any(row[field] is None or row[field] for row in result["audit_rows"]):
			result["warnings"].append("Unexplained reconciliation residual: " + field + "; see Source Ledger Audit")
