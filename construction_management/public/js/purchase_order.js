const CONSTRUCTION_PO_METHOD =
	"construction_management.construction_management.purchase_order";

frappe.ui.form.on("Purchase Order", {
	refresh(frm) {
		if (!frm.doc.sc_work_order || frm.doc.docstatus !== 1 || frm.doc.status === "Cancelled") {
			return;
		}

		frm.add_custom_button(
			__("SC Bill"),
			function () {
				frappe.model.open_mapped_doc({
					method: `${CONSTRUCTION_PO_METHOD}.make_sc_bill`,
					frm: frm,
				});
			},
			__("Create"),
		);
	},
});
