from frappe import _


DESIGN_CONTEXT_DOCTYPES = [
	"Drawing Review",
	"Drawing Approval",
	"Request For Information",
	"Design Issue",
	"Design Change Request",
	"Design NCR",
	"Drawing Distribution",
	"Drawing Transmittal",
	"BOQ",
]

EXECUTION_DOCTYPES = [
	"BOQ",
	"Sales Order",
	"RA Bill",
	"Sales Invoice",
	"SC Work Order",
	"Purchase Order",
	"SC Bill",
	"Purchase Invoice",
]


def _context_fieldnames(fieldname):
	return {doctype: fieldname for doctype in DESIGN_CONTEXT_DOCTYPES}


def _drawing_fieldnames(extra=None):
	fieldnames = {doctype: "drawing" for doctype in DESIGN_CONTEXT_DOCTYPES + EXECUTION_DOCTYPES}
	fieldnames.update(extra or {})
	return fieldnames


def design_package_dashboard():
	return {
		"fieldname": "design_package",
		"internal_links": {"Project": "project"},
		"non_standard_fieldnames": {
			"Design Discipline": "package",
			"Drawing Register": "design_package",
			**_context_fieldnames("design_package"),
		},
		"transactions": [
			{"label": _("Incoming Documents"), "items": ["Project"]},
			{"label": _("Current Documents"), "items": ["Design Discipline", "Drawing Register"]},
			{"label": _("Review and Approval"), "items": ["Drawing Review", "Drawing Approval"]},
			{"label": _("Queries and Issues"), "items": ["Request For Information", "Design Issue"]},
			{"label": _("Change Control"), "items": ["Design Change Request", "Design NCR"]},
			{"label": _("Distribution"), "items": ["Drawing Distribution", "Drawing Transmittal"]},
			{"label": _("Execution"), "items": ["BOQ"]},
		],
	}


def design_discipline_dashboard():
	return {
		"fieldname": "discipline",
		"internal_links": {"Design Package": "package", "Project": "project"},
		"non_standard_fieldnames": {
			"Drawing Register": "discipline",
			**_context_fieldnames("discipline"),
		},
		"transactions": [
			{"label": _("Incoming Documents"), "items": ["Project", "Design Package"]},
			{"label": _("Current Documents"), "items": ["Drawing Register"]},
			{"label": _("Review and Approval"), "items": ["Drawing Review", "Drawing Approval"]},
			{"label": _("Queries and Issues"), "items": ["Request For Information", "Design Issue"]},
			{"label": _("Change Control"), "items": ["Design Change Request", "Design NCR"]},
			{"label": _("Distribution"), "items": ["Drawing Distribution", "Drawing Transmittal"]},
			{"label": _("Execution"), "items": ["BOQ"]},
		],
	}


def drawing_register_dashboard():
	return {
		"fieldname": "drawing",
		"internal_links": {
			"Project": "project",
			"Design Package": "design_package",
			"Design Discipline": "discipline",
		},
		"non_standard_fieldnames": _drawing_fieldnames(),
		"transactions": [
			{"label": _("Incoming Documents"), "items": ["Project", "Design Package", "Design Discipline"]},
			{"label": _("Review and Approval"), "items": ["Drawing Review", "Drawing Approval"]},
			{"label": _("Queries and Issues"), "items": ["Request For Information", "Design Issue"]},
			{"label": _("Change Control"), "items": ["Design Change Request", "Design NCR"]},
			{"label": _("Distribution"), "items": ["Drawing Distribution", "Drawing Transmittal"]},
			{"label": _("Execution"), "items": ["BOQ", "Sales Order", "RA Bill", "Sales Invoice"]},
			{"label": _("Subcontracting"), "items": ["SC Work Order", "Purchase Order", "SC Bill", "Purchase Invoice"]},
		],
	}


def drawing_revision_dashboard():
	return {
		"fieldname": "revision",
		"internal_links": {"Drawing Register": "drawing"},
		"transactions": [
			{"label": _("Legacy Source"), "items": ["Drawing Register"]},
		],
	}


def drawing_review_dashboard():
	return {
		"fieldname": "drawing_review",
		"internal_links": {
			"Project": "project",
			"Design Package": "design_package",
			"Design Discipline": "discipline",
			"Drawing Register": "drawing",
		},
		"non_standard_fieldnames": {
			"Drawing Approval": "drawing_review",
			"Request For Information": "drawing",
			"Design Issue": "drawing",
			"Design Change Request": "drawing",
		},
		"transactions": [
			{"label": _("Incoming Documents"), "items": ["Project", "Design Package", "Design Discipline", "Drawing Register"]},
			{"label": _("Outgoing Documents"), "items": ["Drawing Approval"]},
			{"label": _("Queries and Issues"), "items": ["Request For Information", "Design Issue"]},
			{"label": _("Change Control"), "items": ["Design Change Request"]},
		],
	}


