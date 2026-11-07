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
	return [dict(description=label, amount=ledger.get(key), currency=ledger.get("currency")) for key, label in MEASURES]


def columns():
	return [dict(fieldname="description", label="Measure", fieldtype="Data", width=420),
		dict(fieldname="amount", label="Amount", fieldtype="Currency", options="currency", width=200),
		dict(fieldname="currency", fieldtype="Data", hidden=1)]


def cards(result):
	return [dict(label=row["description"], value=row["amount"] if row["amount"] is not None else "Not Available",
		datatype="Currency" if row["amount"] is not None else "Data", currency=row["currency"], precision=2,
		provisional=False) for row in summary_rows(result)[:3]]


def export_rows(result):
	h = result["header"]
	currency = result.get("ledger_summary", {}).get("currency")
	return [["VAT per General Ledger"], ["Company", h.get("company")],
		["Posting period", h.get("from_date"), h.get("to_date")], ["Currency", currency],
		["Posted VAT account movements; internal recovery approval does not change these totals."],
		["Measure", "Amount"]] + [[r["description"], r["amount"]] for r in summary_rows(result)]


def html(result, interactive=False):
	from urllib.parse import quote
	entries = [dict(row, voucher_url="/app/" + frappe.scrub(row["voucher_type"]).replace("_", "-") + "/" + quote(row["voucher_no"], safe="")) for row in result.get("ledger_entries", [])]
	return frappe.render_template("construction_management/report/uae_vat_201_return/gl_content.html",
		dict(result=result, rows=summary_rows(result), entries=entries, interactive=interactive))


def sheets(workbook, result):
	def safe(value):
		return "'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@")) else value
	summary = workbook.create_sheet("VAT per General Ledger", 0)
	for row in export_rows(result):
		summary.append([safe(v) for v in row])
	ledger = workbook.create_sheet("VAT GL Entries", 1)
	ledger.append(LABELS)
	for row in result.get("ledger_entries", []):
		ledger.append([safe(row.get(k)) for k in FIELDS])
	ledger.auto_filter.ref = ledger.dimensions
	for sheet in (summary, ledger):
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
