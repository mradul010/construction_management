frappe.ui.form.on("RA Bill", {
	setup: function (frm) {
		frm.set_query("boq", function () {
			return {
				filters: {
					project: frm.doc.project,
					docstatus: 1,
				},
			};
		});

		frm.set_query("boq_item", "items", function () {
			return {
				filters: {
					parent: frm.doc.boq,
				},
			};
		});
	},

	refresh: function (frm) {
		if (frm.doc.status === "Submitted" && frm.doc.docstatus === 1) {
			frm.add_custom_button(
				"Approve",
				function () {
					frappe.confirm("Are you sure you want to approve this RA Bill?", function () {
						frappe.db.set_value("RA Bill", frm.doc.name, "status", "Approved").then(() => {
							frm.reload_doc();
							frappe.show_alert(
								{
									message: "RA Bill Approved",
									indicator: "green",
								},
								3,
							);
						});
					});
				},
				"Actions",
			);
		}

		if (frm.doc.status === "Approved" && !frm.doc.sales_invoice) {
			frm.add_custom_button(
				"Create Sales Invoice",
				function () {
					frappe.confirm(
						`Create Sales Invoice for ${frappe.format(frm.doc.net_payable, {
							fieldtype: "Currency",
							options: frm.doc.currency,
						})}?`,
						function () {
							frappe.call({
								method: "create_sales_invoice",
								doc: frm.doc,
								callback: function (r) {
									if (r.message) {
										frm.reload_doc();
									}
								},
							});
						},
					);
				},
				"Actions",
			);
		}

		if (frm.doc.sales_invoice) {
			frm.add_custom_button(
				frm.doc.sales_invoice,
				function () {
					frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
				},
				"View",
			);
		}
	},

	project: function (frm) {
		if (frm.doc.boq) {
			frm.set_value("boq", null);
			frm.clear_table("items");
			frm.refresh_field("items");
		}
	},

	boq: function (frm) {
		if (frm.doc.items && frm.doc.items.length > 0) {
			frappe.confirm("Changing the BOQ will clear all current items. Continue?", function () {
				frm.clear_table("items");
				frm.refresh_field("items");
			});
		}
	},

	retention_percent: function (frm) {
		frm.trigger("recalculate_totals");
	},

	recalculate_totals: function (frm) {
		let gross = 0;

		(frm.doc.items || []).forEach((row) => {
			gross += row.current_amount || 0;
		});

		const retention = gross * ((frm.doc.retention_percent || 0) / 100);

		frappe.model.set_value(frm.doctype, frm.docname, "gross_amount", gross);
		frappe.model.set_value(frm.doctype, frm.docname, "retention_amount", retention);
		frappe.model.set_value(frm.doctype, frm.docname, "net_payable", gross - retention);
	},
});

frappe.ui.form.on("RA Bill Item", {
	boq_item: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];

		if (!row.boq_item) return;

		frappe.db
			.get_value("BOQ Item", row.boq_item, ["item_name", "qty", "unit_rate", "uom"])
			.then((r) => {
				if (r.message) {
					frappe.model.set_value(cdt, cdn, "item_name", r.message.item_name);
					frappe.model.set_value(cdt, cdn, "boq_qty", r.message.qty);
					frappe.model.set_value(cdt, cdn, "boq_rate", r.message.unit_rate);
					frappe.model.set_value(cdt, cdn, "uom", r.message.uom);
				}
			});
	},

	current_qty: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const currentQty = row.current_qty || 0;
		const prevQty = row.prev_cumulative_qty || 0;
		const boqQty = row.boq_qty || 0;
		const cumulativeQty = prevQty + currentQty;
		const amount = currentQty * (row.boq_rate || 0);

		frappe.model.set_value(cdt, cdn, "cumulative_qty", cumulativeQty);
		frappe.model.set_value(cdt, cdn, "completion_pct", boqQty ? (cumulativeQty / boqQty) * 100 : 0);
		frappe.model.set_value(cdt, cdn, "current_amount", amount);
		frm.trigger("recalculate_totals");
	},

	items_remove: function (frm) {
		frm.trigger("recalculate_totals");
	},
});

frappe.ui.form.on("RA Bill Item", {
	boq_item: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];

		frappe.db.get_value("BOQ Item", row.boq_item, "item_name", (r) => {
			if (r.message) {
				frappe.model.set_value(cdt, cdn, "item_name", r.message.item_name);
			}
		});
	},
});