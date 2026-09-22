frappe.ui.form.on("Construction Activity Item", {
	qty(frm, cdt, cdn) {
		set_total_weight(cdt, cdn);
	},
	unit_weight(frm, cdt, cdn) {
		set_total_weight(cdt, cdn);
	},
});

function set_total_weight(cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "total_weight", (flt(row.qty) || 0) * (flt(row.unit_weight) || 0));
}
