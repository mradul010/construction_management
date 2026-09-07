import frappe


SELF_LINK_FIELDS = ("original_boq", "parent_boq", "superseded_by")


def execute():
	"""Prevent standard BOQ duplicates from acting like revision dependencies."""
	for fieldname in SELF_LINK_FIELDS:
		frappe.db.set_value(
			"DocField",
			{"parent": "BOQ", "fieldname": fieldname},
			"no_copy",
			1,
		)

	duplicates = frappe.db.sql(
		"""
		SELECT name, original_boq
		FROM `tabBOQ`
		WHERE COALESCE(original_boq, '') != ''
		  AND original_boq != name
		  AND COALESCE(is_revision, 0) = 0
		  AND (parent_boq IS NULL OR parent_boq = '')
		""",
		as_dict=True,
	)
	for boq in duplicates:
		frappe.db.set_value(
			"BOQ",
			boq.name,
			{
				"original_boq": boq.name,
				"parent_boq": None,
				"superseded_by": None,
				"is_revision": 0,
				"is_active_revision": 0,
			},
			update_modified=False,
		)

	frappe.clear_cache(doctype="BOQ")
