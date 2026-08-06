import re

import frappe
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.model.document import Document
from frappe.utils import now, today

DESIGN_REFERENCE_FIELDS = ("drawing", "drawing_revision", "ifc_revision")
IFC_STATUS = "Issued For Construction"
DRAWING_IFC_STATUS = "IFC"
INVALID_EXECUTION_STATUSES = {"Draft", "Rejected", "Cancelled", "Superseded"}


class DesignPackage(Document):
	def validate(self):
		if self.project and not self.company:
			self.company = frappe.db.get_value("Project", self.project, "company")


class DesignDiscipline(Document):
	def validate(self):
		if self.package:
			package = frappe.db.get_value("Design Package", self.package, ["project", "company"], as_dict=True)
			if package and not self.project:
				self.project = package.project
			if package and self.project and package.project != self.project:
				frappe.throw(_("Design Discipline package must belong to Project {0}.").format(self.project))


class DrawingRegister(Document):
	def validate(self):
		self._validate_project_links()
		self._validate_unique_drawing_number()
		self._set_revision_defaults()
		self._sync_legacy_summary_fields()

	def _validate_project_links(self):
		if self.design_package and self.project:
			project = frappe.db.get_value("Design Package", self.design_package, "project")
			if project and project != self.project:
				frappe.throw(_("Design Package must belong to Project {0}.").format(self.project))
		if self.discipline:
			discipline = frappe.db.get_value(
				"Design Discipline",
				self.discipline,
				["project", "package"],
				as_dict=True,
			)
			if discipline:
				if self.project and discipline.project and discipline.project != self.project:
					frappe.throw(_("Design Discipline must belong to Project {0}.").format(self.project))
				if self.design_package and discipline.package and discipline.package != self.design_package:
					frappe.throw(_("Design Discipline must belong to Design Package {0}.").format(self.design_package))

	def _validate_unique_drawing_number(self):
		if not self.project or not self.drawing_number:
			return
		existing = frappe.db.get_value(
			"Drawing Register",
			{"project": self.project, "drawing_number": self.drawing_number, "name": ["!=", self.name]},
			"name",
		)
		if existing:
			frappe.throw(_("Drawing Number {0} already exists for Project {1}.").format(self.drawing_number, self.project))

	def _set_revision_defaults(self):
		if not self.revision_number:
			self.revision_number = self.current_revision or "REV0"
		if not self.revision_date:
			self.revision_date = today()
		if not self.current_status:
			self.current_status = "Draft"
		if self.current_status in (DRAWING_IFC_STATUS, IFC_STATUS):
			self.current_status = DRAWING_IFC_STATUS
			self.ifc_status = 1
			if not self.ifc_date:
				self.ifc_date = today()
			if not self.ifc_by:
				self.ifc_by = frappe.session.user
		elif self.current_status in INVALID_EXECUTION_STATUSES or self.current_status != DRAWING_IFC_STATUS:
			self.ifc_status = 0
			self.ifc_date = None
			self.ifc_by = None

	def _sync_legacy_summary_fields(self):
		self.current_revision = self.revision_number
		if not self.revision_count:
			self.revision_count = 1

	def sync_revision_summary(self):
		self._sync_legacy_summary_fields()


