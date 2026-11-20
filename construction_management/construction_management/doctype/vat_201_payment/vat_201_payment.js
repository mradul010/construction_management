frappe.ui.form.on("VAT 201 Payment", {
	setup(frm) {
		frm.set_query("filing", () => ({filters: {docstatus: 1}}));
		frm.set_query("bank_account", () => ({
			filters: {company: frm.doc.company, is_group: 0, account_type: ["in", ["Bank", "Cash"]]},
		}));
	},
	filing(frm) {
		if (!frm.doc.filing) return;
		frappe.call({
			method: "construction_management.construction_management.report.uae_vat_201_return.filing.payment_context",
			args: {filing: frm.doc.filing},
		}).then(({message}) => {
			frm.set_value({
				company: message.company,
				from_date: message.from_date,
				to_date: message.to_date,
				outstanding_before_payment: message.outstanding_amount,
				payment_amount: message.outstanding_amount,
			});
		});
	},
});
