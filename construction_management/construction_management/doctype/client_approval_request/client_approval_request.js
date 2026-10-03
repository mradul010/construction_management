frappe.ui.form.on("Client Approval Request", {
	refresh(frm) {
		frm.set_df_property("customer", "read_only", 1);
	},

	project(frm) {
		set_project_customer(frm);
	},

	source_doctype(frm) {
		set_approval_type_from_source(frm);
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
			frm.refresh_field("customer");
		});
	});
}

function set_approval_type_from_source(frm) {
	if (frm.doc.approval_type || !frm.doc.source_doctype) {
		return;
	}
	const type_by_source = {
		"Drawing Approval": "Drawing",
		"Design Change Request": "Design Change",
		BOQ: "BOQ",
		"RA Bill": "RA Bill",
	};
	if (type_by_source[frm.doc.source_doctype]) {
		frm.set_value("approval_type", type_by_source[frm.doc.source_doctype]);
	}
}
