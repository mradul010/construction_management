import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today


AMOUNT_TOLERANCE = 0.0001
CANCEL_REMARK = "Cancelled because RA Bill was cancelled"


class RetentionRecord(Document):
	def validate(self):
		self._validate_amounts()
		self._set_balance_and_status()

	def _validate_amounts(self):
		if flt(self.gross_amount) < 0:
			frappe.throw(_("Gross Amount cannot be negative."))

		if flt(self.retention_amount) < 0:
			frappe.throw(_("Retention Amount cannot be negative."))

		if flt(self.released_amount) < 0:
			frappe.throw(_("Released Amount cannot be negative."))

		if flt(self.released_amount) > flt(self.retention_amount) + AMOUNT_TOLERANCE:
			frappe.throw(_("Released Amount cannot be greater than Retention Amount."))

	def _set_balance_and_status(self):
		retention_amount = flt(self.retention_amount)
		released_amount = flt(self.released_amount)

		self.gross_amount = flt(self.gross_amount)
		self.retention_amount = retention_amount
		self.released_amount = released_amount
		self.balance_amount = max(0, retention_amount - released_amount)

		if self.status == "Cancelled":
			return

		if released_amount <= 0:
			self.status = "Held"
		elif released_amount < retention_amount:
			self.status = "Partially Released"
		else:
			self.status = "Released"

	@frappe.whitelist()
	def release_retention(self, release_amount, release_date=None, remarks=None):
		release_amount = flt(release_amount)
		if release_amount <= 0:
			frappe.throw(_("Release Amount must be greater than 0."))

		if self.status == "Cancelled":
			frappe.throw(_("Cannot release retention from a Cancelled Retention Record."))

		balance_amount = flt(self.balance_amount)
		if not balance_amount:
			balance_amount = max(0, flt(self.retention_amount) - flt(self.released_amount))

		if release_amount > balance_amount + AMOUNT_TOLERANCE:
			frappe.throw(_("Release Amount cannot be greater than Balance Amount."))

		self.released_amount = flt(self.released_amount) + release_amount
		self.release_date = getdate(release_date) if release_date else today()
		if remarks:
			self.remarks = _append_remark(self.remarks, remarks)

		self.save()
		return {
			"name": self.name,
			"released_amount": self.released_amount,
			"balance_amount": self.balance_amount,
			"status": self.status,
		}


def sync_from_ra_bill(ra_bill, sales_invoice=None):
	if flt(ra_bill.retention_amount) <= 0:
		return None

	record_name = frappe.db.get_value("Retention Record", {"ra_bill": ra_bill.name}, "name")
	if record_name:
		record = frappe.get_doc("Retention Record", record_name)
	else:
		record = frappe.new_doc("Retention Record")
		record.ra_bill = ra_bill.name
		record.released_amount = 0

	record.project = ra_bill.project
	record.customer = ra_bill.customer
	record.boq = ra_bill.boq
	record.sales_invoice = sales_invoice or ra_bill.sales_invoice
	record.retention_percent = ra_bill.retention_percent
	record.gross_amount = ra_bill.gross_amount
	record.retention_amount = ra_bill.retention_amount

	if record_name:
		record.save(ignore_permissions=True)
	else:
		record.insert(ignore_permissions=True)

	return record.name


def set_sales_invoice_for_ra_bill(ra_bill, sales_invoice):
	record_name = frappe.db.get_value("Retention Record", {"ra_bill": ra_bill.name}, "name")
	if not record_name:
		return sync_from_ra_bill(ra_bill, sales_invoice=sales_invoice)

	frappe.db.set_value(
		"Retention Record",
		record_name,
		"sales_invoice",
		sales_invoice,
		update_modified=True,
	)
	return record_name


def mark_cancelled_from_ra_bill(ra_bill):
	record_name = frappe.db.get_value("Retention Record", {"ra_bill": ra_bill.name}, "name")
	if not record_name:
		return None

	record = frappe.get_doc("Retention Record", record_name)
	record.status = "Cancelled"
	record.remarks = _append_remark(record.remarks, CANCEL_REMARK)
	record.save(ignore_permissions=True)
	return record.name


def _append_remark(existing, remark):
	remark = (remark or "").strip()
	if not remark:
		return existing

	existing = (existing or "").strip()
	if not existing:
		return remark

	if remark in existing:
		return existing

	return f"{existing}\n{remark}"
