import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cint, flt, getdate, now_datetime


def setup():
	for name in ("vat_201_filing_period", "vat_201_classification"):
		frappe.reload_doc("construction_management", "doctype", name)
	fields = [
		("custom_vat201_periods", "Table", "VAT 201 Filing Periods", "VAT 201 Filing Period"),
		("custom_vat201_classifications", "Table", "VAT 201 Classifications", "VAT 201 Classification"),
		("custom_vat201_legal_name_english", "Data", "Registered Legal Name in English", None),
		("custom_vat201_registration_date", "Date", "VAT Registration Date", None),
		("custom_vat201_registered_emirate", "Select", "Registered Emirate", "\nAbu Dhabi\nDubai\nSharjah\nAjman\nUmm Al Quwain\nRas Al Khaimah\nFujairah"),
		("custom_vat201_legal_name_arabic", "Data", "Legal Name in Arabic", None),
		("custom_vat201_signatory_english", "Data", "Signatory Name in English", None),
		("custom_vat201_signatory_arabic", "Data", "Signatory Name in Arabic", None),
		("custom_vat201_mobile_code", "Data", "Mobile Country Code", None),
		("custom_vat201_mobile", "Data", "Mobile Number", None),
		("custom_vat201_email", "Data", "Signatory Email", None),
	]
	create_custom_fields({
		"UAE VAT Settings": [dict(fieldname=n, fieldtype=t, label=l, options=o, module="Construction Management") for n,t,l,o in fields],
		"UAE VAT Account": [dict(fieldname="custom_vat201_side", fieldtype="Select", label="VAT Ledger Side", options="\nOutput\nInput\nBoth", in_list_view=1, module="Construction Management")],
	})
	# Keep optional evidence references; the standard invoice fields hold the decisions.
	create_custom_fields({
		"Sales Invoice": [
			dict(fieldname="custom_vat201_evidence_reference",label="VAT Source Evidence Reference",fieldtype="Data",insert_after="vat_emirate",module="Construction Management"),
		],
		"Purchase Invoice": [
			dict(fieldname="custom_vat201_evidence_reference",label="VAT Source Evidence Reference",fieldtype="Data",insert_after="recoverable_standard_rated_expenses",module="Construction Management"),
		],
	})
	hide_legacy_sales_emirate_fields()
	hide_legacy_purchase_recovery_fields()
	from construction_management.construction_management.report.uae_vat_201_return.purchase_recovery import setup as setup_recovery
	setup_recovery()
	from frappe.permissions import add_permission, update_permission_property
	for role in ("Accounts Manager", "System Manager", "Accounts User", "Auditor"):
		add_permission("UAE VAT Settings", role, 0)
		update_permission_property("UAE VAT Settings", role, 0, "read", 1)
		if role in ("Accounts Manager", "System Manager"):
			for action in ("write", "create"):
				update_permission_property("UAE VAT Settings", role, 0, action, 1)
			add_permission("UAE VAT Settings", role, 1)
			for action in ("read", "write"):
				update_permission_property("UAE VAT Settings", role, 1, action, 1)
	frappe.reload_doc("construction_management", "report", "uae_vat_201_return")


def hide_legacy_sales_emirate_fields():
	"""Hide obsolete controls, retaining their definitions, columns and saved values."""
	names = frappe.get_all("Custom Field", filters={"dt": "Sales Invoice", "fieldname": ["in", [
		"custom_vat201_supply_verified", "custom_vat201_supply_emirate",
	]]}, pluck="name")
	for name in names:
		frappe.db.set_value("Custom Field", name, "hidden", 1, update_modified=False)
	if names:
		frappe.clear_cache(doctype="Sales Invoice")
	return names


def hide_legacy_purchase_recovery_fields():
	"""Retain historical values but hide the redundant recovery controls."""
	names = frappe.get_all("Custom Field", filters={"dt": "Purchase Invoice", "fieldname": ["in", [
		"custom_vat201_recovery_verified", "custom_vat201_recovery_percent",
	]]}, pluck="name")
	for name in names:
		frappe.db.set_value("Custom Field", name, "hidden", 1, update_modified=False)
	if names:
		frappe.clear_cache(doctype="Purchase Invoice")
	return names


