frappe.ui.form.on("VAT 201 Filing", {
	refresh(frm) {
		if (frm.is_new()) {
			frm.get_field("vat_return_preview").$wrapper.html(
				`<p class="text-muted">${__("Save the Draft to generate the VAT 201 form preview.")}</p>`
			);
			return;
		}
		frappe.call({
			method: "construction_management.construction_management.report.uae_vat_201_return.filing.preview",
			args: {name: frm.doc.name},
		}).then(({message}) => {
			if (frm.doc.name)
				frm.get_field("vat_return_preview").$wrapper.html(message);
		});
		if (frm.doc.docstatus === 1 && flt(frm.doc.outstanding_amount) > 0) {
			frm.add_custom_button(__("VAT Payment"), () => {
				frappe.new_doc("VAT 201 Payment", {
					filing: frm.doc.name,
					company: frm.doc.company,
					from_date: frm.doc.from_date,
					to_date: frm.doc.to_date,
					outstanding_before_payment: frm.doc.outstanding_amount,
					payment_amount: frm.doc.outstanding_amount,
				});
			}, __("Create"));
		}
	},
});
