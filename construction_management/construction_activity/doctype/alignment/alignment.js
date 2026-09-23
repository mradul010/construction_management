frappe.ui.form.on("Alignment", {
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			add_next_stage_button(frm, __("Create Completion"), "construction_management.construction_activity.activity.make_completion");
		}
	},
});

function add_next_stage_button(frm, label, method) {
	frm.add_custom_button(label, () => {
		frappe.model.open_mapped_doc({
			method,
			frm,
		});
	});
}
