import hashlib

import frappe
from frappe.utils import cint


RA_BILL_VISIBLE_PREFIX = "RAB-"
RA_BILL_VISIBLE_DIGITS = 3


def execute():
	if not frappe.db.has_column("RA Bill", "ra_bill_no"):
		return

	projects = frappe.db.sql(
		"""
		SELECT DISTINCT project
		FROM `tabRA Bill`
		WHERE COALESCE(project, '') != ''
		ORDER BY project
		""",
		as_dict=True,
	)

	for row in projects:
		renumber_project_ra_bills(row.project)

	frappe.db.add_unique(
		"RA Bill",
		["project", "ra_bill_no"],
		constraint_name="unique_project_ra_bill_no",
	)
	frappe.clear_cache(doctype="RA Bill")


def renumber_project_ra_bills(project):
	ra_bills = frappe.db.sql(
		"""
		SELECT name
		FROM `tabRA Bill`
		WHERE project = %s
		ORDER BY
			CASE WHEN COALESCE(bill_no, 0) > 0 THEN 0 ELSE 1 END,
			COALESCE(bill_no, 0),
			creation,
			name
		""",
		project,
		as_dict=True,
	)

	for index, row in enumerate(ra_bills, start=1):
		frappe.db.set_value(
			"RA Bill",
			row.name,
			{
				"bill_no": index,
				"ra_bill_no": format_ra_bill_no(index),
			},
			update_modified=False,
		)

	seed_project_series(project, len(ra_bills))


def format_ra_bill_no(sequence):
	return f"{RA_BILL_VISIBLE_PREFIX}{cint(sequence):0{RA_BILL_VISIBLE_DIGITS}d}"


def get_project_series_key(project):
	project_hash = hashlib.sha1(str(project or "").encode()).hexdigest()[:12]
	return f"RA-BILL-{project_hash}-"


def seed_project_series(project, current):
	frappe.db.sql(
		"""
		INSERT INTO `tabSeries` (`name`, `current`)
		VALUES (%s, %s)
		ON DUPLICATE KEY UPDATE `current` = GREATEST(`current`, VALUES(`current`))
		""",
		(get_project_series_key(project), cint(current)),
	)
