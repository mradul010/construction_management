import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, fmt_money


COST_BREAKDOWN_TOLERANCE = 0.01


class BOQ(Document):

	def validate(self):
		self._ensure_component_keys()
		self._fill_parent_categories()
		self.validate_item_values()
		self._calculate_totals()
		self.validate_cost_breakdown_matches_unit_cost()

	def _ensure_component_keys(self):
		ref_map = {}
		for row in self.items:
			old_ref = row.name
			if not row.get("component_key"):
				row.component_key = frappe.generate_hash(length=12)
			ref_map[old_ref] = row.component_key

		for component in self.cost_components or []:
			if component.boq_item in ref_map:
				component.boq_item = ref_map[component.boq_item]

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

	def validate_item_values(self):
		for row in self.items:
			item = row.item_name or row.item or row.name

			if flt(row.qty) <= 0:
				frappe.throw(_("Qty for item {0} must be greater than 0.").format(item))

			if flt(row.margin_percent) < 0:
				frappe.throw(_("Margin % for item {0} cannot be negative.").format(item))

			if flt(row.unit_cost) < 0 or flt(row.unit_rate) < 0:
				frappe.throw(_("Unit Cost/Rate for item {0} cannot be negative.").format(item))

	def validate_cost_breakdown_matches_unit_cost(self):
		all_components = self.cost_components or []

		for row in self.items:
			component_key = row.get("component_key") or row.name
			components = [
				component
				for component in all_components
				if component.boq_item in (component_key, row.name)
			]
			if not components:
				continue

			unit_cost = flt(row.unit_cost)
			breakdown_total = sum(flt(component.amount) for component in components)
			difference = unit_cost - breakdown_total

			if abs(difference) > COST_BREAKDOWN_TOLERANCE:
				item = row.item_name or row.item or row.name
				frappe.throw(
					_(
						"Cost Breakdown Mismatch for item {0}.<br>"
						"Unit Cost: {1}<br>"
						"Cost Breakdown Total: {2}<br>"
						"Difference: {3}<br>"
						"Cost Breakdown must match Unit Cost only. "
						"It must not include quantity, margin, or total amount."
					).format(
						item,
						self._format_currency(unit_cost),
						self._format_currency(breakdown_total),
						self._format_currency(abs(difference)),
					),
					title=_("Cost Breakdown Mismatch"),
				)

	def _format_currency(self, value):
		return fmt_money(flt(value), currency=self.currency or "AED")

	def _calculate_totals(self):
		grand_total = 0
		total_cost = 0

		for row in self.items:
			unit_cost = flt(row.unit_cost)
			margin_percent = flt(row.margin_percent)
			qty = flt(row.qty)

			row.unit_rate = unit_cost * (1 + margin_percent / 100)
			row.amount = qty * unit_cost
			row.amount_after_margin = qty * flt(row.unit_rate)

			total_cost += row.amount
			grand_total += row.amount_after_margin

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
