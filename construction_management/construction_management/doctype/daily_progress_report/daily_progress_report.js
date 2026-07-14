frappe.ui.form.on("Daily Progress Report", {
	refresh(frm) {
		frm.set_query("project", () => ({
			filters: {
				status: ["!=", "Cancelled"],
			},
		}));
	},
});
