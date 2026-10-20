import csv
import io
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, escape_html

from construction_management.construction_management.report.uae_vat_201_return.engine import build, OUTPUT, INPUT


def get_columns():
	columns = [dict(fieldname="box",label=_("Box No."),fieldtype="Data",width=80),
		dict(fieldname="description",label=_("Description"),fieldtype="Data",width=420)]
	for key,label in (("amount","Amount (AED)"),("vat_amount","VAT Amount (AED)"),("adjustment","Adjustment (AED)"),
		("ledger_amount","Ledger VAT (AED)"),("difference","Difference (AED)"),("observed_vat","Unclassified Source Tax (AED)")):
		columns.append(dict(fieldname=key,label=_(label),fieldtype="Currency",options="currency",width=150))
	for key,label,kind,options in (("tax_date","Tax Date","Date",None),("posting_date","Posting Date","Date",None),
		("voucher_type","Voucher Type","Link","DocType"),("voucher_no","Voucher Number","Dynamic Link","voucher_type"),
		("party","Customer / Supplier","Data",None),("tax_rate","VAT Rate","Percent",None),
		("emirate","Emirate","Data",None),("account","Account","Link","Account"),("tax_account","Tax Account","Link","Account"),
		("source_row","Source Row ID","Data",None),("supporting_reference","Evidence","Data",None),("company","Company","Link","Company")):
		columns.append(dict(fieldname=key,label=_(label),fieldtype=kind,options=options,width=160))
	columns.append(dict(fieldname="currency",label=_("Currency"),fieldtype="Data",hidden=1))
	return columns


def execute(filters=None):
	result = build(filters)
	rows = []
	by_box = defaultdict(list)
	for event in result["events"]:
		by_box[event["box"]].append(event)
	lookup = {b["box"]:b for b in result["boxes"]}
	detailed = result["filters"].get("view_type") == "Detailed"
	for section, label, keys in (("outputs","VAT on Sales and All Other outputs",OUTPUT+["8"]),
		("inputs","VAT on Expenses and All Other Inputs",INPUT+["11"]),("net","Net VAT Due",["12","13","14"])):
		rows.append(dict(row_id=section,description=_(label),is_group=1,indent=0,_section=True))
		for key in keys:
			box = dict(lookup[key],row_id="box_"+key,parent_id=section,indent=1,is_group=1,_box=True)
			if not result["filters"].show_zero and key not in ("8","11","12","13","14") and not any(box[k] for k in ("amount","vat_amount","adjustment")):
				continue
			rows.append(box)
			if detailed:
				for index,event in enumerate(by_box[key]):
					rows.append(dict(event,row_id=f"event_{key}_{index}",parent_id="box_"+key,indent=2,description=event["voucher_no"],_event=True))
	rows.append(dict(row_id="reconciliation",description=_("Tax Reconciliation"),is_group=1,_section=True))
	for index,rec in enumerate(result["reconciliation"]):
		rows.append(dict(rec,row_id=f"rec_{index}",parent_id="reconciliation",indent=1,vat_amount=rec["report_amount"]))
	rows.append(dict(row_id="reviews",description=_("VAT Classification Review"),is_group=1,_section=True))
	for index,review in enumerate(result["reviews"]):
		rows.append(dict(voucher_type=review["voucher_type"],voucher_no=review["voucher_no"],source_row=review["source_row"],
			posting_date=review["posting_date"],tax_account=review.get("tax_account"),company=result["header"]["company"],currency="AED",
			description=review["review"],observed_vat=flt(review.get("raw_vat")) if result["header"]["base_currency"]=="AED" else None,row_id=f"review_{index}",parent_id="reviews",indent=1,_review=True))
	header = result["header"]
	metadata = " | ".join(f"{label}: {escape_html(str(header.get(key) or 'Not Configured'))}" for key,label in
		(("company","Company"),("trn","TRN"),("from_date","From"),("to_date","To"),("stagger","Stagger"),("due_date","Due Date")))
	message = f"<strong>{escape_html(result['status'])}</strong><br>{metadata}<br>AED | ERP-generated preparation report; not submitted to the FTA."
	if result["warnings"]:
		message += "<br>" + "<br>".join(escape_html(w) for w in result["warnings"])
	summary = [dict(label=_("Return Status"),value=result["status"],datatype="Data",indicator="Orange" if result["status"]=="Needs Review" else "Blue"),
		dict(label=_("Transactions Requiring Review"),value=len(result["reviews"]),datatype="Int")]
	return get_columns(),rows,message,None,summary,True


@frappe.whitelist()
def period_context(filters):
	from construction_management.construction_management.report.uae_vat_201_return.engine import access, settings_for, normalize, taxpayer
	f = frappe._dict(frappe.parse_json(filters) or {})
	access(f.company)
	settings = settings_for(f.company)
	f = normalize(f, settings)
	return taxpayer(f.company,settings,f)


@frappe.whitelist()
def report_context(filters):
	result = build(filters)
	return {k:result[k] for k in ("header","status","warnings")}


@frappe.whitelist()
def transactions(filters, box, fieldname=None):
	result = build(filters)
	keys = OUTPUT if box in ("8","12") else INPUT if box in ("11","13") else OUTPUT+INPUT if box=="14" else [box]
	return [e for e in result["events"] if e["box"] in keys]


def export_rows(result):
	"""Every export contains taxpayer metadata, summary, evidence and reconciliation."""
	rows = [["UAE VAT 201 RETURN",result["status"]],["ERP-generated preparation report; not submitted to the FTA."]]
	rows += [[key.replace("_"," ").title(),value or "Not Configured"] for key,value in result["header"].items()]
	rows += [["Warnings"]]+[[w] for w in result["warnings"]]
	rows += [["VAT 201 Summary"],["Box","Description","Amount (AED)","VAT Amount (AED)","Adjustment (AED)"]]
	rows += [[b[k] for k in ("box","description","amount","vat_amount","adjustment")] for b in result["boxes"]]
	fields = ("box","tax_date","posting_date","voucher_type","voucher_no","party","amount","vat_amount","adjustment","nonrecoverable","tax_rate","classification","emirate","account","tax_account","source_row","supporting_reference","reason","company","currency","source_currency","base_currency","aed_exchange_rate","source_taxable_amount")
	rows += [["Transaction Details"],list(fields)]+[[e.get(k) for k in fields] for e in result["events"]]
	rows += [["Tax Reconciliation"],["Description","Report Amount","Ledger Amount","Difference"]]
	rows += [[r[k] for k in ("description","report_amount","ledger_amount","difference")] for r in result["reconciliation"]]
	rows += [["Classification Review"],["Voucher Type","Voucher","Source Row","Review","Source Tax (AED, unclassified)"]]
	rows += [[r[k] for k in ("voucher_type","voucher_no","source_row","review")]+[flt(r.get("raw_vat")) if result["header"].get("base_currency")=="AED" else None] for r in result["reviews"]]
	rows += [["Approved Outside VAT Exclusions"],["Voucher Type","Voucher","Source Row","Reason","Evidence"]]
	rows += [[e.get(k) for k in ("voucher_type","voucher_no","source_row","reason","supporting_reference")] for e in result.get("excluded",[])]
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
		letter = column[0].column_letter
		sheet.column_dimensions[letter].width = min(55,max(16,max(len(str(c.value or "")) for c in column)+2))
		for cell in column:
			if isinstance(cell.value,(int,float)):
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
