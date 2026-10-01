frappe.ui.form.on("Project Portal File", {
	refresh(frm) {
		frm.set_df_property("customer", "read_only", 1);
	},

	project(frm) {
		set_project_customer(frm);
	},
});

function set_project_customer(frm) {
	if (!frm.doc.project) {
		frm.set_value("customer", "");
		return;
	}

	frappe.model.with_doctype("Project", () => {
		let customer_field = null;
		if (frappe.meta.get_docfield("Project", "customer")) {
			customer_field = "customer";
		} else if (frappe.meta.get_docfield("Project", "client")) {
			customer_field = "client";
		}

		if (!customer_field) {
			frm.set_value("customer", "");
			return;
		}

		frappe.db.get_value("Project", frm.doc.project, customer_field).then((response) => {
			const value = response?.message?.[customer_field] || "";
			frm.set_value("customer", value);
		});
	});
}
