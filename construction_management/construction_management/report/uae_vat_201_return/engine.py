"""VAT preparation from posted evidence; classification never changes accounting."""
from collections import defaultdict
from decimal import Decimal

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, flt, getdate, today
from erpnext.regional.report.uae_vat_201.uae_vat_201 import get_emirates

OUTPUT = ["1" + chr(97+i) for i in range(7)] + ["2", "3", "4", "5", "6", "7"]
INPUT = ["9", "10"]
OUTPUT_ADJUSTMENTS = {"Bad Debt Relief", "Commercial Property Tax Paid by Buyer"}
INPUT_ADJUSTMENTS = {"Bad Debt Relief", "Annual Input Tax Apportionment", "Capital Assets Scheme"}
LABELS = {"1" + chr(97+i): "Standard Rated Supplies in " + emirate for i,emirate in enumerate(get_emirates())}
LABELS.update({"2": "Tax Refunds provided to Tourists under the Tax Refunds for Tourists Scheme",
	"3": "Supplies subject to the reverse charge provisions", "4": "Zero Rated Supplies", "5": "Exempt Supplies",
	"6": "Goods imported into the UAE", "7": "Adjustments to goods imported into the UAE", "8": "Totals",
	"9": "Standard Rated Expenses", "10": "Supplies subject to the reverse charge provisions", "11": "Totals",
	"12": "Total Value of due tax for the period", "13": "Total Value of recoverable tax for the period", "14": "Payable tax for the period"})
INVOICES = {"Sales Invoice": ("Sales Invoice Item", "Sales Taxes and Charges", "customer"),
	"Purchase Invoice": ("Purchase Invoice Item", "Purchase Taxes and Charges", "supplier"),
	"POS Invoice": ("POS Invoice Item", "Sales Taxes and Charges", "customer")}


def number(value):
	return Decimal(str(value or 0))


def money(value):
	return flt(value, frappe.get_precision("GL Entry", "debit", currency="AED"))


def access(company):
	from frappe.desk.query_report import get_report_doc
	get_report_doc("UAE VAT 201 Return")
	frappe.has_permission("GL Entry", "read", throw=True)
	frappe.get_doc("Company", company).check_permission("read")


def settings_for(company):
	names = frappe.get_list("UAE VAT Settings", filters={"company": company}, pluck="name", limit_page_length=1)
	return frappe.get_doc("UAE VAT Settings", names[0]) if names else frappe._dict()


def normalize(filters, settings):
	f = frappe._dict(frappe.parse_json(filters) or {})
	f.period_type = f.get("period_type") or "Custom Date Range"
	f.year = cint(f.get("year") or getdate(today()).year)
	if f.get("filing_period"):
		period = next((p for p in settings.get("custom_vat201_periods", []) if f.filing_period == f"{p.from_date} to {p.to_date}"), None)
		if not period:
			frappe.throw(_("Select a configured VAT filing period for this Company"))
		f.from_date, f.to_date = period.from_date, period.to_date
		f.period_type = "Custom Date Range"
	if f.period_type == "Monthly":
		month = cint(f.get("month"))
		if not 1 <= month <= 12:
			frappe.throw(_("Select a month from 1 to 12"))
		f.from_date = getdate(f"{f.year}-{month:02d}-01")
		f.to_date = getdate(add_days(add_months(f.from_date, 1), -1))
	elif f.period_type == "Quarterly":
		periods = [p for p in settings.get("custom_vat201_periods", []) if p.frequency == "Quarterly" and getdate(p.from_date).year == f.year and cint(p.get("quarter_number"))==cint(f.get("quarter"))]
		quarter = cint(f.get("quarter"))
		if not 1 <= quarter <= 4 or len(periods)!=1:
			frappe.throw(_("Configure the Company's quarterly VAT filing calendar in UAE VAT Settings; calendar quarters are not assumed"))
		f.from_date, f.to_date = periods[0].from_date, periods[0].to_date
	elif f.period_type != "Custom Date Range":
		frappe.throw(_("Invalid VAT Return Period"))
	elif not f.from_date and not f.to_date:
		# Open the confirmed first return, not an unrelated current-month selection.
		periods = sorted(settings.get("custom_vat201_periods", []), key=lambda p: getdate(p.from_date))
		if periods:
			f.from_date, f.to_date = periods[0].from_date, periods[0].to_date
		else:
			f.from_date, f.to_date = getdate(today()).replace(day=1), getdate(today())
	if not f.from_date or not f.to_date or getdate(f.from_date) > getdate(f.to_date):
		frappe.throw(_("A valid From Date and To Date are required"))
	f.from_date, f.to_date = getdate(f.from_date), getdate(f.to_date)
	f.include_adjustments = cint(f.get("include_adjustments", 1))
	f.show_zero = cint(f.get("show_zero", 1))
	return f


