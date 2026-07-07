function getNumber(value) {
	const parsed = parseFloat(value);
	return isNaN(parsed) ? 0 : parsed;
}

frappe.ui.form.on("Retention Record", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		const can_create_invoice =
			["Held", "Partially Released"].includes(frm.doc.status || "") &&
			getNumber(frm.doc.balance_amount) > 0 &&
			!frm.doc.retention_release_invoice &&
			Boolean(frm.doc.customer) &&
			Boolean(frm.doc.project);

		if (can_create_invoice) {
			frm.add_custom_button(__("Create Sales Invoice"), () => {
				frm.call({
					doc: frm.doc,
					method: "create_sales_invoice",
					freeze: true,
					freeze_message: __("Creating sales invoice..."),
					callback: (r) => {
						if (r.message) {
							frappe.set_route("Form", "Sales Invoice", r.message);
						}
					},
				});
			});
		}

		const can_view_invoice = Boolean(frm.doc.retention_release_invoice);

		if (can_view_invoice) {
			frm.add_custom_button(__("View Sales Invoice"), () => {
				frappe.set_route("Form", "Sales Invoice", frm.doc.retention_release_invoice);
			});
		}
	},
});
