"""Completeness of known box subtotals, independent of ledger reconciliation."""
from collections import defaultdict

from construction_management.construction_management.report.uae_vat_201_return import engine

COMPONENTS = ("amount", "vat_amount", "adjustment")
STANDARD_OUTPUT = engine.OUTPUT[:7]


def possible_components(source, rules):
	"""Use established treatment first; genuinely unknown sources retain broad scope."""
	declared = [rule for rule in rules if (rule.get("voucher_type"), rule.get("voucher_no"), rule.get("source_row")) ==
		(source["voucher_type"], source["voucher_no"], source["source_row"])]
	adjustments = [rule for rule in declared if rule.get("is_adjustment")]
	if source.get("is_adjustment") or source.get("adjustment_type") or adjustments:
		boxes = {rule.get("box") for rule in adjustments} | {source.get("box"), source.get("vat_box")}
		boxes &= set(engine.OUTPUT + engine.INPUT)
		if not boxes:
			boxes = {"9"} if source["voucher_type"] == "Purchase Invoice" or source.get("journal_vat_role") == "Input" else set(STANDARD_OUTPUT)
		return {box: ("amount", "adjustment") for box in boxes}
	if source.get("journal_treatment") in ("VAT settlement", "VAT payment", "VAT reclassification"):
		return {}
	emirate = source.get("source_emirate")
	output_boxes = ["1" + chr(97 + engine.get_emirates().index(emirate))] if emirate in engine.get_emirates() else STANDARD_OUTPUT
	if source.get("journal_vat_role") == "Output" or source.get("journal_category") == "Customer-advance output VAT":
		boxes = output_boxes
	elif source.get("journal_category") == "Recorded purchase VAT" or source.get("journal_vat_role") == "Input":
		boxes = ["9"]
	elif source["voucher_type"] == "Purchase Invoice":
		boxes = ["3", "10"] if source.get("reverse_charge") == "Y" else ["3", "6", "10"] if source.get("potential_reverse_charge") else ["9"]
	elif source["voucher_type"] in ("Sales Invoice", "POS Invoice"):
		if source.get("treatment_hint") in ("Zero Rated", "Exempt") and not source.get("raw_vat"):
			boxes = ["4" if source["treatment_hint"] == "Zero Rated" else "5"]
		elif source.get("raw_vat") or source.get("tax_account"):
			boxes = output_boxes
		else:
			boxes = STANDARD_OUTPUT + ["4", "5"]
	else:
		# A nonzero unclassified journal tax posting could genuinely be ordinary,
		# reverse-charge, tourist/import VAT. It cannot be zero-rated/exempt VAT.
		boxes = [box for box in engine.OUTPUT + engine.INPUT if box not in ("4", "5")]
	fields = ("amount", "vat_amount") if source.get("raw_vat") or source.get("tax_account") or source.get("potential_reverse_charge") else ("amount",)
	return {box: fields for box in boxes}


def apply(result, settings):
	states = {box["box"]: {field: set() for field in COMPONENTS} for box in result["boxes"]}
	problems = {}
	groups = defaultdict(set)
	for source in result["reviews"]:
		key = (source["voucher_type"], source["voucher_no"], source["source_row"])
		reference = " / ".join(key)
		problems[reference] = source.get("issue") or source.get("review") or "Source treatment is unresolved"
		groups[problems[reference]].add(reference)
		affected = possible_components(source, settings.get("custom_vat201_classifications", []))
		source["affected_components"] = affected
		for box, fields in affected.items():
			for field in fields:
				states[box][field].add(reference)
	if result.get("scope_incomplete"):
		reference = "Restricted or unconfigured source scope"
		problems[reference] = "Source/account mapping or permissions are incomplete; no-activity cannot be confirmed"
		groups[problems[reference]].add(reference)
		for box in engine.OUTPUT + engine.INPUT:
			for field in COMPONENTS:
				states[box][field].add(reference)
	for parent, children in (("8", engine.OUTPUT), ("11", engine.INPUT)):
		for field in COMPONENTS:
			states[parent][field] = set().union(*(states[box][field] for box in children))
	for parent, child in (("12", "8"), ("13", "11")):
		states[parent]["amount"] = states[child]["vat_amount"] | states[child]["adjustment"]
	states["14"]["amount"] = states["12"]["amount"] | states["13"]["amount"]
	for box in result["boxes"]:
		box["completeness"] = {field: dict(provisional=bool(refs),
			reasons=[ref + ": " + problems[ref] for ref in sorted(refs)]) for field, refs in states[box["box"]].items()}
	for reason, refs in groups.items():
		boxes = [box["box"] for box in result["boxes"] if any(states[box["box"]][field] & refs for field in COMPONENTS)]
		if boxes:
			result["warnings"].append("Provisional known subtotals (affected components only; Boxes " + ", ".join(boxes) +
				"): " + str(len(refs)) + " source(s). " + reason)
	# Keep unresolved output identifiable and signed, without counting it in boxes
	# until its allocation and duplicate checks establish inclusion.
	result["unallocated_output"] = [dict(voucher_type=row["voucher_type"], voucher_no=row["voucher_no"], source_row=row["source_row"],
		taxable_amount=row.get("invoice_taxable_amount"), recorded_vat=row.get("recorded_vat_amount"), reason=row.get("issue"))
		for row in result["reviews"] if row.get("journal_vat_role") == "Output"]
	if result["unallocated_output"]:
		known_base = [row["taxable_amount"] for row in result["unallocated_output"]]
		known_vat = [row["recorded_vat"] for row in result["unallocated_output"]]
		base = engine.money(sum(engine.number(value) for value in known_base)) if all(value is not None for value in known_base) else None
		vat = engine.money(sum(engine.number(value) for value in known_vat)) if all(value is not None for value in known_vat) else None
		result["warnings"].append("Unallocated output VAT, excluded from box subtotals: taxable AED " + str(base if base is not None else "unavailable") +
			", recorded output VAT AED " + str(vat if vat is not None else "unavailable") + ". See the identified journal details for allocation/overlap evidence.")
	return result