class DrawingRevision(Document):
	def validate(self):
		self._set_drawing_context()
		self._validate_unique_revision()
		self._validate_ifc_status()
		self._validate_read_only_old_revision()

	def on_update(self):
		self.update_drawing_register()

	def _validate_unique_revision(self):
		if not self.drawing or not self.revision_number:
			return
		existing = frappe.db.get_value(
			"Drawing Revision",
			{"drawing": self.drawing, "revision_number": self.revision_number, "name": ["!=", self.name]},
			"name",
		)
		if existing:
			frappe.throw(_("Revision {0} already exists for this drawing.").format(self.revision_number))

	def _set_drawing_context(self):
		apply_drawing_context(self)

	def _validate_ifc_status(self):
		if self.status == IFC_STATUS:
			self.ifc = 1
			if not self.ifc_date:
				self.ifc_date = today()
		elif self.status in INVALID_EXECUTION_STATUSES:
			self.ifc = 0
			self.ifc_date = None

	def _validate_read_only_old_revision(self):
		if self.is_new() or frappe.flags.in_migrate:
			return
		latest = frappe.db.get_value("Drawing Register", self.drawing, "latest_revision") if self.drawing else None
		if latest and latest != self.name and not frappe.has_role(("System Manager", "Document Controller")):
			frappe.throw(_("Old drawing revisions are read-only. Create a new revision instead."))

	def update_drawing_register(self):
		if not self.drawing:
			return
		drawing = frappe.get_doc("Drawing Register", self.drawing)
		drawing.sync_revision_summary()
		drawing.db_update()


class DrawingReview(Document):
	def validate(self):
		validate_revision_belongs_to_drawing(self.drawing, self.revision)
		apply_drawing_context(self)
		set_revision_number_from_drawing(self)
		if not self.review_date:
			self.review_date = today()


class DrawingApproval(Document):
	def validate(self):
		validate_revision_belongs_to_drawing(self.drawing, self.revision)
		apply_drawing_context(self)
		set_revision_number_from_drawing(self)
		if self.approval_status == IFC_STATUS and self.drawing:
			status = frappe.db.get_value("Drawing Register", self.drawing, "current_status")
			if status != "Approved":
				frappe.throw(_("Only Approved drawings can be issued for construction."))
		if self.approval_status in ("Approved", IFC_STATUS) and not self.approval_date:
			self.approval_date = now()

	def on_update(self):
		if self.drawing and self.approval_status == "Approved":
			frappe.db.set_value("Drawing Register", self.drawing, "current_status", "Approved", update_modified=False)
		if self.revision and self.approval_status:
			frappe.db.set_value("Drawing Revision", self.revision, "status", self.approval_status, update_modified=False)
			revision = frappe.get_doc("Drawing Revision", self.revision)
			revision._validate_ifc_status()
			revision.db_update()
			revision.update_drawing_register()


class DrawingDistribution(Document):
	def validate(self):
		validate_revision_belongs_to_drawing(self.drawing, self.revision)
		apply_drawing_context(self)
		set_revision_number_from_drawing(self)


class DesignIssue(Document):
	def validate(self):
		validate_revision_belongs_to_drawing(self.drawing, self.revision)
		apply_drawing_context(self)
		set_revision_number_from_drawing(self)


class RequestForInformation(Document):
	def validate(self):
		validate_revision_belongs_to_drawing(self.drawing, self.revision)
		apply_drawing_context(self)
		set_revision_number_from_drawing(self)


class DesignChangeRequest(Document):
	def validate(self):
		validate_revision_belongs_to_drawing(self.drawing, self.revision)
		apply_drawing_context(self)
		set_revision_number_from_drawing(self)


class DesignNCR(Document):
	def validate(self):
		validate_revision_belongs_to_drawing(self.drawing, self.revision)
		apply_drawing_context(self)
		set_revision_number_from_drawing(self)


class DrawingTransmittal(Document):
	def validate(self):
		apply_drawing_context(self)
		set_revision_number_from_drawing(self)
		for row in self.items:
			validate_revision_belongs_to_drawing(row.drawing, row.revision)
			set_revision_number_from_drawing(row)


class DrawingAttachment(Document):
	pass


class DrawingComment(Document):
	pass


class DrawingTransmittalItem(Document):
	pass


def validate_revision_belongs_to_drawing(drawing, revision):
	if not drawing or not revision:
		return
	revision_drawing = frappe.db.get_value("Drawing Revision", revision, "drawing")
	if revision_drawing and revision_drawing != drawing:
		frappe.throw(_("Drawing Revision {0} does not belong to Drawing {1}.").format(revision, drawing))


