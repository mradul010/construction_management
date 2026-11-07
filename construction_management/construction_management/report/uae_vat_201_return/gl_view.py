"""Books view: posting-date ledger amounts, independent of recovery decisions."""
import frappe
from openpyxl.styles import Font, Alignment

MEASURES = (
	("period_credit", "Period VAT Credits"),
	("period_debit", "Period VAT Debits"),
	("period_net_credit", "Net VAT per Books (credit minus debit)"),
	("opening_debit", "Opening Debit Balance"),
	("opening_credit", "Opening Credit Balance"),
	("closing_debit", "Closing Debit Balance"),
	("closing_credit", "Closing Credit Balance"),
)
FIELDS = ("posting_date", "voucher_type", "voucher_no", "account", "name", "debit", "credit")
LABELS = ("Posting Date", "Voucher Type", "Voucher", "VAT Account", "GL Entry", "Debit", "Credit")


def enabled(result):
	return result.get("report_view") == "General Ledger"


def summary_rows(result):
	ledger = result.get("ledger_summary", {})
	return [dict(key=key, description=label, amount=ledger.get(key), currency=ledger.get("currency")) for key, label in MEASURES]


def columns():
	return [dict(fieldname="description", label="Measure", fieldtype="Data", width=420),
		dict(fieldname="amount", label="Amount", fieldtype="Currency", options="currency", width=200),
		dict(fieldname="currency", fieldtype="Data", hidden=1)]


def cards(result):
	data = business_summary(result)
	currency = result.get("ledger_summary", {}).get("currency")
	cards = [dict(label=label, value=data[key][field] if data[key][field] is not None else "Not Available",
		datatype="Currency" if data[key][field] is not None else "Data", currency=currency, precision=2,
		provisional=data[key][field] is None) for key, field, label in (
		("sales", "base", "Net Sales Amount (excluding VAT)"), ("sales", "vat", "Net Sales VAT"),
		("purchases", "base", "Net Purchases and Expenses (excluding VAT)"), ("purchases", "vat", "Net Purchase and Expense VAT"))]
	payable = net_payable(result, data)
	cards.append(dict(label="Net VAT Payable" if payable >= 0 else "Net VAT Refundable", value=payable,
		datatype="Currency", currency=currency, precision=2, provisional=False))
	return cards


def net_payable(result, data=None):
	from construction_management.construction_management.report.uae_vat_201_return.engine import number, money
	data = data if data is not None else business_summary(result)
	return money(number(data["sales"]["vat"]) - number(data["purchases"]["vat"]))



CATEGORIES = {"sales": "Sales including customer advances, less returns", "purchases": "Purchases and expenses less returns",
	"other": "Unallocated ledger entries"}
SUMMARY_CATEGORIES = ("sales", "purchases")


def ordered(entries):
	return sorted(entries, key=lambda r: (str(r.get("posting_date") or ""), r.get("voucher_type") or "", r.get("voucher_no") or "", r.get("name") or r.get("source_row") or ""))


def business_summary(result):
	"""Use raw source bases and GL signs, never approved recovery or return events."""
	from collections import defaultdict
	from construction_management.construction_management.report.uae_vat_201_return.engine import number, money
	sources = defaultdict(list)
	for source in result.get("sources", []):
		sources[(source["voucher_type"], source["voucher_no"])].append(source)
	groups = defaultdict(list)
	for entry in ordered(result.get("ledger_entries", [])):
		key = (entry["voucher_type"], entry["voucher_no"])
		linked = [s for s in sources[key] if s.get("source_row") == entry["name"] or entry["name"] in s.get("journal_group_gl_rows", [])]
		category = "sales" if key[0] in ("Sales Invoice", "POS Invoice") else "purchases" if key[0] == "Purchase Invoice" else None
		if category is None:
			kinds = {s.get("journal_category") for s in linked}
			category = "purchases" if kinds == {"Recorded purchase VAT"} else "sales" if kinds == {"Customer-advance output VAT"} else "other"
		groups[(category, *key)].append(entry)
	out = {key: dict(label=label, base=0, vat=0, rows=[], entries=[], missing_bases=0) for key, label in CATEGORIES.items()}
	for (category, dt, voucher), entries in groups.items():
		ids = {r["name"] for r in entries}
		accounts = {r["account"] for r in entries}
		selected = [s for s in sources[(dt, voucher)] if
			(s.get("tax_account") in accounts if dt in ("Sales Invoice", "POS Invoice", "Purchase Invoice") else
			 s.get("source_row") in ids or bool(ids.intersection(s.get("journal_group_gl_rows", []))))]
		selected = list({s["source_row"]: s for s in selected}.values())
		base = sum((number(s["base"]) for s in selected), number(0)) if selected and all(s.get("base") is not None for s in selected) else None
		vat = sum((number(e["credit"])-number(e["debit"]) for e in entries), number(0)) * (-1 if category == "purchases" else 1)
		target = out[category]
		target["entries"].extend(entries)
		target["rows"].append(dict(voucher_type=dt, voucher_no=voucher, posting_date=min(str(e["posting_date"]) for e in entries),
			base=money(base) if base is not None else None, vat=money(vat), gl_entries=", ".join(sorted(ids)),
			category="Expense journal" if category == "purchases" and dt == "Journal Entry" else "Customer advance" if category == "sales" and dt == "Journal Entry" else CATEGORIES[category]))
		target["vat"] += vat
		if base is None:
			target["missing_bases"] += 1
		else:
			target["base"] += base
	for target in out.values():
		target["base"] = None if target["missing_bases"] else money(target["base"])
		target["vat"] = money(target["vat"])
		target["rows"] = ordered(target["rows"])
		target["entries"] = ordered(target["entries"])
	return out


