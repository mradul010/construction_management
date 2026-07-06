from frappe.model.document import Document
from frappe.utils import flt


class BOQItem(Document):
	def validate(self):
		self.calculate()

	def calculate(self):
		unit_cost = flt(self.unit_cost)
		margin_percent = flt(self.margin_percent)
		qty = flt(self.qty)

		self.unit_rate = unit_cost * (1 + margin_percent / 100)
		self.amount = qty * unit_cost
		self.amount_after_margin = qty * flt(self.unit_rate)
