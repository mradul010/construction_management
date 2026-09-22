const construction_print_formats = [
	"RA Bill Certificate",
	"RA Bill",
	"RA Bill Print Format",
	"BOQ Print Formate",
];

frappe.ui.form.on("Print Format", {
	refresh(frm) {
		if (!construction_print_formats.includes(frm.doc.name) || frm.is_new()) {
			return;
		}

		setTimeout(() => {
			frm.page.clear_inner_toolbar();

			if (!frm.doc.custom_format && frm.doc.doc_type) {
				frm.add_custom_button(__("Edit Format"), () => {
					frappe.set_route("print-format-builder", frm.doc.name);
				});
			} else if (frm.doc.custom_format && !frm.doc.raw_printing) {
				frm.set_df_property("html", "reqd", 1);
			}

			if (frappe.model.can_write("Customize Form") && frm.doc.doc_type) {
				frappe.model.with_doctype(frm.doc.doc_type, () => {
					const current_format = frappe.get_meta(frm.doc.doc_type).default_print_format;
					if (current_format === frm.doc.name) {
						return;
					}

					frm.add_custom_button(__("Set as Default"), () => {
						frappe.call({
							method: "frappe.printing.doctype.print_format.print_format.make_default",
							args: {
								name: frm.doc.name,
							},
							callback() {
								frm.refresh();
							},
						});
					});
				});
			}
		}, 0);
	},
});
