import frappe
from frappe.model.document import Document


class ConstructionCompanySettings(Document):
	def validate(self):
		if self.company:
			self.country = frappe.db.get_value("Company", self.company, "country")