def taxpayer(company, settings, f):
	company_doc = frappe.get_doc("Company", company)
	period = next((p for p in settings.get("custom_vat201_periods", []) if getdate(p.from_date) == f.from_date and getdate(p.to_date) == f.to_date), frappe._dict())
	address_names = frappe.get_all("Dynamic Link", filters={"parenttype": "Address", "link_doctype": "Company", "link_name": company}, pluck="parent")
	addresses = frappe.get_list("Address", filters={"name": ["in", address_names]}, fields=["address_line1", "address_line2", "city", "state", "country", "pincode"], limit_page_length=1) if address_names else []
	address = ", ".join(str(v) for v in addresses[0].values() if v) if addresses else None
	return dict(company=company, legal_name_english=settings.get("custom_vat201_legal_name_english") or company_doc.company_name, legal_name_arabic=settings.get("custom_vat201_legal_name_arabic"),
		trn=company_doc.tax_id, address=address, currency="AED", base_currency=company_doc.default_currency,
		registration_date=str(settings.custom_vat201_registration_date) if settings.get("custom_vat201_registration_date") else None,
		registered_emirate=settings.get("custom_vat201_registered_emirate"),
		filing_frequency=period.get("frequency"), quarter_number=period.get("quarter_number"),
		due_date_basis=period.get("due_date_basis"),
		from_date=str(f.from_date), to_date=str(f.to_date), stagger=period.get("stagger"), due_date=str(period.due_date) if period.get("due_date") else None,
		tax_year_end=str(period.tax_year_end) if period.get("tax_year_end") else None,
		period_label=period.get("label"), period_status=period.get("status"), period_kind="Configured filing period" if period else "Analytical period",
		profit_margin_scheme=period.get("profit_margin_scheme") or f.get("profit_margin_scheme"),
		signatory_english=settings.get("custom_vat201_signatory_english"), signatory_arabic=settings.get("custom_vat201_signatory_arabic"),
		mobile_code=settings.get("custom_vat201_mobile_code"), mobile=settings.get("custom_vat201_mobile"), email=settings.get("custom_vat201_email"),
		submission_date=str(period.submission_date) if period.get("submission_date") else None)


def fields_existing(doctype, fields):
	meta = frappe.get_meta(doctype)
	return [f for f in fields if f in ("name","parent","parenttype","idx") or meta.has_field(f)]


def recovery_source_references(docs):
	"""Read recovery changes only for permitted parents; never infer intent from default zero."""
	fields = ("recoverable_standard_rated_expenses", "recoverable_reverse_charge")
	parents = {d.name: d for d in docs if d.get(fields[0]) == 0 or d.get("reverse_charge") == "Y"}
	if not parents:
		return {}
	# Frappe's form loader also reads Version after checking access to its parent.
	versions = frappe.get_all("Version", filters={"ref_doctype": "Purchase Invoice", "docname": ["in", list(parents)]},
		fields=["name", "docname", "data"], order_by="creation desc, name desc", limit_page_length=0)
	references, seen = {}, set()
	for version in versions:
		try:
			data = frappe.parse_json(version.data)
		except (ValueError, TypeError):
			continue
		if not isinstance(data, dict):
			continue
		changes = data.get("changed") or []
		if not isinstance(changes, list):
			continue
		for change in changes:
			if not isinstance(change, (list, tuple)) or len(change) != 3 or change[0] not in fields:
				continue
			field, old, new = change
			key = (version.docname, field)
			if key in seen:
				continue
			seen.add(key)
			current = parents[version.docname].get(field)
			if old in (None, "") or new in (None, "") or current in (None, ""):
				continue
			try:
				if number(old) != number(new) and number(new) == number(current):
					references[key] = "Saved " + field + " decision in source Version " + version.name
			except (ArithmeticError, ValueError, TypeError):
				continue
	return references