def get_drawing_context(drawing=None, revision=None):
	if not drawing and revision:
		drawing = frappe.db.get_value("Drawing Revision", revision, "drawing")
	if not drawing:
		return frappe._dict()
	context = frappe.db.get_value(
		"Drawing Register",
		drawing,
		["name", "project", "company", "design_package", "discipline", "consultant", "prepared_by"],
		as_dict=True,
	)
	return context or frappe._dict()


def validate_drawing_context(doc):
	drawing = doc.get("drawing")
	if not drawing:
		return
	context = get_drawing_context(drawing)
	if not context:
		return
	for fieldname in ("project", "design_package", "discipline"):
		if doc.meta.has_field(fieldname) and doc.get(fieldname) and context.get(fieldname) and doc.get(fieldname) != context.get(fieldname):
			frappe.throw(_("Drawing {0} does not belong to the selected {1}.").format(drawing, doc.meta.get_label(fieldname)))


def apply_drawing_context(doc):
	context = get_drawing_context(doc.get("drawing"), doc.get("revision"))
	if not context:
		return
	for source, target in (
		("project", "project"),
		("company", "company"),
		("design_package", "design_package"),
		("discipline", "discipline"),
	):
		if doc.meta.has_field(target) and context.get(source) and not doc.get(target):
			doc.set(target, context.get(source))
	validate_drawing_context(doc)


def set_revision_number_from_drawing(doc):
	if not doc.get("drawing") or not doc.meta.has_field("revision_number"):
		return
	revision_number = frappe.db.get_value("Drawing Register", doc.get("drawing"), "revision_number")
	if revision_number and not doc.get("revision_number"):
		doc.revision_number = revision_number


def validate_ifc_revision(drawing, revision):
	validate_revision_belongs_to_drawing(drawing, revision)
	status, ifc = frappe.db.get_value("Drawing Revision", revision, ["status", "ifc"])
	if not ifc or status != IFC_STATUS:
		frappe.throw(_("Only Issued For Construction drawing revisions can be used for execution documents."))


def validate_ifc_drawing(drawing):
	if not drawing:
		return
	status, ifc_status = frappe.db.get_value("Drawing Register", drawing, ["current_status", "ifc_status"])
	if status != DRAWING_IFC_STATUS and not ifc_status:
		frappe.throw(_("Only IFC drawings can be used for execution documents."))


def validate_design_references(doc, method=None):
	drawing = doc.get("drawing")
	revision = doc.get("drawing_revision") or doc.get("ifc_revision")
	if drawing and revision:
		apply_drawing_context(doc)
		set_revision_number_from_drawing(doc)
		validate_ifc_revision(drawing, revision)
		if doc.meta.has_field("ifc_revision") and not doc.get("ifc_revision"):
			doc.ifc_revision = revision
	elif revision:
		drawing = frappe.db.get_value("Drawing Revision", revision, "drawing")
		if drawing and doc.meta.has_field("drawing"):
			doc.drawing = drawing
		apply_drawing_context(doc)
		set_revision_number_from_drawing(doc)
		validate_ifc_revision(doc.get("drawing"), revision)
		if doc.meta.has_field("ifc_revision") and not doc.get("ifc_revision"):
			doc.ifc_revision = revision
	elif drawing:
		apply_drawing_context(doc)
		set_revision_number_from_drawing(doc)
		validate_ifc_drawing(drawing)

	for tablefield in ("items", "packed_items"):
		for row in doc.get(tablefield) or []:
			drawing = row.get("drawing")
			revision = row.get("drawing_revision") or row.get("ifc_revision")
			if drawing and revision:
				apply_drawing_context(row)
				set_revision_number_from_drawing(row)
				validate_ifc_revision(drawing, revision)
				if not row.get("ifc_revision"):
					row.ifc_revision = revision
			elif revision:
				drawing = frappe.db.get_value("Drawing Revision", revision, "drawing")
				if drawing:
					row.drawing = drawing
				apply_drawing_context(row)
				set_revision_number_from_drawing(row)
				validate_ifc_revision(row.drawing, revision)
				if not row.get("ifc_revision"):
					row.ifc_revision = revision
			elif drawing:
				apply_drawing_context(row)
				set_revision_number_from_drawing(row)
				validate_ifc_drawing(drawing)


