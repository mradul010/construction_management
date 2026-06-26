const boqItemLabels = {};

frappe.form.link_formatters["BOQ Item"] = function (value, doc) {
	return (doc && doc.item_name) || boqItemLabels[value] || value;
};

if (frappe.ui.form.ControlLink && !frappe.ui.form.ControlLink.prototype.boq_item_label_only) {
	const originalAwesompleteFilter = frappe.ui.form.ControlLink.prototype.custom_awesomplete_filter;

	frappe.ui.form.ControlLink.prototype.custom_awesomplete_filter = function (awesomplete) {
		if (originalAwesompleteFilter) {
			originalAwesompleteFilter.call(this, awesomplete);
		}

		if (this.get_options() !== "BOQ Item") return;

		const control = this;

		awesomplete.item = function (item) {
			const d = this.get_item(item.value);
			if (!d.label) {
				d.label = d.value;
			}

			const label = frappe.utils.escape_html(control.get_translated(d.label));
			const html = d.html || `<strong>${label}</strong>`;

			return $(`<div role="option">`)
				.on("click", (event) => {
					control.awesomplete.select(event.currentTarget, event.currentTarget);
					control.show_link_and_clear_buttons();
				})
				.data("item.autocomplete", d)
				.prop("aria-selected", "false")
				.html(`<p title="${label}">${html}</p>`)
				.get(0);
		};
	};

	frappe.ui.form.ControlLink.prototype.boq_item_label_only = true;
}

function setBoqItemDetails(frm, cdt, cdn, options = {}) {
	const row = locals[cdt][cdn];

	if (!row || !row.boq_item) return Promise.resolve();

	return frappe.db
		.get_value("BOQ Item", row.boq_item, ["item_name", "qty", "unit_rate", "uom"])
		.then((r) => {
			if (!r.message) return;

			boqItemLabels[row.boq_item] = r.message.item_name || row.boq_item;

			frappe.model.set_value(cdt, cdn, "item_name", r.message.item_name);

			if (!options.labelOnly) {
				frappe.model.set_value(cdt, cdn, "boq_qty", r.message.qty);
				frappe.model.set_value(cdt, cdn, "boq_rate", r.message.unit_rate);
				frappe.model.set_value(cdt, cdn, "uom", r.message.uom);
			}

			frm.refresh_field("items");
		});
}

function hydrateBoqItemLabels(frm) {
	const rows = (frm.doc.items || []).filter((row) => row.boq_item);

	rows.forEach((row) => {
		if (row.item_name) {
			boqItemLabels[row.boq_item] = row.item_name;
			return;
		}

		setBoqItemDetails(frm, row.doctype, row.name, { labelOnly: true });
	});
}

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
				query: "construction_management.construction_management.api.boq_item_search",
				filters: {
					parent: frm.doc.boq,
				},
			};
		});
	},

	refresh: function (frm) {
		hydrateBoqItemLabels(frm);

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
		setBoqItemDetails(frm, cdt, cdn);
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