def source_data(f, rules, candidate_accounts):
	"""Read each parent/child table in bulk, constrained by parent permissions."""
	sources, headers, warnings = [], {}, []
	for dt, (item_dt, tax_dt, party) in INVOICES.items():
		if not frappe.has_permission(dt, "read"):
			warnings.append(_("{0} is not accessible; VAT results are incomplete").format(dt))
			continue
		dated = [r.voucher_no for r in rules if r.voucher_type == dt and f.from_date <= getdate(r.tax_date) <= f.to_date]
		or_filters = [["posting_date", "between", [f.from_date, f.to_date]]]
		if dated:
			or_filters.append(["name", "in", dated])
		doc_filters = {"company": f.company, "docstatus": 1}
		docs = frappe.get_list(dt, filters=doc_filters, or_filters=or_filters,
			fields=fields_existing(dt, ["name","posting_date",party,"base_net_total","currency","conversion_rate","is_return","return_against","reverse_charge", "vat_emirate", "project", "bill_no", "bill_date", "tax_id", "remarks", "ra_bill", "recoverable_standard_rated_expenses", "recoverable_reverse_charge", "custom_vat201_evidence_reference"]), limit_page_length=0)
		if not docs:
			continue
		posted_gl = frappe.get_list("GL Entry", filters={"company":f.company,"voucher_type":dt,"voucher_no":["in",[d.name for d in docs]],"docstatus":1,"is_cancelled":0}, fields=["name","voucher_no","account","debit","credit"],limit_page_length=0)
		posted = {g.voucher_no for g in posted_gl}
		if dt != "POS Invoice" and any(d.name not in posted for d in docs):
			warnings.append(_("Some submitted {0} documents have no accessible active GL; verify missing postings or source permissions").format(dt))
		gl_by_account = defaultdict(list)
		for g in posted_gl:
			gl_by_account[(g.voucher_no,g.account)].append(g)
		docs = [d for d in docs if d.name in posted]
		if not docs:
			continue
		names = [d.name for d in docs]
		recovery_references = recovery_source_references(docs) if dt == "Purchase Invoice" else {}
		taxes = frappe.get_all(tax_dt, filters={"parent": ["in", names], "parenttype": dt}, fields=fields_existing(tax_dt,["name","parent","idx","row_id","account_head","charge_type","rate","base_tax_amount_after_discount_amount","base_total","add_deduct_tax","category"]), order_by="idx asc", limit_page_length=0)
		items = frappe.get_all(item_dt, filters={"parent": ["in", names], "parenttype":dt}, fields=fields_existing(item_dt,["name","parent","base_net_amount","income_account","expense_account","is_zero_rated","is_exempt","description","project","item_code"]), limit_page_length=0)
		by_tax, by_item = defaultdict(list), defaultdict(list)
		for row in taxes:
			by_tax[row.parent].append(row)
		for row in items:
			by_item[row.parent].append(row)
		for doc in docs:
			headers[(dt,doc.name)] = doc
			evidence = dict(project=doc.get("project"), is_return=doc.get("is_return"), return_against=doc.get("return_against"),
				source_emirate=doc.get("vat_emirate"), bill_no=doc.get("bill_no"), bill_date=doc.get("bill_date"),
				source_tax_id=doc.get("tax_id"), remarks=doc.get("remarks"), ra_bill=doc.get("ra_bill"),
				recovery_source_amount=doc.get("recoverable_standard_rated_expenses"),
				recovery_source_reference=recovery_references.get((doc.name, "recoverable_standard_rated_expenses")),
				reverse_recovery_percent=doc.get("recoverable_reverse_charge"),
				reverse_recovery_reference=recovery_references.get((doc.name, "recoverable_reverse_charge")),
				verification_reference=doc.get("custom_vat201_evidence_reference"),
				item_evidence=[dict(i) for i in by_item[doc.name]])
			vat_taxes = [t for t in by_tax[doc.name] if t.account_head in candidate_accounts and number(t.base_tax_amount_after_discount_amount)]
			evidence["vat_rows_count"] = len(vat_taxes)
			for tax in vat_taxes:
				base = None
				if tax.charge_type == "On Net Total":
					base = doc.base_net_total
				elif tax.charge_type == "On Previous Row Total":
					previous = next((t for t in by_tax[doc.name] if t.idx == cint(tax.get("row_id"))), None)
					base = previous.base_total if previous else None
				# Mixed tax treatments and multiple VAT rows need explicit allocation.
				if len(vat_taxes) > 1 or any(i.get("is_zero_rated") or i.get("is_exempt") for i in by_item[doc.name]):
					base = None
				vat = number(tax.base_tax_amount_after_discount_amount)
				if tax.get("add_deduct_tax") == "Deduct":
					vat = -vat
				gl_rows = gl_by_account[(doc.name,tax.account_head)]
				gl_tax = sum((number(g.credit)-number(g.debit) if dt in ("Sales Invoice","POS Invoice") else number(g.debit)-number(g.credit) for g in gl_rows), Decimal(0))
				account_tax = sum((number(t.base_tax_amount_after_discount_amount)*(-1 if t.get("add_deduct_tax")=="Deduct" else 1) for t in vat_taxes if t.account_head==tax.account_head), Decimal(0))
				sources.append(dict(evidence, voucher_type=dt,voucher_no=doc.name,source_row=tax.name,posting_date=doc.posting_date,party=doc.get(party),
					base=base,raw_vat=vat,tax_rate=tax.rate,tax_account=tax.account_head,account=None,reverse_charge=doc.get("reverse_charge"),currency=doc.currency,
					gl_evidence=[dict(g) for g in gl_rows], invoice_tax_difference=money(account_tax-gl_tax)))
			for item in by_item[doc.name]:
				if vat_taxes and not (item.get("is_zero_rated") or item.get("is_exempt")):
					continue
				sources.append(dict(evidence, voucher_type=dt,voucher_no=doc.name,source_row=item.name,posting_date=doc.posting_date,party=doc.get(party),base=item.base_net_amount,
					raw_vat=Decimal(0),tax_rate=0,tax_account=None,account=item.get("income_account") or item.get("expense_account"),currency=doc.currency,
					treatment_hint="Exempt" if item.get("is_exempt") else "Zero Rated" if item.get("is_zero_rated") else "Unclassified"))
	return sources, headers, warnings