def get_ifc_revision_query(doctype, txt, searchfield, start, page_len, filters):
	drawing = (filters or {}).get("drawing")
	query_filters = {"ifc": 1, "status": IFC_STATUS}
	if drawing:
		query_filters["drawing"] = drawing
	return frappe.get_all(
		doctype,
		filters=query_filters,
		or_filters={"revision_number": ["like", f"%{txt}%"], "name": ["like", f"%{txt}%"]},
		fields=["name", "revision_number", "drawing"],
		start=start,
		page_length=page_len,
		as_list=True,
	)


def get_impact_analysis(drawing, revision=None):
	if not drawing:
		return {}
	impact = {}
	child_tables = {
		"BOQ Item": "BOQ",
		"RA Bill Item": "RA Bill",
		"SC Work Order Item": "SC Work Order",
		"SC Bill Item": "SC Bill",
		"Sales Order Item": "Sales Order",
		"Purchase Order Item": "Purchase Order",
		"Purchase Invoice Item": "Purchase Invoice",
		"Material Request Item": "Material Request",
		"Stock Entry Detail": "Stock Entry",
		"Purchase Receipt Item": "Purchase Receipt",
	}
	for child_dt, parent_dt in child_tables.items():
		if not frappe.db.table_exists(child_dt):
			continue
		meta = frappe.get_meta(child_dt)
		if meta.has_field("drawing"):
			filters = {"drawing": drawing}
		elif revision and meta.has_field("drawing_revision"):
			filters = {"drawing_revision": revision}
		else:
			continue
		parents = frappe.get_all(
			child_dt,
			filters=filters,
			fields=["distinct parent as parent"],
		)
		impact[parent_dt] = len(parents)
	return impact


def _make_mapped_doc(source_doctype, source_name, target_doctype, field_map=None, postprocess=None, target_doc=None):
	return get_mapped_doc(
		source_doctype,
		source_name,
		{
			source_doctype: {
				"doctype": target_doctype,
				"field_map": field_map or {},
			}
		},
		target_doc,
		postprocess,
	)


def _set_if_present(doc, values):
	for fieldname, value in values.items():
		if doc.meta.has_field(fieldname) and value not in (None, ""):
			doc.set(fieldname, value)


def _set_revision_context_from_revision(source, target):
	_set_if_present(
		target,
		{
			"drawing": source.drawing,
			"revision": source.name,
			"project": source.project,
			"company": source.company,
			"design_package": source.design_package,
			"discipline": source.discipline,
		},
	)


def _set_drawing_context_from_drawing(source, target):
	_set_if_present(
		target,
		{
			"drawing": source.name,
			"revision_number": source.revision_number or source.current_revision,
			"project": source.project,
			"company": source.company,
			"design_package": source.design_package,
			"discipline": source.discipline,
		},
	)