def validate_settings(doc, method=None):
	previous = doc.get_doc_before_save()
	old = {r.name: r.as_dict() for r in previous.get("custom_vat201_classifications", [])} if previous else {}
	keys = set()
	manager = bool(set(frappe.get_roles()) & {"Accounts Manager", "System Manager"})
	if not manager and any(r.get("approved") and name not in {row.name for row in doc.get("custom_vat201_classifications", [])} for name,r in old.items()):
		frappe.throw(_("Only Accounts Managers may remove approved VAT classifications"), frappe.PermissionError)
	for account in doc.uae_vat_accounts:
		if frappe.get_cached_value("Account", account.account, "company") != doc.company:
			frappe.throw(_("VAT accounts must belong to the configured Company"))
	for period in doc.get("custom_vat201_periods", []):
		if not period.from_date or not period.to_date or getdate(period.from_date) > getdate(period.to_date):
			frappe.throw(_("Each VAT filing period requires valid start and end dates"))
		if doc.get("custom_vat201_registration_date") and getdate(period.from_date) < getdate(doc.custom_vat201_registration_date):
			frappe.throw(_("VAT filing periods cannot start before the VAT registration date"))
		if period.frequency=="Quarterly" and not 1 <= cint(period.quarter_number) <= 4:
			frappe.throw(_("Quarterly filing periods require an explicitly configured VAT Quarter Number from 1 to 4"))
		for other in doc.get("custom_vat201_periods", []):
			if other is not period and getdate(period.from_date) <= getdate(other.to_date) and getdate(other.from_date) <= getdate(period.to_date):
				frappe.throw(_("VAT filing periods cannot overlap"))
		old_period = next((p for p in previous.get("custom_vat201_periods", []) if p.name==period.name), None) if previous else None
		if period.status in ("Ready for Approval","Approved","Filed") and (not old_period or old_period.status != period.status):
			if not manager:
				frappe.throw(_("Only Accounts Managers may change the VAT return approval state"), frappe.PermissionError)
			from construction_management.construction_management.report.uae_vat_201_return.engine import build
			result = build(dict(company=doc.company,from_date=str(period.from_date),to_date=str(period.to_date)), settings_override=doc)
			if result["warnings"] or result["reviews"]:
				frappe.throw(_("VAT return has unresolved classification or reconciliation issues and cannot be approved or filed"))
			if period.status == "Approved":
				period.return_approved_by, period.return_approved_on = frappe.session.user, now_datetime()
			if period.status == "Filed" and (not old_period or old_period.status!="Approved" or not period.submission_date or not period.filing_reference):
				frappe.throw(_("Filed requires a previously approved return, explicit submission date and FTA filing receipt reference"))
	for row in doc.get("custom_vat201_classifications", []):
		if not row.approved:
			if old.get(row.name, {}).get("approved") and not manager:
				frappe.throw(_("Only Accounts Managers may revoke a VAT approval"), frappe.PermissionError)
			row.approved_by = row.approval_time = None
			if row.get("review_status") not in ("Rejected","Needs Review"):
				row.review_status = "Pending Review"
			continue
		row.review_status = "Approved"
		if row.voucher_type not in ("Sales Invoice", "Purchase Invoice", "POS Invoice", "Journal Entry", "Payment Entry"):
			frappe.throw(_("Unsupported VAT supporting voucher type"))
		if not all((row.voucher_no, row.source_row, row.box, row.tax_date, row.reason, row.supporting_reference)):
			frappe.throw(_("Approved VAT classifications require a voucher, source row, box, tax date, reason and evidence"))
		voucher = frappe.get_doc(row.voucher_type, row.voucher_no)
		voucher.check_permission("read")
		if voucher.docstatus != 1 or voucher.company != doc.company:
			frappe.throw(_("VAT classifications must reference submitted vouchers in this Company"))
		if row.voucher_type in ("Sales Invoice","Purchase Invoice","POS Invoice"):
			valid_rows = {r.name for r in list(voucher.get("items", []))+list(voucher.get("taxes", []))}
			if row.source_row not in valid_rows:
				frappe.throw(_("Source Row must belong to the referenced invoice"))
		else:
			gl = frappe.db.get_value("GL Entry", row.source_row, ["voucher_type","voucher_no","company","docstatus","is_cancelled"], as_dict=True)
			if not gl or (gl.voucher_type,gl.voucher_no,gl.company,gl.docstatus,gl.is_cancelled) != (row.voucher_type,row.voucher_no,doc.company,1,0):
				frappe.throw(_("Source Row must be an active submitted GL Entry of the supporting voucher"))
		if row.box!="Outside VAT" and frappe.get_cached_value("Company",doc.company,"default_currency") != "AED" and flt(row.aed_exchange_rate) <= 0:
			frappe.throw(_("Non-AED companies require a reviewed AED exchange rate for each tax event"))
		if row.box in ("9", "10") and (not row.recovery_confirmed or not 0 <= flt(row.recovery_percent) <= 100):
			frappe.throw(_("Input VAT requires explicit recoverability review and a percentage from 0 to 100"))
		if row.is_adjustment and (not row.adjustment_type or row.box not in ("1a","1b","1c","1d","1e","1f","1g","9")):
			frappe.throw(_("The Adjustment column is supported only for Boxes 1a-1g and 9; use Box 7 for import adjustments"))
		if row.is_adjustment:
			from construction_management.construction_management.report.uae_vat_201_return.engine import INPUT_ADJUSTMENTS, OUTPUT_ADJUSTMENTS
			if row.adjustment_type not in (INPUT_ADJUSTMENTS if row.box=="9" else OUTPUT_ADJUSTMENTS):
				frappe.throw(_("Ordinary VAT corrections use the VAT Amount column. Select a permitted bad-debt, property, annual-apportionment or capital-assets adjustment treatment."))
		side = "Input" if row.box in ("9", "10") else "Output"
		key = (row.voucher_type, row.voucher_no, row.source_row, "GL" if row.voucher_type in ("Journal Entry","Payment Entry") else side)
		if key in keys:
			frappe.throw(_("A source tax event cannot be classified twice on the same VAT side"))
		keys.add(key)
		if any(k[:3]==key[:3] and k!=key for k in keys) and (row.box=="Outside VAT" or any(r.approved and r.box=="Outside VAT" and (r.voucher_type,r.voucher_no,r.source_row)==key[:3] for r in doc.get("custom_vat201_classifications", []))):
			frappe.throw(_("An Outside VAT exclusion cannot coexist with a VAT classification of the same source"))
		review_fields = ("voucher_type","voucher_no","source_row","box","tax_date","recovery_confirmed","recovery_percent","override_base","taxable_base_aed","aed_exchange_rate","is_adjustment","adjustment_type","reason","supporting_reference","approved","source_fingerprint","source_evidence","journal_treatment")
		changed = any(row.get(k) != old.get(row.name, {}).get(k) for k in review_fields)
		if changed:
			if not manager:
				frappe.throw(_("Only Accounts Managers may approve or change approved VAT classifications"), frappe.PermissionError)
			row.approved_by, row.approval_time = frappe.session.user, now_datetime()
		else:
			row.approved_by, row.approval_time = old[row.name].get("approved_by"), old[row.name].get("approval_time")
