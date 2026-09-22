from frappe.model.document import Document
from frappe.utils import flt


class ConstructionActivityItem(Document):
	def validate(self):
		self.total_weight = flt(self.qty) * flt(self.unit_weight)
