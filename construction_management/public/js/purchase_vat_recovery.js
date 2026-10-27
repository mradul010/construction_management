frappe.ui.form.on("Purchase Invoice", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		frm.set_df_property("recoverable_standard_rated_expenses", "read_only", 1);
		if (!frm.perm?.some(p => p.write) || !frappe.user_roles.some(role => ["Accounts Manager", "System Manager"].includes(role))) return;
		frm.add_custom_button(__("Update VAT Recovery"), () => {
			if (frm.is_dirty()) {
				frappe.msgprint(__("Save or reload pending changes before updating VAT recovery"));
				return;
			}
			const dialog = new frappe.ui.Dialog({
				title: __("Update VAT Recovery"),
				fields: [
					{fieldname: "amount", label: __("Recoverable VAT (AED)"), fieldtype: "Currency", options: "AED", default: frm.doc.recoverable_standard_rated_expenses, reqd: 1},
					{fieldname: "reason", label: __("Reason"), fieldtype: "Small Text", reqd: 1},
				],
				primary_action_label: __("Update"),
				async primary_action(values) {
					await frappe.call({
						method: "construction_management.construction_management.report.uae_vat_201_return.purchase_recovery.update_recovery",
						args: {invoice: frm.doc.name, amount: values.amount, reason: values.reason, modified: frm.doc.modified},
						freeze: true,
					});
					dialog.hide();
					await frm.reload_doc();
				},
			});
			dialog.show();
		}, __("Actions"));
	},
});