def apply_rule(source, rule, base_currency, *, source_verified=False):
	"""Return an event or a review reason. Amounts always originate in posted evidence."""
	box = rule.box
	if box not in OUTPUT + INPUT + ["Outside VAT"]:
		return None, "Invalid VAT 201 box"
	if (not source_verified and not rule.get("approved_by")) or not rule.get("reason") or not rule.get("supporting_reference"):
		return None, "Classification approval and supporting evidence are incomplete"
	if rule.get("requires_review"):
		return None, "Source cancelled, amended or changed; classification requires renewed review"
	if source.get("invoice_tax_difference") and not source.get("reverse_charge") == "Y":
		return None, "Source invoice VAT does not reconcile with active GL postings"
	if rule.get("source_fingerprint"):
		from construction_management.construction_management.report.uae_vat_201_return.review import fingerprint
		if rule.source_fingerprint != fingerprint(source):
			return None, "Source evidence changed since review; approval must be renewed"
	if box=="Outside VAT":
		return dict(source,box=box,amount=0,vat_amount=0,adjustment=0,tax_date=str(rule.tax_date),reason=rule.reason,supporting_reference=rule.supporting_reference,classification="Outside VAT scope",company=source.get("company")),None
	if box in INPUT and (not rule.get("recovery_confirmed") or not 0 <= flt(rule.recovery_percent) <= 100):
		return None, "Input VAT recoverability has not been explicitly reviewed"
	rate = Decimal(1) if base_currency == "AED" else number(rule.get("aed_exchange_rate"))
	if rate <= 0:
		return None, "Approved tax-point AED exchange rate is missing"
	base = number(rule.taxable_base_aed) if rule.get("override_base") else (number(source["base"]) * rate if source.get("base") is not None else None)
	if base is None:
		return None, "Reviewed taxable base is required for this tax calculation or journal posting"
	vat = number(source["raw_vat"]) * rate
	if "debit" in source:
		vat = (number(source["debit"]) - number(source["credit"])) * rate * (-1 if box in OUTPUT else 1)
	if box in ("4","5") and vat:
		return None, "Zero-rated/exempt supplies cannot contain posted VAT"
	if source["voucher_type"] in ("Sales Invoice","POS Invoice") and box in INPUT:
		return None, "Sales invoices cannot be claimed as input VAT"
	if source["voucher_type"] == "Purchase Invoice" and box in OUTPUT[:7]+["2","4","5"]:
		return None, "Purchase invoices cannot be classified as sales supplies or tourist refunds"
	if box=="2" and (vat>0 or base>0):
		return None, "Tourist refunds require negative posted tax corrections"
	if box in ("3","10") and source["voucher_type"] == "Purchase Invoice" and source.get("reverse_charge") != "Y":
		return None, "Purchase reverse charge is not enabled on the source document"
	if box in ("6","7") and not rule.get("override_base"):
		return None, "Imports require a reviewed customs taxable base and supporting reference"
	if rule.get("is_adjustment") and (not rule.get("adjustment_type") or box not in ["1"+chr(97+i) for i in range(7)]+["9"]):
		return None, "Invalid Adjustment column classification"
	if rule.get("is_adjustment"):
		allowed = INPUT_ADJUSTMENTS if box=="9" else OUTPUT_ADJUSTMENTS
		if rule.adjustment_type not in allowed or (box!="9" and vat>0):
			return None, "Adjustment column treatment is not valid for this box; ordinary corrections belong in the VAT Amount column"
	full_vat = vat
	source_base = base
	if box in INPUT:
		vat *= number(rule.recovery_percent) / 100
		if not flt(rule.recovery_percent):
			base = Decimal(0)
	event = dict(source, box=box, amount=money(base),vat_amount=0 if rule.get("is_adjustment") else money(vat),
		adjustment=money(vat) if rule.get("is_adjustment") else 0,full_vat=money(full_vat),nonrecoverable=money(full_vat-vat),
		tax_date=str(rule.tax_date),emirate=get_emirates()[ord(box[-1])-97] if box in OUTPUT[:7] else None,
		classification=LABELS[box],reason=rule.reason,supporting_reference=rule.supporting_reference,company=source.get("company"),currency="AED",source_currency=source.get("currency"),base_currency=base_currency,aed_exchange_rate=float(rate),source_taxable_amount=money(source_base))
	return event, None


