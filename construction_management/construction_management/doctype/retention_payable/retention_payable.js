function getNumber(value) {
	const parsed = parseFloat(value);
	return isNaN(parsed) ? 0 : parsed;
}

frappe.ui.form.on("Retention Payable", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		const can_create_payment =
			frm.doc.docstatus !== 2 &&
			["Held", "Partially Released"].includes(frm.doc.status || "") &&
			getNumber(frm.doc.balance_amount) > 0;

		if (can_create_payment) {
			frm.add_custom_button(
				__("Release Retention"),
				() => {
					frm.call({
						doc: frm.doc,
						method: "release_retention",
						freeze: true,
						freeze_message: __("Creating draft Payment Entry..."),
						callback: (r) => {
							if (r.message) {
								frappe.set_route("Form", "Payment Entry", r.message);
								frm.reload_doc();
							}
						},
					});
				},
				__("Actions"),
			);
		}

		if (frm.doc.last_payment_entry) {
			frm.add_custom_button(
				__("View Payment Entry"),
				() => {
					frappe.set_route("Form", "Payment Entry", frm.doc.last_payment_entry);
				},
				__("Actions"),
			);
		}

		if (frm.doc.purchase_invoice) {
			frm.add_custom_button(
				__("View Purchase Invoice"),
				() => {
					frappe.set_route("Form", "Purchase Invoice", frm.doc.purchase_invoice);
				},
				__("Actions"),
			);
		}

		const can_cancel = frm.doc.docstatus !== 2 && (frm.doc.status || "") !== "Cancelled";
		if (can_cancel) {
			frm.add_custom_button(
				__("Cancel Retention Payable"),
				() => {
					frappe.confirm(
						__("Cancel this retention payable record? This will not cancel linked invoices or payments."),
						() => {
							frm.call({
								doc: frm.doc,
								method: "cancel_retention_payable",
								freeze: true,
								freeze_message: __("Cancelling retention payable..."),
								callback: () => frm.reload_doc(),
							});
						},
					);
				},
				__("Actions"),
			);
		}
	},
});