def drilldown(result, group, component="vat"):
	if component not in ("base", "vat"):
		frappe.throw("Unsupported VAT detail component")
	if group == "net_payable":
		data = business_summary(result)
		return dict(kind="ledger", rows=ordered(data["sales"]["entries"] + data["purchases"]["entries"]), label="Net VAT Payable / Refundable")
	if group in CATEGORIES:
		data = business_summary(result)[group]
		return dict(kind="sources" if component == "base" else "ledger", rows=data["rows"] if component == "base" else data["entries"], label=data["label"])
	if group not in {key for key, label in MEASURES}:
		frappe.throw("Unsupported VAT detail group")
	entries = result.get("opening_entries", []) if group.startswith("opening_") else result.get("ledger_entries", [])
	if group.startswith("closing_"):
		entries = result.get("opening_entries", []) + entries
	if group in ("period_credit", "period_debit"):
		entries = [e for e in entries if e.get("credit" if group == "period_credit" else "debit")]
	return dict(kind="ledger", rows=ordered(entries), label=dict(MEASURES)[group])


def export_rows(result):
	h = result["header"]
	currency = result.get("ledger_summary", {}).get("currency")
	return [["VAT Sales and Purchases"], ["Company", h.get("company")],
		["Posting period", h.get("from_date"), h.get("to_date")], ["Currency", currency],
		["Posted VAT account movements; internal recovery approval does not change these totals."],
		["Category", "Amount Excluding VAT", "Recorded VAT"]] + [[d["label"], d["base"], d["vat"]] for key, d in business_summary(result).items() if key in SUMMARY_CATEGORIES] + [["Net VAT Payable / Refundable", net_payable(result)], ["Recorded sales VAT less purchase/expense VAT; excludes opening balances and unallocated ledger entries."], ["GL Reconciliation"], ["Measure", "Amount"]] + [[r["description"], r["amount"]] for r in summary_rows(result)]


def html(result, interactive=False):
	from urllib.parse import quote
	entries = [dict(row, voucher_url="/app/" + frappe.scrub(row["voucher_type"]).replace("_", "-") + "/" + quote(row["voucher_no"], safe="")) for row in ordered(result.get("ledger_entries", []))]
	return frappe.render_template("construction_management/report/uae_vat_201_return/gl_content.html",
		dict(result=result, rows=summary_rows(result), business=business_summary(result), summary_categories=SUMMARY_CATEGORIES, payable=net_payable(result), entries=entries, interactive=interactive))


def sheets(workbook, result):
	def safe(value):
		return "'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@")) else value
	summary = workbook.create_sheet("VAT per General Ledger", 0)
	for row in export_rows(result):
		summary.append([safe(v) for v in row])
	ledger = workbook.create_sheet("VAT GL Entries", 1)
	ledger.append(LABELS)
	for row in ordered(result.get("ledger_entries", [])):
		ledger.append([safe(row.get(k)) for k in FIELDS])
	ledger.auto_filter.ref = ledger.dimensions
	extra = []
	for key, data in business_summary(result).items():
		sheet = workbook.create_sheet("VAT Reconciliation Entries" if key == "other" else "VAT " + key.title())
		sheet.append(["Posting Date", "Voucher Type", "Voucher", "Amount Excluding VAT", "Recorded VAT", "GL Entries", "Category"])
		for row in data["rows"]:
			sheet.append([safe(row.get(k)) for k in ("posting_date", "voucher_type", "voucher_no", "base", "vat", "gl_entries", "category")])
		extra.append(sheet)
	opening = workbook.create_sheet("VAT Opening Entries")
	opening.append(LABELS)
	for row in ordered(result.get("opening_entries", [])):
		opening.append([safe(row.get(k)) for k in FIELDS])
	for sheet in (summary, ledger, opening, *extra):
		if sheet != summary:
			sheet.auto_filter.ref = sheet.dimensions
		sheet.freeze_panes = "A2"
		for row in sheet:
			for cell in row:
				cell.alignment = Alignment(vertical="top", wrap_text=True)
				if isinstance(cell.value, (int, float)):
					cell.number_format = '#,##0.00;[Red](#,##0.00)'
		for cell in sheet[1]:
			cell.font = Font(bold=True)
		for col in sheet.columns:
			sheet.column_dimensions[col[0].column_letter].width = 30
		sheet.column_dimensions['A'].width = 52 if sheet == summary else 20
		sheet.sheet_properties.pageSetUpPr.fitToPage = True
		sheet.page_setup.fitToWidth = 1
		sheet.page_setup.fitToHeight = 0
		sheet.print_area = sheet.dimensions