def aggregate(events):
	boxes = {key:dict(box=key,description=LABELS[key],amount=0.0,vat_amount=0.0,adjustment=0.0,currency="AED") for key in OUTPUT+["8"]+INPUT+["11","12","13","14"]}
	for key in OUTPUT+INPUT:
		for field in ("amount","vat_amount","adjustment"):
			boxes[key][field] = money(sum((number(e[field]) for e in events if e["box"]==key),Decimal(0)))
	for target, children in (("8",OUTPUT),("11",INPUT)):
		for field in ("amount","vat_amount","adjustment"):
			boxes[target][field] = money(sum(number(boxes[k][field]) for k in children))
	boxes["12"]["amount"] = money(number(boxes["8"]["vat_amount"])+number(boxes["8"]["adjustment"]))
	boxes["13"]["amount"] = money(number(boxes["11"]["vat_amount"])+number(boxes["11"]["adjustment"]))
	boxes["14"]["amount"] = money(number(boxes["12"]["amount"])-number(boxes["13"]["amount"]))
	return boxes


def ledger_sides(entry, mappings, headers, events):
	side = mappings.get(entry.account)
	debit, credit = number(entry.debit), number(entry.credit)
	if side == "Both":
		if entry.voucher_type in ("Sales Invoice","POS Invoice"):
			side = "Output"
		elif entry.voucher_type == "Purchase Invoice":
			header = headers.get((entry.voucher_type,entry.voucher_no),{})
			if header.get("reverse_charge") == "Y":
				return [("Output",-debit),("Input",-credit)] if header.get("is_return") else [("Input",debit),("Output",credit)]
			side = "Input"
		else:
			matching = [e for e in events if e["source_row"]==entry.name]
			side = ("Input" if matching[0]["box"] in INPUT else "Output") if len(matching)==1 else None
	return [(side if side in ("Output","Input") else "Unallocated", credit-debit if side=="Output" else debit-credit)]


