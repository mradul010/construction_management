"""Reconcile saved generator rows to permitted journal VAT GL, without granting recovery."""
from collections import defaultdict
from decimal import Decimal
from itertools import combinations

import frappe
from frappe.utils import flt


def number(value):
	return Decimal(str(value or 0))


def signed(row):
	return number(row.get("debit")) - number(row.get("credit"))


def dimension(row, account):
	return (account, row.get("project") or "", row.get("cost_center") or "", signed(row) > 0)


def partition(units, targets, tolerance):
	"""Return a unique, exhaustive allocation; ambiguous/large searches stay unresolved."""
	if not units or not targets:
		return None
	unit_names = {unit["name"] for unit in units}
	if any(target.get("links") and not set(target["links"]) <= unit_names for target in targets):
		return None
	solutions, budget = [], [20000]

	def visit(index, remaining, allocation):
		if len(solutions) > 1 or budget[0] <= 0:
			return
		if index == len(targets):
			if not remaining:
				solutions.append(allocation)
			return
		target = targets[index]
		links = set(target.get("links") or [])
		if links:
			choices = [tuple(unit for unit in remaining if unit["name"] in links)]
		elif index == len(targets) - 1:
			choices = [tuple(remaining)]
		elif len(remaining) <= 16:
			choices = (choice for count in range(1, len(remaining) + 1) for choice in combinations(remaining, count))
		else:
			return
		for choice in choices:
			budget[0] -= 1
			if budget[0] <= 0 or len(solutions) > 1:
				return
			if not choice or (links and {unit["name"] for unit in choice} != links):
				continue
			if abs(sum((unit["amount"] for unit in choice), Decimal(0)) - target["amount"]) > tolerance:
				continue
			used = {unit["name"] for unit in choice}
			visit(index + 1, [unit for unit in remaining if unit["name"] not in used], allocation + [choice])

	visit(0, units, [])
	return solutions[0] if len(solutions) == 1 and budget[0] > 0 else None


def base_spec(row, company_currency, precision):
	"""Replay the generator's saved inclusive/exclusive boundary, never VAT / rate."""
	rate = number(row.get("custom_vat_rate"))
	base = signed(row)
	if rate <= 0 or not base or number(row.get("debit")) < 0 or number(row.get("credit")) < 0:
		return None
	side = "debit" if base > 0 else "credit"
	account_amount = number(row.get(side + "_in_account_currency")) or abs(base)
	currency = row.get("account_currency") or company_currency
	account_precision = frappe.get_precision("Journal Entry Account", "debit_in_account_currency", currency=currency)
	exchange = number(row.get("exchange_rate")) if currency != company_currency else Decimal(1)
	if exchange <= 0:
		return None
	# A foreign account must reconcile to saved company amounts; the old generator
	# mirrors currencies and is not safe to reinterpret when these values disagree.
	quantum = Decimal(1).scaleb(-precision)
	if abs(account_amount * exchange - abs(base)) > quantum:
		return None
	if row.get("custom_vat_inclusive"):
		gross = number(row.get("custom_tax_base_gross"))
		last_net = number(row.get("custom_tax_last_net"))
		account_quantum = Decimal(1).scaleb(-account_precision)
		if not gross or abs(last_net - account_amount) > account_quantum:
			return None
		net = number(flt(gross / (1 + rate / 100), account_precision))
		if abs(net - account_amount) > account_quantum:
			return None
		tax = number(flt(gross - net, account_precision))
	else:
		tax = number(flt(account_amount * rate / 100, account_precision))
	return dict(name=row["name"], amount=tax * exchange, base=base, row=row, rate=rate)


