import csv
import io
from decimal import Decimal

import frappe
from frappe import _
from frappe.utils import escape_html, flt

from construction_management.construction_management.report.uae_vat_201_return.automatic import build, detail_remarks, PRELIMINARY
from construction_management.construction_management.report.uae_vat_201_return.engine import OUTPUT, INPUT


def get_columns():
	return [dict(fieldname="box",label=_("Box Number"),fieldtype="Data",width=100),
		dict(fieldname="description",label=_("Description"),fieldtype="Data",width=440)] + [
		dict(fieldname=key,label=_(label),fieldtype="Currency",options="currency",width=170,align="right")
		for key,label in (("amount","Amount (AED)"),("vat_amount","VAT Amount (AED)"),("adjustment","Adjustments (AED)"))
	] + [dict(fieldname="currency",fieldtype="Data",hidden=1)]


def execute(filters=None):
	result = build(filters)
	pending = result["status"] == PRELIMINARY
	rows = [dict(box,_box=True,_incomplete=pending) for box in result["boxes"]]
	header = result["header"]
	metadata = " | ".join(f"{label}: {escape_html(str(header.get(key) or 'Not Configured'))}" for key,label in (
		("legal_name_english","Legal Name"),("trn","TRN"),("registered_emirate","Registered Emirate"),
		("from_date","From"),("to_date","To"),("due_date","Due Date"),("filing_frequency","Frequency")))
	message = f"<strong>{escape_html(result['status'])}</strong><br>{metadata}"
	if result["warnings"]:
		message += "<br>" + "<br>".join(escape_html(w) for w in result["warnings"])
	boxes = {b["box"]:b for b in result["boxes"]}
	input_pending = any(r["voucher_type"]=="Purchase Invoice" for r in result["reviews"])
	journal_pending = any(r["voucher_type"] not in ("Sales Invoice","POS Invoice","Purchase Invoice") for r in result["reviews"])
	def card(label,value):
		return dict(label=_(label),value=_("Pending Verification") if value is None else value,
			datatype="Data" if value is None else "Currency",currency="AED")
	summary = [card("Sales VAT (Recorded)",result["observed"]["sales_vat"]),
		card("Recoverable Purchase VAT",None if input_pending else boxes["13"]["amount"]),
		card("VAT Adjustments",None if journal_pending else sum(b["adjustment"] * (-1 if b["box"] in INPUT else 1) for b in result["boxes"] if b["box"] in OUTPUT+INPUT)),
		card("Net VAT Payable / Refundable",None if pending else boxes["14"]["amount"])]
	return get_columns(),rows,message,None,summary,True


@frappe.whitelist()
def period_context(filters):
	from construction_management.construction_management.report.uae_vat_201_return.engine import access, settings_for, normalize, taxpayer
	f = frappe._dict(frappe.parse_json(filters) or {})
	access(f.company)
	settings = settings_for(f.company)
	f = normalize(f, settings)
	header = taxpayer(f.company,settings,f)
	header["available_periods"] = [f"{p.from_date} to {p.to_date}" for p in settings.get("custom_vat201_periods", [])]
	return header


@frappe.whitelist()
def report_context(filters):
	result = build(filters)
	# Source permissions are checked by the reader; no stored evidence snapshots are returned.
	return {key:result[key] for key in ("header","status","warnings","details","reconciliation","observed")}


@frappe.whitelist()
def transactions(filters, box, fieldname=None):
	result = build(filters)
	keys = OUTPUT if box in ("8","12") else INPUT if box in ("11","13") else OUTPUT+INPUT if box=="14" else [box]
	events = [dict(e) for e in result["events"] if e["box"] in keys]
	for event in events:
		if box in ("12","13","14") and fieldname in (None,"amount"):
			value = flt(event["vat_amount"])+flt(event["adjustment"])
			if box=="14" and event["box"] in INPUT:
				value = -value
		elif box in ("12","13","14"):
			value = 0
		else:
			value = flt(event.get(fieldname or "vat_amount"))
		event["contribution"] = value
		event["display_remarks"] = detail_remarks(event)
	return events


