const DESIGN_MANAGEMENT_METHOD = "construction_management.design_management.design_management";

function can_create(doctype) {
	return !frappe.model.can_create || frappe.model.can_create(doctype);
}

function open_design_mapped_doc(frm, method) {
	frappe.model.open_mapped_doc({
		method: `${DESIGN_MANAGEMENT_METHOD}.${method}`,
		frm,
	});
}

function add_create_button(frm, label, method, target_doctype, condition = true) {
	if (frm.is_new() || !condition || !can_create(target_doctype)) {
		return;
	}
	frm.add_custom_button(__(label), () => open_design_mapped_doc(frm, method), __("Create"));
}

function is_ifc(frm) {
	return frm.doc.current_status === "IFC" || frm.doc.ifc_status;
}

frappe.ui.form.on("Design Package", {
	refresh(frm) {
		add_create_button(frm, "Design Discipline", "make_design_discipline", "Design Discipline");
		add_create_button(frm, "Drawing Register", "make_drawing_register_from_package", "Drawing Register");
		add_create_button(frm, "Transmittal", "make_transmittal_from_package", "Drawing Transmittal");
	},
});

frappe.ui.form.on("Design Discipline", {
	refresh(frm) {
		add_create_button(frm, "Drawing Register", "make_drawing_register_from_discipline", "Drawing Register");
	},
});

frappe.ui.form.on("Drawing Register", {
	refresh(frm) {
		add_create_button(frm, "Drawing Review", "make_review_from_drawing", "Drawing Review");
		add_create_button(frm, "Drawing Approval", "make_approval_from_drawing", "Drawing Approval");
		add_create_button(frm, "RFI", "make_rfi_from_drawing", "Request For Information");
		add_create_button(frm, "Design Issue", "make_issue_from_drawing", "Design Issue");
		add_create_button(frm, "Design Change Request", "make_dcr_from_drawing", "Design Change Request");
		add_create_button(frm, "Design NCR", "make_ncr_from_drawing", "Design NCR");
		add_create_button(frm, "Distribution", "make_distribution_from_drawing", "Drawing Distribution");
		add_create_button(frm, "Transmittal", "make_transmittal_from_drawing", "Drawing Transmittal");
		add_create_button(frm, "BOQ", "make_boq_from_drawing", "BOQ", is_ifc(frm));
	},
});

frappe.ui.form.on("Drawing Review", {
	refresh(frm) {
		add_create_button(frm, "Approval", "make_approval_from_review", "Drawing Approval");
	},
});

frappe.ui.form.on("Drawing Approval", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.drawing && frm.doc.approval_status === "Approved") {
			frm.add_custom_button(
				__("Issue For Construction"),
				() => {
					frappe.call({
						method: `${DESIGN_MANAGEMENT_METHOD}.issue_for_construction`,
						args: { source_name: frm.doc.drawing },
						callback() {
							frm.reload_doc();
						},
					});
				},
				__("Status")
			);
		}
		if (!frm.is_new() && frm.doc.drawing && frm.doc.approval_status === "Issued For Construction" && can_create("BOQ")) {
			frm.add_custom_button(
				__("BOQ"),
				() => {
					frappe.model.open_mapped_doc({
						method: `${DESIGN_MANAGEMENT_METHOD}.make_boq_from_drawing`,
						source_name: frm.doc.drawing,
					});
				},
				__("Create")
			);
		}
	},
});

frappe.ui.form.on("Drawing Distribution", {
	refresh(frm) {
		add_create_button(frm, "Transmittal", "make_transmittal_from_distribution", "Drawing Transmittal");
	},
});

frappe.ui.form.on("Request For Information", {
	refresh(frm) {
		add_create_button(frm, "Design Change Request", "make_dcr_from_rfi", "Design Change Request");
		add_create_button(frm, "Design Issue", "make_issue_from_rfi", "Design Issue");
	},
});

frappe.ui.form.on("Design Issue", {
	refresh(frm) {
		add_create_button(frm, "Design Change Request", "make_dcr_from_issue", "Design Change Request");
		add_create_button(frm, "Design NCR", "make_ncr_from_issue", "Design NCR");
	},
});

frappe.ui.form.on("Design Change Request", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.approval === "Approved" && frm.doc.drawing) {
			frm.add_custom_button(
				__("Update Drawing Register"),
				() => {
					frappe.call({
						method: `${DESIGN_MANAGEMENT_METHOD}.update_drawing_register_from_dcr`,
						args: { source_name: frm.doc.name },
						callback() {
							frm.reload_doc();
						},
					});
				},
				__("Create")
			);
		}
	},
});

frappe.ui.form.on("Design NCR", {
	refresh(frm) {
		add_create_button(frm, "Design Issue", "make_issue_from_ncr", "Design Issue");
	},
});
