frappe.ui.form.on("Unloading", {
	refresh(frm) {
		calculate_unloading_parent_total_weight(frm);

		if (frm.doc.docstatus === 1) {
			add_next_stage_button(frm, __("Create Assembly"), "construction_management.construction_activity.activity.make_assembly");
		}
	},

	validate(frm) {
		calculate_unloading_parent_total_weight(frm);
	},

	items_add(frm) {
		calculate_unloading_parent_total_weight(frm);
	},

	items_remove(frm) {
		calculate_unloading_parent_total_weight(frm);
	},

	items_move(frm) {
		calculate_unloading_parent_total_weight(frm);
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

function calculate_unloading_parent_total_weight(frm) {
	let total = 0;
	(frm.doc.items || []).forEach((row) => {
		total += flt(row.total_weight);
	});

	if (flt(frm.doc.total_weight) !== flt(total)) {
		frm.set_value("total_weight", total);
	}
	frm.refresh_field("total_weight");
}
