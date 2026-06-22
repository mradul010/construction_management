import frappe
from frappe.model.document import Document


class BOQItem(Document):
	def calculate(self):
		self.unit_rate = (self.material_rate + self.labour_rate) * (1 + (self.margin_percent or 0) / 100)
		self.amount = (self.qty or 0) * self.unit_rate
