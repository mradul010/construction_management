function setAccountingOnlyReturnState(frm) {
	if (!frm.fields_dict.accounting_only_return) return;

	const isAccountingOnlyReturn = cint(frm.doc.is_return) && cint(frm.doc.accounting_only_return);
	if (isAccountingOnlyReturn && cint(frm.doc.update_stock)) {
		frm.set_value("update_stock", 0);
	}

	frm.set_df_property("update_stock", "read_only", isAccountingOnlyReturn ? 1 : 0);
	frm.toggle_display("accounting_only_return", cint(frm.doc.is_return));
}

frappe.ui.form.on("Purchase Invoice", {
	refresh(frm) {
		setAccountingOnlyReturnState(frm);
	},

	is_return(frm) {
		if (!cint(frm.doc.is_return) && cint(frm.doc.accounting_only_return)) {
			frm.set_value("accounting_only_return", 0);
		}
		setAccountingOnlyReturnState(frm);
	},

	accounting_only_return(frm) {
		setAccountingOnlyReturnState(frm);
	},
});