def account_mappings(rows):
	"""One ledger scan per account, even when legacy rows map it on both sides."""
	sides = defaultdict(set)
	for row in rows:
		side = row.get("custom_vat201_side")
		sides[row.account].update(("Input", "Output") if side == "Both" else (side,))
	return {account: "Both" if values == {"Input", "Output"} else next(iter(values)) if len(values) == 1 else None
		for account, values in sides.items()}


def build(filters, settings_override=None):
	filters = frappe._dict(frappe.parse_json(filters) or {})
	if not filters.company:
		frappe.throw(_("Company is mandatory"))
	access(filters.company)
	settings = settings_override if settings_override is not None else settings_for(filters.company)
	f = normalize(filters,settings)
	header = taxpayer(f.company,settings,f)
	if header["profit_margin_scheme"] == "Yes":
		frappe.throw(_("Profit Margin Scheme calculation is not supported. A VAT return cannot be generated for this selection."))
	warnings = []
	for key,label in (("trn","TRN"),("stagger","VAT Stagger"),("due_date","VAT Return Due Date"),("tax_year_end","Tax Year End"),("profit_margin_scheme","Profit Margin Scheme answer")):
		if not header[key]:
			warnings.append(_("{0}: Not Configured").format(label))
	if header["period_kind"] == "Analytical period":
		warnings.append(_("Analytical period; this selection is not a configured VAT filing period"))
	if not f.include_adjustments:
		warnings.append(_("Adjustments are excluded; this is an analytical report"))
	if header.get("due_date_basis") == "Provisional (28 days)":
		warnings.append(_("Due date is provisional (period end plus 28 days); confirm against the FTA filing calendar"))
	mappings = account_mappings(settings.get("uae_vat_accounts", []))
	if not mappings or any(v not in ("Output","Input","Both") for v in mappings.values()):
		warnings.append(_("VAT accounts and ledger sides must be configured in UAE VAT Settings"))
	accounts = frappe.get_list("Account",filters={"company":f.company},fields=["name","account_type"],limit_page_length=0)
	accessible_accounts = {a.name for a in accounts}
	if set(mappings)-accessible_accounts:
		warnings.append(_("Some configured VAT accounts are restricted; report scope is incomplete"))
	candidates = ({a.name for a in accounts if a.account_type == "Tax"} | set(mappings)) & accessible_accounts
	rules = [r for r in settings.get("custom_vat201_classifications", []) if r.approved and r.tax_date and not r.get("requires_review")]
	sources, headers, source_warnings = source_data(f,rules,candidates)
	warnings += source_warnings
	date_filters = [["posting_date","between",[f.from_date,f.to_date]]]
	dated_gl = [r.source_row for r in rules if r.voucher_type in ("Journal Entry","Payment Entry") and f.from_date <= getdate(r.tax_date) <= f.to_date]
	if dated_gl:
		date_filters.append(["name","in",dated_gl])
	all_tax_gl = frappe.get_list("GL Entry",filters={"company":f.company,"account":["in",sorted(candidates)],"docstatus":1,"is_cancelled":0},or_filters=date_filters,
		fields=["name","posting_date","voucher_type","voucher_no","account","debit","credit"],limit_page_length=0) if candidates else []
	ledger = [g for g in all_tax_gl if f.from_date <= getdate(g.posting_date) <= f.to_date]
	if any(g.voucher_type in INVOICES and (g.voucher_type,g.voucher_no) not in headers for g in ledger):
		warnings.append(_("Some tax-ledger vouchers are restricted as source documents; results are incomplete"))
	# Journal/Payment tax events use actual GL row IDs and document permissions.
	for dt in {g.voucher_type for g in all_tax_gl if g.voucher_type not in INVOICES}:
		if dt not in ("Journal Entry","Payment Entry") or not frappe.has_permission(dt,"read"):
			warnings.append(_("Unsupported or restricted tax-ledger voucher type: {0}").format(dt))
			continue
		allowed = set(frappe.get_list(dt,filters={"company":f.company,"docstatus":1,"name":["in",[g.voucher_no for g in all_tax_gl if g.voucher_type==dt]]},pluck="name",limit_page_length=0))
		if any(g.voucher_type==dt and g.voucher_no not in allowed for g in all_tax_gl):
			warnings.append(_("Some tax-ledger vouchers are restricted as source documents; results are incomplete"))
		for g in all_tax_gl:
			if g.voucher_type==dt and g.voucher_no in allowed:
				sources.append(dict(voucher_type=dt,voucher_no=g.voucher_no,source_row=g.name,posting_date=g.posting_date,party=None,
					base=None,raw_vat=number(g.debit)-number(g.credit),debit=g.debit,credit=g.credit,tax_account=g.account,account=g.account,currency=header["base_currency"]))
	from construction_management.construction_management.report.uae_vat_201_return.review import enrich_journals, annotate_reviews, control_movement_only
	enrich_journals(sources)
	by_source = defaultdict(list)
	for rule in rules:
		by_source[(rule.voucher_type,rule.voucher_no,rule.source_row)].append(rule)
	events, reviews, excluded = [], [], []
	seen = set()
	for source in sources:
		source["company"] = f.company
		key = (source["voucher_type"],source["voucher_no"],source["source_row"])
		matched = by_source.get(key,[])
		if any(r.box=="Outside VAT" for r in matched) and len(matched)>1:
			reviews.append(dict(source,review="Outside VAT exclusion conflicts with another classification"))
			continue
		if not matched:
			if f.from_date <= getdate(source["posting_date"]) <= f.to_date:
				reviews.append(dict(source,review="VAT classification, tax date and supporting evidence require review"))
			continue
		for rule in matched:
			if rule.box!="Outside VAT" and not f.from_date <= getdate(rule.tax_date) <= f.to_date:
				continue
			side = "Input" if rule.box in INPUT else "Output"
			unique = key+("GL" if source["voucher_type"] in ("Journal Entry","Payment Entry") else side,)
			if unique in seen:
				reviews.append(dict(source,review="Duplicated source event classification"))
				continue
			seen.add(unique)
			if rule.box=="Outside VAT":
				if source.get("tax_account") in mappings and not control_movement_only(source,rule):
					reviews.append(dict(source,review="A configured VAT-account posting cannot be excluded as Outside VAT"))
					continue
				exclusion,error=apply_rule(source,rule,header["base_currency"])
				if error:
					reviews.append(dict(source,review=error))
				else:
					exclusion.update(classification_status="Approved", classification_id=rule.name, origin=rule.get("origin") or "Manual", journal_treatment=rule.get("journal_treatment"))
					excluded.append(exclusion)
				continue
			if source.get("tax_account") and mappings.get(source["tax_account"]) not in (side,"Both"):
				reviews.append(dict(source,review="VAT account / ledger side is not mapped"))
				continue
			event,error = apply_rule(source,rule,header["base_currency"])
			if error:
				reviews.append(dict(source,review=error))
			elif not rule.is_adjustment or f.include_adjustments:
				event.update(classification_status="Approved", classification_id=rule.name, origin=rule.get("origin") or "Manual", journal_treatment=rule.get("journal_treatment"))
				events.append(event)
	boxes = aggregate(events)
	# Reconciliation uses posting dates; tax-date differences remain visible.
	ledger_totals = {"Output":Decimal(0),"Input":Decimal(0),"Unallocated":Decimal(0)}
	ledger_available = {side:True for side in ledger_totals}
	rates_by_voucher, events_by_source = defaultdict(set), defaultdict(list)
	for event in events:
		rates_by_voucher[(event["voucher_type"],event["voucher_no"],event.get("tax_account"))].add(event["aed_exchange_rate"])
		events_by_source[(event["voucher_type"],event["voucher_no"],event["source_row"])].append(event)
	has_unallocated = False
	excluded_gl = {e["source_row"] for e in excluded if "debit" in e}
	excluded_invoice_accounts = {(e["voucher_type"],e["voucher_no"],e.get("tax_account")) for e in excluded if "debit" not in e and e.get("tax_account")}
	for g in ledger:
		if g.name in excluded_gl or (g.voucher_type,g.voucher_no,g.account) in excluded_invoice_accounts:
			continue
		factor = Decimal(1)
		if header["base_currency"] != "AED":
			rates = rates_by_voucher[(g.voucher_type,g.voucher_no,g.account)]
			factor = number(next(iter(rates))) if len(rates)==1 else None
		for side,balance in ledger_sides(g,mappings,headers,events_by_source[(g.voucher_type,g.voucher_no,g.name)]):
			has_unallocated |= side=="Unallocated"
			if factor is None:
				ledger_available[side] = False
				warnings.append(_("Some ledger postings lack a unique approved AED exchange rate; AED ledger totals for those sides are unavailable"))
			else:
				ledger_totals[side] += balance*factor
	reconciliation = []
	for side,key in (("Output","12"),("Input","13")):
		report_amount = boxes[key]["amount"]
		mapped_side = any(value in (side,"Both") for value in mappings.values())
		ledger_amount = money(ledger_totals[side]) if ledger_available[side] and mapped_side else None
		difference = money(number(report_amount)-number(ledger_amount)) if ledger_amount is not None else None
		reconciliation.append(dict(description=side+" VAT",report_amount=report_amount,ledger_amount=ledger_amount,difference=difference,currency="AED"))
		if difference:
			warnings.append(_("{0} VAT differs from the posting-date ledger; review missing mappings, tax dates, recovery exclusions and manual entries").format(side))
	if has_unallocated:
		warnings.append(_("Tax-account postings remain unallocated to Output/Input VAT; configure accounts and review manual entries"))
	reconciliation.append(dict(description="Unallocated tax-account ledger (debit - credit)",report_amount=None,ledger_amount=money(ledger_totals["Unallocated"]) if ledger_available["Unallocated"] else None,difference=None,currency="AED"))
	if reviews:
		warnings.append(_("{0} transactions require VAT classification review").format(len(reviews)))
	annotate_reviews(reviews, settings, mappings)
	invoice_checks = []
	checked = set()
	for source in sources:
		key = (source["voucher_type"],source["voucher_no"],source.get("tax_account"))
		if source["voucher_type"] not in INVOICES or not key[2] or key in checked:
			continue
		checked.add(key)
		invoice_checks.append(dict(voucher_type=key[0],voucher_no=key[1],tax_account=key[2],
			difference=source.get("invoice_tax_difference"),currency=header["base_currency"]))
		if source.get("invoice_tax_difference"):
			warnings.append(_("Invoice tax/GL difference: {0}").format(source["voucher_no"]))
	observed = {}
	for side, types in (("sales",("Sales Invoice","POS Invoice")),("purchases",("Purchase Invoice",))):
		selected = [s for s in sources if s["voucher_type"] in types and s.get("tax_account") in mappings]
		observed[side+"_vat"] = money(sum((number(s["raw_vat"]) for s in selected),Decimal(0))) if header["base_currency"]=="AED" else None
		observed[side+"_base"] = money(sum((number(s["base"]) for s in selected if s.get("base") is not None),Decimal(0))) if header["base_currency"]=="AED" else None
	control = money(sum((number(g.debit)-number(g.credit) for g in ledger if g.account in mappings),Decimal(0))) if header["base_currency"]=="AED" else None
	reconciliation.append(dict(description="Mapped VAT control account movement (debit - credit)",
		report_amount=None,ledger_amount=control,difference=None,currency="AED"))
	if reviews:
		warnings.append(_("Unapproved sources are NOT included in VAT boxes. Zero classified subtotals are not a nil return; recoverable VAT and net liability are undetermined until review."))
	status = "Needs Review" if warnings or reviews else "Ready for Approval"
	if status=="Ready for Approval" and header.get("period_status") in ("Approved","Filed"):
		status = header["period_status"]
	if not sources and not ledger:
		status = "No Transactions"
	return dict(header=header,filters=f,boxes=list(boxes.values()),events=events,reviews=reviews,excluded=excluded,reconciliation=reconciliation,
		warnings=list(dict.fromkeys(warnings)),status=status,transaction_count=len(sources),
		invoice_checks=invoice_checks, observed=observed, control_movement=control)