def drawing_approval_dashboard():
	return {
		"fieldname": "drawing",
		"internal_links": {
			"Project": "project",
			"Design Package": "design_package",
			"Design Discipline": "discipline",
			"Drawing Register": "drawing",
			"Drawing Review": "drawing_review",
		},
		"non_standard_fieldnames": {
			"Drawing Review": "drawing",
			"Drawing Distribution": "drawing",
			"Drawing Transmittal": "drawing",
			"BOQ": "drawing",
		},
		"transactions": [
			{"label": _("Incoming Documents"), "items": ["Project", "Design Package", "Design Discipline", "Drawing Register", "Drawing Review"]},
			{"label": _("Distribution"), "items": ["Drawing Distribution", "Drawing Transmittal"]},
			{"label": _("Execution"), "items": ["BOQ"]},
		],
	}


def drawing_distribution_dashboard():
	return {
		"fieldname": "drawing",
		"internal_links": {
			"Project": "project",
			"Design Package": "design_package",
			"Design Discipline": "discipline",
			"Drawing Register": "drawing",
		},
		"non_standard_fieldnames": {
			"Drawing Approval": "drawing",
			"Drawing Transmittal": "drawing",
		},
		"transactions": [
			{"label": _("Incoming Documents"), "items": ["Project", "Design Package", "Design Discipline", "Drawing Register", "Drawing Approval"]},
			{"label": _("Outgoing Documents"), "items": ["Drawing Transmittal"]},
		],
	}


def rfi_dashboard():
	return {
		"fieldname": "source_rfi",
		"internal_links": {
			"Project": "project",
			"Design Package": "design_package",
			"Design Discipline": "discipline",
			"Drawing Register": "drawing",
		},
		"non_standard_fieldnames": {
			"Drawing Review": "drawing",
			"Design Issue": "source_rfi",
			"Design Change Request": "source_rfi",
		},
		"transactions": [
			{"label": _("Incoming Documents"), "items": ["Project", "Design Package", "Design Discipline", "Drawing Register"]},
			{"label": _("Review and Approval"), "items": ["Drawing Review"]},
			{"label": _("Outgoing Documents"), "items": ["Design Issue", "Design Change Request"]},
		],
	}


def design_issue_dashboard():
	return {
		"fieldname": "design_issue",
		"internal_links": {
			"Project": "project",
			"Design Package": "design_package",
			"Design Discipline": "discipline",
			"Drawing Register": "drawing",
			"Request For Information": "source_rfi",
			"Design NCR": "source_ncr",
		},
		"non_standard_fieldnames": {
			"Request For Information": "drawing",
			"Design Change Request": "design_issue",
			"Design NCR": "design_issue",
		},
		"transactions": [
			{"label": _("Incoming Documents"), "items": ["Project", "Design Package", "Design Discipline", "Drawing Register", "Request For Information"]},
			{"label": _("Outgoing Documents"), "items": ["Design Change Request", "Design NCR"]},
		],
	}


def dcr_dashboard():
	return {
		"fieldname": "design_change_request",
		"internal_links": {
			"Project": "project",
			"Design Package": "design_package",
			"Design Discipline": "discipline",
			"Drawing Register": "drawing",
			"Request For Information": "source_rfi",
			"Design Issue": "design_issue",
			"Design NCR": "source_ncr",
		},
		"non_standard_fieldnames": {
			"Drawing Review": "drawing",
			"Drawing Approval": "drawing",
			"Design NCR": "source_ncr",
		},
		"transactions": [
			{"label": _("Incoming Documents"), "items": ["Project", "Design Package", "Design Discipline", "Drawing Register", "Request For Information", "Design Issue", "Design NCR"]},
			{"label": _("Review and Approval"), "items": ["Drawing Review", "Drawing Approval"]},
			{"label": _("Change Control"), "items": ["Design NCR"]},
		],
	}


def ncr_dashboard():
	return {
		"fieldname": "source_ncr",
		"internal_links": {
			"Project": "project",
			"Design Package": "design_package",
			"Design Discipline": "discipline",
			"Drawing Register": "drawing",
			"Design Issue": "design_issue",
		},
		"non_standard_fieldnames": {
			"Request For Information": "drawing",
			"Design Issue": "source_ncr",
			"Design Change Request": "source_ncr",
		},
		"transactions": [
			{"label": _("Incoming Documents"), "items": ["Project", "Design Package", "Design Discipline", "Drawing Register"]},
			{"label": _("Queries and Issues"), "items": ["Request For Information", "Design Issue"]},
			{"label": _("Outgoing Documents"), "items": ["Design Change Request"]},
		],
	}


def drawing_transmittal_dashboard():
	return {
		"fieldname": "drawing",
		"internal_links": {
			"Project": "project",
			"Design Package": "design_package",
			"Design Discipline": "discipline",
			"Drawing Register": "drawing",
		},
		"non_standard_fieldnames": {"Drawing Distribution": "drawing"},
		"transactions": [
			{"label": _("Incoming Documents"), "items": ["Project", "Design Package", "Design Discipline", "Drawing Register", "Drawing Distribution"]},
		],
	}
