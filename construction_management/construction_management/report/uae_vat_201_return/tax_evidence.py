"""Approved customs/other documentary tax amounts which have no VAT GL source."""
import frappe
from frappe import _

from construction_management.construction_management.report.uae_vat_201_return import engine
from construction_management.construction_management.report.uae_vat_201_return.filing import EvidenceRecord, decimal_value

BOXES = {"Customs import": "6", "Import adjustment": "7", "Imported services reverse charge": "3", "Tourist refund": "2"}


class TaxEvidenceRecord(EvidenceRecord):
	def validate(self):
		super().validate()
		if self.supply_type not in BOXES or not self.tax_date:
			frappe.throw(_("Select a supported documentary supply type and reviewed tax date"))
		if not self.overlap_checked or not self.overlap_basis:
			frappe.throw(_("Confirm with evidence that this tax is not already counted in invoice or GL VAT"))
		base, vat = decimal_value(self.taxable_base), decimal_value(self.vat_amount)
		if base * vat < 0:
			frappe.throw(_("Documentary taxable base and VAT must have consistent signs"))
		if self.supply_type == "Tourist refund":
			if base > 0 or vat >= 0:
				frappe.throw(_("Tourist refunds require negative documentary VAT"))
		elif not self.recovery_confirmed or not 0 <= decimal_value(self.recovery_percent) <= 100:
			frappe.throw(_("Explicit input recovery review is required, including for zero recovery"))

	def before_submit(self):
		super().before_submit()
		frappe.db.sql("select name from `tabCompany` where name=%s for update", self.company)
		if frappe.db.exists("VAT 201 Tax Evidence", {"company": self.company, "source_reference": self.source_reference, "docstatus": 1}):
			frappe.throw(_("This external tax document has already been included"))


def events_for(doc):
	"""Values come directly from reviewed documents, never an assumed rate."""
	box = BOXES[doc["supply_type"]]
	source = dict(company=doc["company"], voucher_type="VAT 201 Tax Evidence", voucher_no=doc["name"],
		source_row=doc["name"], posting_date=None, base=doc["taxable_base"], raw_vat=doc["vat_amount"],
		currency="AED", tax_account=None, recorded_in_gl=False, treatment="Approved documentary VAT outside GL",
		source_reference=doc["source_reference"])
	rule = frappe._dict(box=box, tax_date=doc["tax_date"], approved_by=doc["approved_by"], approval_time=doc["approved_on"],
		reason=doc["reason"], supporting_reference=doc["supporting_evidence"], override_base=1,
		taxable_base_aed=doc["taxable_base"], recovery_confirmed=doc.get("recovery_confirmed"), recovery_percent=doc.get("recovery_percent"))
	events = []
	for selected in ([box, "10"] if box != "2" else [box]):
		event, error = engine.apply_rule(source, frappe._dict(rule, box=selected), "AED")
		if error:
			frappe.throw(_(error))
		event["display_remarks"] = "Documentary amount outside VAT GL; duplicate check: " + doc["overlap_basis"]
		events.append(event)
	return events


def load(result):
	header = result.get("header", {})
	if not all(header.get(k) for k in ("company", "from_date", "to_date")) or not frappe.db.exists("DocType", "VAT 201 Tax Evidence"):
		return []
	if not frappe.has_permission("VAT 201 Tax Evidence", "read"):
		result["warnings"].append("Documentary VAT evidence is restricted; return scope is incomplete")
		result["scope_incomplete"] = True
		return []
	rows = frappe.get_list("VAT 201 Tax Evidence", filters={"company": header["company"], "tax_date": ["between", [header["from_date"], header["to_date"]]], "docstatus": 1}, fields=["*"], limit_page_length=0)
	return [event for row in rows for event in events_for(row)]