def export_rows(result):
	rows = [["UAE VAT 201 RETURN",result["status"]],["ERP-generated preparation report; not submitted to the FTA."]]
	rows += [[key.replace("_"," ").title(),value if value not in (None,"") else "Not Configured"] for key,value in result["header"].items()]
	rows += [["Warnings"]]+[[w] for w in result["warnings"]]
	rows += [["VAT 201 Summary"],["Box","Description","Amount (AED)","VAT Amount (AED)","Adjustment (AED)"]]
	rows += [[b["box"],b["description"]]+[
		("Pending Verification" if result["status"] == PRELIMINARY and (not b[k] or b["box"] in ("12","13","14")) else b[k]) for k in ("amount","vat_amount","adjustment")
	] for b in result["boxes"]]
	fields = ("posting_date","voucher_no","party","invoice_taxable_amount","recorded_vat_amount","treatment","vat_box","display_remarks")
	rows += [["Transaction Details"],["Date","Voucher Number","Party","Taxable Amount","VAT Amount","VAT Treatment","VAT Box","Remarks"]]
	for row in result.get("details",result["events"]):
		values = dict(row)
		values.setdefault("invoice_taxable_amount",row.get("base"))
		values.setdefault("recorded_vat_amount",row.get("raw_vat"))
		values.setdefault("vat_box",row.get("box"))
		values.setdefault("display_remarks",row.get("remarks"))
		rows.append([values.get(k) for k in fields])
	rows += [["Needs Attention"],["Voucher Type","Voucher","Source Row","Issue","Recorded VAT","Recommended Action"]]
	rows += [[r.get(k) for k in ("voucher_type","voucher_no","source_row","issue","raw_vat","recommended_action")] for r in result["reviews"]]
	rows += [["Tax Reconciliation"],["Description","Included VAT","Ledger VAT","Difference"]]
	rows += [[r[k] for k in ("description","report_amount","ledger_amount","difference")] for r in result["reconciliation"]]
	rows += [["Recorded source amounts"]]+[[k,v] for k,v in result.get("observed",{}).items()]
	rows += [["VAT Control Movement (debit - credit)",result.get("control_movement")]]
	rows += [["Invoice tax versus GL"],["Voucher Type","Voucher","VAT Account","Difference","Currency"]]
	rows += [[r.get(k) for k in ("voucher_type","voucher_no","tax_account","difference","currency")] for r in result.get("invoice_checks",[])]
	return [[("'"+v if v.startswith(("=","+","-","@")) else v) if isinstance(v,str) else v for v in row] for row in rows]


def workbook_bytes(result):
	from openpyxl import Workbook
	from openpyxl.styles import Font
	workbook = Workbook()
	precision = frappe.get_precision("GL Entry","debit",currency="AED")
	pattern = '#,##0' + ('.'+'0'*precision if precision else '')
	sheet = workbook.active
	sheet.title = "VAT 201 Preparation"
	for row in export_rows(result):
		sheet.append(row)
	for cell in sheet[1]:
		cell.font = Font(bold=True)
	sheet.freeze_panes = "C2"
	for column in sheet.columns:
		sheet.column_dimensions[column[0].column_letter].width = min(55,max(16,max(len(str(c.value or "")) for c in column)+2))
		for cell in column:
			if isinstance(cell.value,(int,float,Decimal)):
				cell.number_format = pattern+';[Red]('+pattern+')'
	output = io.BytesIO()
	workbook.save(output)
	return output.getvalue()


def pdf_bytes(result):
	from frappe.utils.pdf import get_pdf
	return get_pdf(frappe.render_template("construction_management/report/uae_vat_201_return/return_print.html",dict(result=result,precision=frappe.get_precision("GL Entry","debit",currency="AED"))),options={"page-size":"A4","margin-top":"10mm","margin-bottom":"10mm","margin-left":"10mm","margin-right":"10mm"})


@frappe.whitelist()
def download(filters, file_type="xlsx"):
	result = build(filters)
	if file_type not in ("xlsx","csv","pdf"):
		frappe.throw(_("Unsupported export format"))
	frappe.has_permission("GL Entry","print" if file_type=="pdf" else "export",throw=True)
	if file_type=="xlsx":
		content = workbook_bytes(result)
	elif file_type=="pdf":
		content = pdf_bytes(result)
	else:
		stream = io.StringIO()
		csv.writer(stream).writerows(export_rows(result))
		content = stream.getvalue().encode("utf-8-sig")
	frappe.local.response.filename = f"UAE-VAT-201-{result['header']['to_date']}.{file_type}"
	frappe.local.response.filecontent = content
	frappe.local.response.type = "pdf" if file_type=="pdf" else "binary"
