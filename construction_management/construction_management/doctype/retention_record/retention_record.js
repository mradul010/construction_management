function getNumber(value) {
	const parsed = parseFloat(value);
	return isNaN(parsed) ? 0 : parsed;
}

frappe.ui.form.on("Retention Record", {
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
				__("Receive Retention"),
				() => {
					frm.call({
						doc: frm.doc,
						method: "receive_retention",
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

		const can_view_invoice = Boolean(frm.doc.retention_release_invoice);
		if (can_view_invoice) {
			frm.add_custom_button(
				__("View Sales Invoice"),
				() => {
					frappe.set_route("Form", "Sales Invoice", frm.doc.retention_release_invoice);
				},
				__("Actions"),
			);

			frm.add_custom_button(
				__("Sync Status"),
				() => {
					frm.call({
						doc: frm.doc,
						method: "sync_status_from_sales_invoice",
						freeze: true,
						freeze_message: __("Syncing retention status..."),
						callback: () => {
							frm.reload_doc();
						},
					});
				},
				__("Actions"),
			);
		}

		const can_cancel = frm.doc.docstatus !== 2 && (frm.doc.status || "") !== "Cancelled";
		if (can_cancel) {
			frm.add_custom_button(
				__("Cancel Retention Record"),
				() => {
					frappe.confirm(
						__(
							"Cancel this retention record? This will not cancel the linked Sales Invoice.",
						),
						() => {
							frm.call({
								doc: frm.doc,
								method: "cancel_retention_record",
								freeze: true,
								freeze_message: __("Cancelling retention record..."),
								callback: () => {
									frm.reload_doc();
								},
							});
						},
					);
				},
				__("Actions"),
			);
		}
	},
});
