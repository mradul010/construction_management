frappe.ui.form.on("Project", {
	refresh(frm) {
		if (
			frm.is_new() ||
			(frappe.model.can_create && !frappe.model.can_create("Daily Progress Report"))
		) {
			return;
		}

		frm.add_custom_button(
			__("Daily Progress Report"),
			() => {
				const values = {
					project: frm.doc.name,
					dpr_date: frappe.datetime.get_today(),
					prepared_by: frappe.session.user,
				};

				if (frm.doc.customer) {
					values.customer = frm.doc.customer;
				}

				frappe.new_doc("Daily Progress Report", values);
			},
			__("Create")
		);
	},
});
