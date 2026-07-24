import frappe


def execute():
	if not frappe.db.table_exists("Drawing Register"):
		return

	meta = frappe.get_meta("Drawing Register")
	fields = {df.fieldname for df in meta.fields}

	values = {}
	if "revision_number" in fields:
		values["revision_number"] = "REV0"
	if "current_revision" in fields:
		values["current_revision"] = "REV0"
	if "revision_count" in fields:
		values["revision_count"] = 1

	if values:
		filters = []
		if "revision_number" in fields:
			filters.append("revision_number is null or revision_number = ''")
		elif "current_revision" in fields:
			filters.append("current_revision is null or current_revision = ''")
		if filters:
			frappe.db.sql(
				f"""
				update `tabDrawing Register`
				set {", ".join(f"`{fieldname}` = %s" for fieldname in values)}
				where {" or ".join(filters)}
				""",
				tuple(values.values()),
			)

	if {"current_status", "ifc_status"}.issubset(fields):
		frappe.db.sql(
			"""
			update `tabDrawing Register`
			set current_status = 'IFC', ifc_status = 1
			where current_status = 'Issued For Construction'
			"""
		)

	for doctype in (
		"Drawing Review",
		"Drawing Approval",
		"Drawing Distribution",
		"Design Issue",
		"Request For Information",
		"Design Change Request",
		"Design NCR",
		"Drawing Transmittal",
	):
		if not frappe.db.table_exists(doctype):
			continue
		meta = frappe.get_meta(doctype)
		if not meta.has_field("revision_number") or not meta.has_field("drawing"):
			continue
		frappe.db.sql(
			f"""
			update `tab{doctype}` target
			join `tabDrawing Register` drawing on drawing.name = target.drawing
			set target.revision_number = drawing.revision_number
			where target.drawing is not null
				and target.drawing != ''
				and (target.revision_number is null or target.revision_number = '')
			"""
		)