@frappe.whitelist()
def make_design_package(source_name, target_doc=None):
	def postprocess(source, target):
		target.project = source.name
		target.company = source.get("company")
		target.package_name = _("Design Package for {0}").format(source.get("project_name") or source.name)

	return _make_mapped_doc("Project", source_name, "Design Package", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_design_discipline(source_name, target_doc=None):
	def postprocess(source, target):
		target.package = source.name
		target.project = source.project
		target.discipline = _("New Discipline")

	return _make_mapped_doc("Design Package", source_name, "Design Discipline", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_drawing_register_from_package(source_name, target_doc=None):
	def postprocess(source, target):
		target.project = source.project
		target.company = source.company
		target.design_package = source.name

	return _make_mapped_doc("Design Package", source_name, "Drawing Register", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_drawing_register_from_discipline(source_name, target_doc=None):
	def postprocess(source, target):
		package = frappe.db.get_value("Design Package", source.package, ["company"], as_dict=True) or {}
		target.project = source.project
		target.company = package.get("company")
		target.design_package = source.package
		target.discipline = source.name

	return _make_mapped_doc("Design Discipline", source_name, "Drawing Register", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_revision_from_drawing(source_name, target_doc=None):
	def postprocess(source, target):
		target.drawing = source.name
		target.project = source.project
		target.company = source.company
		target.design_package = source.design_package
		target.discipline = source.discipline
		target.revision_number = get_next_revision_number(source.name)
		target.revision_date = today()
		target.changed_by = frappe.session.user
		target.status = "Draft"

	return _make_mapped_doc("Drawing Register", source_name, "Drawing Revision", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_review_from_drawing(source_name, target_doc=None):
	def postprocess(source, target):
		_set_drawing_context_from_drawing(source, target)
		target.review_date = today()
		target.reviewer = frappe.session.user

	return _make_mapped_doc("Drawing Register", source_name, "Drawing Review", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_review_from_revision(source_name, target_doc=None):
	def postprocess(source, target):
		_set_revision_context_from_revision(source, target)
		target.review_date = today()
		target.reviewer = frappe.session.user

	return _make_mapped_doc("Drawing Revision", source_name, "Drawing Review", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_approval_from_drawing(source_name, target_doc=None):
	def postprocess(source, target):
		_set_drawing_context_from_drawing(source, target)
		target.approval_status = "Approved" if source.current_status == "Approved" else source.current_status

	return _make_mapped_doc("Drawing Register", source_name, "Drawing Approval", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_approval_from_revision(source_name, target_doc=None):
	def postprocess(source, target):
		_set_revision_context_from_revision(source, target)
		target.approval_status = "Approved" if source.status == "Approved" else source.status

	return _make_mapped_doc("Drawing Revision", source_name, "Drawing Approval", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_approval_from_review(source_name, target_doc=None):
	def postprocess(source, target):
		_set_if_present(
			target,
			{
				"drawing": source.drawing,
				"revision": source.revision,
				"revision_number": source.get("revision_number"),
				"drawing_review": source.name,
				"project": source.project,
				"company": source.company,
				"design_package": source.design_package,
				"discipline": source.discipline,
			},
		)
		target.approval_status = "Approved" if source.decision in ("Approved", "Approved with Comments") else "Internal Review"

	return _make_mapped_doc("Drawing Review", source_name, "Drawing Approval", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_distribution_from_drawing(source_name, target_doc=None):
	def postprocess(source, target):
		_set_drawing_context_from_drawing(source, target)
		target.date = today()
		target.status = "Pending"

	return _make_mapped_doc("Drawing Register", source_name, "Drawing Distribution", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_distribution_from_revision(source_name, target_doc=None):
	def postprocess(source, target):
		_set_revision_context_from_revision(source, target)
		target.date = today()
		target.status = "Pending"

	return _make_mapped_doc("Drawing Revision", source_name, "Drawing Distribution", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_rfi_from_drawing(source_name, target_doc=None):
	def postprocess(source, target):
		_set_drawing_context_from_drawing(source, target)
		target.rfi_number = make_autoname_preview("RFI")
		target.raised_by = frappe.session.user
		target.status = "Open"

	return _make_mapped_doc("Drawing Register", source_name, "Request For Information", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_rfi_from_revision(source_name, target_doc=None):
	def postprocess(source, target):
		_set_revision_context_from_revision(source, target)
		target.rfi_number = make_autoname_preview("RFI")
		target.raised_by = frappe.session.user
		target.status = "Open"

	return _make_mapped_doc("Drawing Revision", source_name, "Request For Information", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_issue_from_drawing(source_name, target_doc=None):
	def postprocess(source, target):
		_set_drawing_context_from_drawing(source, target)
		target.issue_no = make_autoname_preview("DI")
		target.assigned_to = frappe.session.user
		target.status = "Open"

	return _make_mapped_doc("Drawing Register", source_name, "Design Issue", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_issue_from_revision(source_name, target_doc=None):
	def postprocess(source, target):
		_set_revision_context_from_revision(source, target)
		target.issue_no = make_autoname_preview("DI")
		target.assigned_to = frappe.session.user
		target.status = "Open"

	return _make_mapped_doc("Drawing Revision", source_name, "Design Issue", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_dcr_from_drawing(source_name, target_doc=None):
	def postprocess(source, target):
		_set_drawing_context_from_drawing(source, target)
		target.dcr_number = make_autoname_preview("DCR")
		target.status = "Open"
		target.approval = "Pending"

	return _make_mapped_doc("Drawing Register", source_name, "Design Change Request", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_dcr_from_revision(source_name, target_doc=None):
	def postprocess(source, target):
		_set_revision_context_from_revision(source, target)
		target.dcr_number = make_autoname_preview("DCR")
		target.status = "Open"
		target.approval = "Pending"

	return _make_mapped_doc("Drawing Revision", source_name, "Design Change Request", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_ncr_from_drawing(source_name, target_doc=None):
	def postprocess(source, target):
		_set_drawing_context_from_drawing(source, target)
		target.status = "Open"

	return _make_mapped_doc("Drawing Register", source_name, "Design NCR", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_ncr_from_revision(source_name, target_doc=None):
	def postprocess(source, target):
		_set_revision_context_from_revision(source, target)
		target.status = "Open"

	return _make_mapped_doc("Drawing Revision", source_name, "Design NCR", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_transmittal_from_revision(source_name, target_doc=None):
	def postprocess(source, target):
		_set_revision_context_from_revision(source, target)
		target.sent_to = frappe.session.user
		target.date = today()
		target.status = "Draft"
		target.append("items", {"drawing": source.drawing, "revision": source.name})

	return _make_mapped_doc("Drawing Revision", source_name, "Drawing Transmittal", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_transmittal_from_drawing(source_name, target_doc=None):
	def postprocess(source, target):
		target.project = source.project
		target.company = source.company
		target.design_package = source.design_package
		target.discipline = source.discipline
		target.drawing = source.name
		target.revision_number = source.revision_number or source.current_revision
		target.sent_to = frappe.session.user
		target.date = today()
		target.status = "Draft"
		target.append("items", {"drawing": source.name, "revision_number": source.revision_number or source.current_revision})

	return _make_mapped_doc("Drawing Register", source_name, "Drawing Transmittal", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_transmittal_from_package(source_name, target_doc=None):
	def postprocess(source, target):
		target.project = source.project
		target.company = source.company
		target.design_package = source.name
		target.sent_to = frappe.session.user
		target.date = today()
		target.status = "Draft"

	return _make_mapped_doc("Design Package", source_name, "Drawing Transmittal", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_transmittal_from_discipline(source_name, target_doc=None):
	def postprocess(source, target):
		company = frappe.db.get_value("Design Package", source.package, "company")
		target.project = source.project
		target.company = company
		target.design_package = source.package
		target.discipline = source.name
		target.sent_to = frappe.session.user
		target.date = today()
		target.status = "Draft"

	return _make_mapped_doc("Design Discipline", source_name, "Drawing Transmittal", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_transmittal_from_distribution(source_name, target_doc=None):
	def postprocess(source, target):
		_set_if_present(
			target,
			{
				"project": source.project,
				"company": source.company,
				"design_package": source.design_package,
				"discipline": source.discipline,
				"drawing": source.drawing,
				"revision": source.revision,
				"revision_number": source.get("revision_number"),
				"sent_to": source.sent_to,
				"date": today(),
				"status": "Draft",
			},
		)
		target.append("items", {"drawing": source.drawing, "revision": source.revision, "revision_number": source.get("revision_number")})

	return _make_mapped_doc("Drawing Distribution", source_name, "Drawing Transmittal", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_dcr_from_rfi(source_name, target_doc=None):
	def postprocess(source, target):
		_set_if_present(target, _source_context(source))
		target.source_rfi = source.name
		target.dcr_number = make_autoname_preview("DCR")
		target.reason = source.question
		target.status = "Open"
		target.approval = "Pending"

	return _make_mapped_doc("Request For Information", source_name, "Design Change Request", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_dcr_from_issue(source_name, target_doc=None):
	def postprocess(source, target):
		_set_if_present(target, _source_context(source))
		target.design_issue = source.name
		target.dcr_number = make_autoname_preview("DCR")
		target.reason = source.description
		target.status = "Open"
		target.approval = "Pending"

	return _make_mapped_doc("Design Issue", source_name, "Design Change Request", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_issue_from_rfi(source_name, target_doc=None):
	def postprocess(source, target):
		_set_if_present(target, _source_context(source))
		target.source_rfi = source.name
		target.issue_no = make_autoname_preview("DI")
		target.description = source.question
		target.assigned_to = frappe.session.user
		target.status = "Open"

	return _make_mapped_doc("Request For Information", source_name, "Design Issue", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_ncr_from_issue(source_name, target_doc=None):
	def postprocess(source, target):
		_set_if_present(target, _source_context(source))
		target.design_issue = source.name
		target.description = source.description
		target.responsible_person = source.assigned_to
		target.status = "Open"

	return _make_mapped_doc("Design Issue", source_name, "Design NCR", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_issue_from_ncr(source_name, target_doc=None):
	def postprocess(source, target):
		_set_if_present(target, _source_context(source))
		target.source_ncr = source.name
		target.issue_no = make_autoname_preview("DI")
		target.description = source.description
		target.status = "Open"

	return _make_mapped_doc("Design NCR", source_name, "Design Issue", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_revision_from_dcr(source_name, target_doc=None):
	def postprocess(source, target):
		target.drawing = source.drawing
		apply_drawing_context(target)
		target.revision_number = get_next_revision_number(source.drawing)
		target.revision_date = today()
		target.revision_description = source.reason
		target.source_revision = source.revision
		target.design_change_request = source.name
		target.changed_by = frappe.session.user
		target.status = "Draft"
		if source.revision:
			previous = frappe.db.get_value("Drawing Revision", source.revision, ["attachment"], as_dict=True)
			if previous and previous.attachment:
				target.attachment = previous.attachment

	return _make_mapped_doc("Design Change Request", source_name, "Drawing Revision", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_revision_from_ncr(source_name, target_doc=None):
	def postprocess(source, target):
		target.drawing = source.drawing
		apply_drawing_context(target)
		target.revision_number = get_next_revision_number(source.drawing)
		target.revision_date = today()
		target.revision_description = source.corrective_action or source.description
		target.source_revision = source.revision
		target.changed_by = frappe.session.user
		target.status = "Draft"

	return _make_mapped_doc("Design NCR", source_name, "Drawing Revision", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def update_drawing_register_from_dcr(source_name):
	dcr = frappe.get_doc("Design Change Request", source_name)
	if dcr.approval != "Approved":
		frappe.throw(_("Only approved Design Change Requests can update the Drawing Register."))
	if not dcr.drawing:
		frappe.throw(_("Design Change Request must be linked to a Drawing Register."))
	drawing = frappe.get_doc("Drawing Register", dcr.drawing)
	old_revision = drawing.revision_number or drawing.current_revision
	drawing.revision_number = get_next_register_revision_number(old_revision)
	drawing.current_revision = drawing.revision_number
	drawing.revision_date = today()
	drawing.revision_description = dcr.reason or dcr.description or _("Updated from Design Change Request {0}").format(dcr.name)
	drawing.current_status = "Draft"
	drawing.ifc_status = 0
	drawing.ifc_date = None
	drawing.ifc_by = None
	if dcr.get("new_drawing_attachment"):
		drawing.append(
			"attachments",
			{
				"attachment_type": "Drawing",
				"file": dcr.new_drawing_attachment,
				"revision_number": drawing.revision_number,
				"uploaded_by": frappe.session.user,
				"uploaded_on": today(),
				"remarks": _("Updated from Design Change Request {0}").format(dcr.name),
			},
		)
	drawing.save()
	dcr.db_set("new_revision", None, update_modified=False)
	dcr.db_set("status", "Closed", update_modified=False)
	drawing.add_comment(
		"Info",
		_("Revision changed from {0} to {1} from Design Change Request {2}.").format(old_revision or "-", drawing.revision_number, dcr.name),
	)
	return drawing.as_dict()


@frappe.whitelist()
def issue_for_construction(source_name):
	if frappe.db.exists("Drawing Register", source_name):
		drawing = frappe.get_doc("Drawing Register", source_name)
		if drawing.current_status != "Approved":
			frappe.throw(_("Only Approved drawings can be issued for construction."))
		drawing.current_status = DRAWING_IFC_STATUS
		drawing.ifc_status = 1
		drawing.ifc_date = today()
		drawing.ifc_by = frappe.session.user
		drawing.save()
		drawing.add_comment("Info", _("Drawing issued for construction."))
		return drawing.as_dict()

	revision = frappe.get_doc("Drawing Revision", source_name)
	if revision.status != "Approved":
		frappe.throw(_("Only Approved drawing revisions can be issued for construction."))
	revision.status = IFC_STATUS
	revision.save()
	revision.add_comment("Info", _("Revision issued for construction."))
	return revision.as_dict()


@frappe.whitelist()
def make_boq_from_drawing(source_name, target_doc=None):
	source = frappe.get_doc("Drawing Register", source_name)
	if source.current_status != DRAWING_IFC_STATUS and not source.ifc_status:
		frappe.throw(_("Only IFC drawings can create BOQ."))

	def postprocess(source, target):
		target.project = source.project
		target.company = source.company
		target.currency = frappe.db.get_value("Company", source.company, "default_currency") or target.get("currency")
		target.status = "Draft"
		_set_if_present(
			target,
			{
				"drawing": source.name,
				"revision_number": source.revision_number or source.current_revision,
			},
		)

	return _make_mapped_doc("Drawing Register", source_name, "BOQ", postprocess=postprocess, target_doc=target_doc)


@frappe.whitelist()
def make_boq_from_revision(source_name, target_doc=None):
	source = frappe.get_doc("Drawing Revision", source_name)
	if source.status != IFC_STATUS or not source.ifc:
		frappe.throw(_("Only Issued For Construction drawing revisions can create BOQ."))

	def postprocess(source, target):
		target.project = source.project
		target.company = source.company
		target.currency = frappe.db.get_value("Company", source.company, "default_currency") or target.get("currency")
		target.status = "Draft"
		_set_if_present(
			target,
			{
				"drawing": source.drawing,
				"drawing_revision": source.name,
				"ifc_revision": source.name,
			},
		)

	return _make_mapped_doc("Drawing Revision", source_name, "BOQ", postprocess=postprocess, target_doc=target_doc)


def _source_context(source):
	return {
		"project": source.get("project"),
		"company": source.get("company"),
		"design_package": source.get("design_package"),
		"discipline": source.get("discipline"),
		"drawing": source.get("drawing"),
		"revision": source.get("revision"),
		"revision_number": source.get("revision_number"),
	}


def get_next_revision_number(drawing):
	revisions = frappe.get_all(
		"Drawing Revision",
		filters={"drawing": drawing},
		pluck="revision_number",
		order_by="creation desc",
	)
	numbers = []
	for revision in revisions:
		match = re.search(r"(\d+)$", revision or "")
		if match:
			numbers.append(int(match.group(1)))
	if numbers:
		return f"REV{max(numbers) + 1}"
	return "REV0"


def get_next_register_revision_number(current_revision):
	match = re.search(r"(\d+)$", current_revision or "")
	if match:
		prefix = (current_revision or "")[: match.start(1)] or "REV"
		return f"{prefix}{int(match.group(1)) + 1}"
	return "REV1"


def make_autoname_preview(prefix):
	return f"{prefix}-{frappe.generate_hash(length=8).upper()}"
