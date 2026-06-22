import frappe
from frappe.model.document import Document


class BOQ(Document):

	def validate(self):
		self._fill_parent_categories()
		self._calculate_item_unit_costs()
		self._calculate_totals()

	def _fill_parent_categories(self):
		for row in self.items:
			if row.boq_category:
				parent = frappe.db.get_value(
					"BOQ Category", row.boq_category, "parent_node"
				)
				if parent:
					row.boq_parent_category = frappe.db.get_value(
						"BOQ Category", parent, "category_name"
					) or parent
				else:
					row.boq_parent_category = frappe.db.get_value(
						"BOQ Category", row.boq_category, "category_name"
					) or row.boq_category

	def _calculate_item_unit_costs(self):
		"""
		cost_components is a direct child table of BOQ (not BOQ Item) to work
		around Frappe v16's explicit non-support for nested child tables.
		Each component row carries a boq_item field storing the BOQ Item row name.
		We group by boq_item and sum amounts to set unit_cost on each item row.
		"""
		all_components = self.cost_components or []
		for row in self.items:
			components = [c for c in all_components if c.boq_item == row.name]
			if components:
				row.unit_cost = sum(float(getattr(c, "amount", 0) or 0) for c in components)

	def _calculate_totals(self):
		grand_total = 0
		total_cost = 0

		for row in self.items:
			unit_cost = float(row.unit_cost or 0)
			margin_percent = float(row.margin_percent or 0)
			qty = float(row.qty or 0)

			row.unit_rate = unit_cost * (1 + margin_percent / 100)
			row.amount = qty * row.unit_rate

			total_cost += qty * unit_cost
			grand_total += row.amount

		self.total_cost = total_cost
		self.grand_total = grand_total
		self.total_margin = grand_total - total_cost
		self.margin_percent = (
			(grand_total - total_cost) / grand_total * 100
		) if grand_total else 0
		self.rate_per_bua = (
			grand_total / float(self.built_up_area)
		) if self.built_up_area else 0

	def on_submit(self):
		self.db_set("status", "Submitted")

	def on_cancel(self):
		self.db_set("status", "Cancelled")

	def on_amend(self):
		self.revision_no = (self.revision_no or 1) + 1
		self.status = "Draft"
		self.append("revisions", {
			"revision_no": self.revision_no,
			"revision_date": frappe.utils.today(),
			"revised_by": frappe.session.user,
			"remarks": "Amended from " + (self.amended_from or "")
		})
