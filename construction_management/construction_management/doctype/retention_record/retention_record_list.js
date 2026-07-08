frappe.listview_settings["Retention Record"] = {
	onload(listview) {
		listview.page.add_actions_menu_item(__("Create Sales Invoice"), () => {
			const selected = listview.get_checked_items();
			const retention_records = (selected || []).map((row) => row.name).filter(Boolean);

			if (!retention_records.length) {
				frappe.msgprint(__("Please select at least one Retention Record."));
				return;
			}

			frappe.call({
				method:
					"construction_management.construction_management.doctype.retention_record.retention_record.create_sales_invoice_for_retention_records",
				args: {
					retention_records: retention_records,
				},
				freeze: true,
				freeze_message: __("Creating Sales Invoice..."),
				callback(r) {
					if (r.message) {
						frappe.set_route("Form", "Sales Invoice", r.message);
					}
				},
			});
		});
	},
};
