if (!window.construction_activity_item_sync_bound) {
	window.construction_activity_item_sync_bound = true;

	frappe.ui.form.on("Construction Activity Item", {
		mark_no(frm, cdt, cdn) {
			ensure_activity_item(cdt, cdn, "mark_no", "item_code");
		},
		mark_item(frm, cdt, cdn) {
			ensure_activity_item(cdt, cdn, "mark_item", "mark_item_item_code");
		},
		qty(frm, cdt, cdn) {
			set_total_weight(cdt, cdn).then(() => calculate_activity_parent_total_weight(frm));
		},
		unit_weight(frm, cdt, cdn) {
			set_total_weight(cdt, cdn).then(() => calculate_activity_parent_total_weight(frm));
			ensure_activity_item(cdt, cdn, "mark_no", "item_code");
			ensure_activity_item(cdt, cdn, "mark_item", "mark_item_item_code");
		},
		total_weight(frm) {
			calculate_activity_parent_total_weight(frm);
		},
	});
}

function ensure_activity_item(cdt, cdn, source_field, target_field) {
	const row = locals[cdt][cdn];
	const itemValue = (row[source_field] || "").trim();
	if (!itemValue) {
		frappe.model.set_value(cdt, cdn, target_field, "");
		return;
	}

	const signatureField = `__last_${target_field}_sync_signature`;
	const signature = `${itemValue}::${row.unit_weight || ""}`;
	if (row[signatureField] === signature && row[target_field]) {
		return;
	}
	row[signatureField] = signature;

	frappe.call({
		method: "construction_management.construction_activity.item_sync.ensure_item_for_mark",
		args: {
			mark_no: itemValue,
			unit_weight: row.unit_weight,
		},
		callback(r) {
			if (r.message && r.message.item) {
				frappe.model.set_value(cdt, cdn, target_field, r.message.item);
			}
		},
	});
}

function set_total_weight(cdt, cdn) {
	const row = locals[cdt][cdn];
	return frappe.model.set_value(cdt, cdn, "total_weight", (flt(row.qty) || 0) * (flt(row.unit_weight) || 0));
}

function calculate_activity_parent_total_weight(frm) {
	if (!frm.fields_dict.total_weight) {
		return;
	}

	let total = 0;
	(frm.doc.items || []).forEach((row) => {
		total += flt(row.total_weight);
	});

	if (flt(frm.doc.total_weight) !== flt(total)) {
		frm.set_value("total_weight", total);
	}
	frm.refresh_field("total_weight");
}