def match_journal(doc, sources, expense_accounts, company_currency, advance_accounts=()):
	"""Mutate presentation evidence only; each saved base/tax/GL row is consumed once."""
	precision = frappe.get_precision("GL Entry", "debit", currency=company_currency)
	quantum = Decimal(1).scaleb(-precision)
	rows = doc.get("accounts", [])
	bases, taxes, ledgers = defaultdict(list), defaultdict(list), defaultdict(list)
	for row in rows:
		if row.get("custom_is_tax_row"):
			taxes[dimension(row, row.get("account"))].append(row)
		elif row.get("custom_vat_account"):
			bases[dimension(row, row["custom_vat_account"])].append(row)
	for source in sources:
		ledgers[dimension(source, source["tax_account"])].append(source)
	for key, gl_sources in ledgers.items():
		base_rows, tax_rows = bases[key], taxes[key]
		if not base_rows or not tax_rows:
			continue
		specs = [base_spec(row, company_currency, precision) for row in base_rows]
		if any(spec is None for spec in specs):
			for source in gl_sources:
				source["journal_match_issue"] = "Saved journal VAT inputs or exchange amounts do not reconcile with the generator"
			continue
		targets = []
		for row in tax_rows:
			links = [row[field] for field in ("custom_vat_source_row", "custom_source_row", "source_row") if row.get(field)]
			targets.append(dict(name=row["name"], amount=abs(signed(row)), links=links))
		allocation = partition(specs, targets, quantum)
		tax_units = [dict(name=row["name"], amount=abs(signed(row))) for row in tax_rows]
		gl_targets = [dict(name=source["source_row"], amount=abs(signed(source)),
			links=[source["voucher_detail_no"]] if source.get("voucher_detail_no") else []) for source in gl_sources]
		gl_allocation = partition(tax_units, gl_targets, Decimal(0))
		if allocation is None or gl_allocation is None:
			for source in gl_sources:
				source["journal_match_issue"] = "Generated VAT/base/GL allocation is ambiguous or does not reconcile by account, project and cost center"
			continue
		by_tax = {target["name"]: units for target, units in zip(targets, allocation)}
		for source, matched_tax in zip(gl_sources, gl_allocation):
			matched = [spec for tax in matched_tax for spec in by_tax[tax["name"]]]
			base = sum((spec["base"] for spec in matched), Decimal(0))
			parties = {spec["row"].get("party") for spec in matched if spec["row"].get("party")}
			refs = [spec["name"] for spec in matched]
			invoice_linked = any(row.get("reference_type") in ("Sales Invoice", "Purchase Invoice", "POS Invoice") and row.get("reference_name") for row in rows)
			expense = all(spec["row"].get("account") in expense_accounts for spec in matched)
			customer_advance = (len(parties) == 1 and all(spec["row"].get("account") in advance_accounts and
				spec["row"].get("party_type") == "Customer" and spec["row"].get("party") for spec in matched))
			if customer_advance:
				# The configured advance base plus generated VAT must balance the
				# same customer's gross receivable; neither account names nor flags suffice.
				party = next(iter(parties))
				receivable = sum((signed(row) for row in rows if not row.get("custom_is_tax_row") and
					row.get("account") not in advance_accounts and row.get("account_type") == "Receivable" and
					row.get("party_type") == "Customer" and row.get("party") == party and
					(row.get("project") or "") == key[1]), Decimal(0))
				customer_advance = bool(receivable) and abs(receivable + base + signed(source)) <= quantum
			source.update(base=base, derived_base=base, base_row_reference=", ".join(refs),
				base_row_references=refs, generated_tax_rows=[tax["name"] for tax in matched_tax],
				party=next(iter(parties)) if len(parties) == 1 else None,
				journal_category="Recorded purchase VAT" if expense and not invoice_linked else "Unresolved",
				journal_invoice_linked=invoice_linked, journal_expense=expense,
				journal_match_issue=None,
				remarks="; ".join(filter(None, (spec["row"].get("user_remark") for spec in matched))))
			if customer_advance:
				row_emirates = {spec["row"].get("vat_emirate") for spec in matched if spec["row"].get("vat_emirate")}
				source.update(journal_category="Customer-advance output VAT", journal_vat_role="Output",
					journal_accounting_base=base, base=-base, derived_base=-base,
					tax_rate=float(matched[0]["rate"]) if len({spec["rate"] for spec in matched}) == 1 else None,
					source_emirate=doc.get("vat_emirate") or (next(iter(row_emirates)) if len(row_emirates) == 1 else None))
			elif expense and not invoice_linked:
				source["journal_vat_role"] = "Input"
			if company_currency == "AED":
				source.update(invoice_taxable_amount=float(source["base"]),
					recorded_vat_amount=float(-source["raw_vat"] if customer_advance else source["raw_vat"]), currency="AED")


def link_advance_evidence(sources, invoices, allocations=(), adjustments=()):
	"""Only permission-filtered, submitted structured links establish related invoices."""
	by_name = {invoice["name"]: invoice for invoice in invoices}
	for source in sources:
		if source.get("journal_category") != "Customer-advance output VAT":
			continue
		doc = source.get("journal_evidence", {}).get("document", {})
		direct = {row["reference_name"] for row in doc.get("accounts", []) if
			row.get("reference_type") == "Sales Invoice" and row.get("reference_name")}
		allocated = {row["parent"] for row in allocations if row.get("reference_type") == "Journal Entry" and
			row.get("reference_name") == source["voucher_no"] and number(row.get("allocated_amount"))}
		linked = direct | allocated
		adjusted = {row["parent"] for row in adjustments if row.get("reference_name") == source["voucher_no"]}
		source["linked_sales_invoices"] = sorted(linked)
		source["linked_advance_adjustments"] = sorted(adjusted)
		emirates = {source["source_emirate"]} if source.get("source_emirate") else set()
		for name in linked:
			invoice = by_name.get(name)
			if invoice and invoice.get("company") == source.get("company", doc.get("company")) and invoice.get("customer") == source.get("party"):
				if invoice.get("vat_emirate"):
					emirates.add(invoice["vat_emirate"])
		source["source_emirate"] = next(iter(emirates)) if len(emirates) == 1 else None
		if linked or adjusted:
			source["journal_duplicate_risk"] = "Structured invoice/advance-adjustment links require VAT overlap reconciliation before including this advance: " + ", ".join(sorted(linked | adjusted))
		else:
			source["journal_source_note"] = "No verified invoice or later-adjustment link found in permitted submitted records; cheque/reference text is not an invoice link"
