function getNumber(value) {
	const parsed = parseFloat(value);
	return isNaN(parsed) ? 0 : parsed;
}

frappe.ui.form.on("Retention Record", {
	refresh(frm) {
		if (
			!frm.is_new() &&
			["Held", "Partially Released"].includes(frm.doc.status) &&
			getNumber(frm.doc.balance_amount) > 0
		) {
			frm.add_custom_button(__("Release Retention"), () => {
				frappe.prompt(
					[
						{
							fieldname: "release_amount",
							label: __("Release Amount"),
							fieldtype: "Currency",
							reqd: 1,
						},
						{
							fieldname: "release_date",
							label: __("Release Date"),
							fieldtype: "Date",
							default: frappe.datetime.get_today(),
						},
						{
							fieldname: "remarks",
							label: __("Remarks"),
							fieldtype: "Small Text",
						},
					],
					(values) => {
						const releaseAmount = getNumber(values.release_amount);
						const balanceAmount = getNumber(frm.doc.balance_amount);

						if (releaseAmount <= 0) {
							frappe.throw(__("Release Amount must be greater than 0."));
						}

						if (releaseAmount > balanceAmount) {
							frappe.throw(__("Release Amount cannot be greater than Balance Amount."));
						}

						frm.call({
							doc: frm.doc,
							method: "release_retention",
							args: values,
							freeze: true,
							freeze_message: __("Releasing retention..."),
							callback: () => {
								frm.reload_doc();
							},
						});
					},
					__("Release Retention"),
					__("Release"),
				);
			});
		}
	},
});
