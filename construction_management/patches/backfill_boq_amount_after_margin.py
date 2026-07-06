import frappe


def execute():
	if not frappe.db.table_exists("BOQ Item") or not frappe.db.table_exists("BOQ"):
		return

	if not frappe.db.has_column("BOQ Item", "amount_after_margin"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabBOQ Item`
		SET
			unit_rate = COALESCE(unit_cost, 0) * (1 + COALESCE(margin_percent, 0) / 100),
			amount = COALESCE(qty, 0) * COALESCE(unit_cost, 0),
			amount_after_margin = COALESCE(qty, 0)
				* (COALESCE(unit_cost, 0) * (1 + COALESCE(margin_percent, 0) / 100))
		WHERE parenttype = 'BOQ'
		  AND parentfield = 'items'
		"""
	)

	frappe.db.sql(
		"""
		UPDATE `tabBOQ` boq
		LEFT JOIN (
			SELECT
				parent,
				SUM(COALESCE(amount, 0)) AS total_cost,
				SUM(COALESCE(amount_after_margin, 0)) AS grand_total
			FROM `tabBOQ Item`
			WHERE parenttype = 'BOQ'
			  AND parentfield = 'items'
			GROUP BY parent
		) item_totals ON item_totals.parent = boq.name
		SET
			boq.total_cost = COALESCE(item_totals.total_cost, 0),
			boq.grand_total = COALESCE(item_totals.grand_total, 0),
			boq.total_margin =
				COALESCE(item_totals.grand_total, 0) - COALESCE(item_totals.total_cost, 0),
			boq.margin_percent = CASE
				WHEN COALESCE(item_totals.grand_total, 0) != 0
					THEN (
						(
							COALESCE(item_totals.grand_total, 0)
							- COALESCE(item_totals.total_cost, 0)
						) / COALESCE(item_totals.grand_total, 0)
					) * 100
				ELSE 0
			END,
			boq.rate_per_bua = CASE
				WHEN COALESCE(boq.built_up_area, 0) != 0
					THEN COALESCE(item_totals.grand_total, 0) / boq.built_up_area
				ELSE 0
			END
		"""
	)
