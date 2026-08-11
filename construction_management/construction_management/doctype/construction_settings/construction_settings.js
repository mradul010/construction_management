frappe.ui.form.on("Construction Settings", {
	setup: function (frm) {
		frm.set_query("default_material_consumption_expense_account", function () {
			const filters = { is_group: 0 };
			if (frm.doc.default_company) filters.company = frm.doc.default_company;
			return { filters };
		});
	},
});
