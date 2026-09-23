if (!window.construction_activity_item_sync_bound) {
	window.construction_activity_item_sync_bound = true;

	frappe.ui.form.on("Construction Activity Item", {
		mark_no(frm, cdt, cdn) {
			ensure_activity_item(cdt, cdn);
		},
		qty(frm, cdt, cdn) {
			set_total_weight(cdt, cdn);
		},
		unit_weight(frm, cdt, cdn) {
			set_total_weight(cdt, cdn);
			ensure_activity_item(cdt, cdn);
		},
	});
}

function ensure_activity_item(cdt, cdn) {
	const row = locals[cdt][cdn];
	const mark_no = (row.mark_no || "").trim();
	if (!mark_no) {
		frappe.model.set_value(cdt, cdn, "mark_item", "");
		return;
	}

	const signature = `${mark_no}::${row.unit_weight || ""}`;
	if (row.__last_item_sync_signature === signature && row.mark_item) {
		return;
	}
	row.__last_item_sync_signature = signature;

	frappe.call({
		method: "construction_management.construction_activity.item_sync.ensure_item_for_mark",
		args: {
			mark_no,
			unit_weight: row.unit_weight,
		},
		callback(r) {
			if (r.message && r.message.item) {
				frappe.model.set_value(cdt, cdn, "mark_item", r.message.item);
			}
		},
	});
}

function set_total_weight(cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "total_weight", (flt(row.qty) || 0) * (flt(row.unit_weight) || 0));
}
