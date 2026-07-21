const SC_WORK_ORDER_METHOD =
	"construction_management.construction_management.doctype.sc_work_order.sc_work_order";

function fltValue(value) {
	const parsed = parseFloat(value);
	return isNaN(parsed) ? 0 : parsed;
}

function calculateWorkOrderRow(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row) return;

	const assignedQty = fltValue(row.assigned_qty);
	const boqRate = fltValue(row.boq_rate);
	const scRate = fltValue(row.sc_rate);
	const boqAmount = assignedQty * boqRate;
	const scAmount = assignedQty * scRate;
	const marginAmount = boqAmount - scAmount;

	frappe.model.set_value(cdt, cdn, "boq_amount", boqAmount);
	frappe.model.set_value(cdt, cdn, "sc_amount", scAmount);
	frappe.model.set_value(cdt, cdn, "margin_amount", marginAmount);
	frappe.model.set_value(cdt, cdn, "margin_percent", boqAmount ? (marginAmount / boqAmount) * 100 : 0);
	frm.trigger("calculate_totals");
}

function toggleWorkOrderSections(frm) {
	const isStandalone = frm.doc.scope_type === "Standalone";
	frm.toggle_display("boq", !isStandalone);
	frm.toggle_display("scope_section", !isStandalone);
	frm.toggle_display("standalone_section", isStandalone);
}

frappe.ui.form.on("SC Work Order", {
	setup(frm) {
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
				query: `${SC_WORK_ORDER_METHOD}.search_boq_items`,
				filters: {
					boq: frm.doc.boq,
				},
			};
		});
	},

	refresh(frm) {
		toggleWorkOrderSections(frm);

		if (frm.doc.docstatus === 1 && frm.doc.status !== "Cancelled") {
			frm.add_custom_button(
				__("Create SC Bill"),
				function () {
					frappe.model.open_mapped_doc({
						method: `${SC_WORK_ORDER_METHOD}.make_sc_bill`,
						frm: frm,
					});
				},
				__("Create"),
			);
		}
	},

	project(frm) {
		if (!frm.doc.project) {
			frm.set_value("boq", "");
		}
	},

	boq(frm) {
		if (!frm.doc.boq) return;
		frappe.db.get_value("BOQ", frm.doc.boq, ["project", "company", "currency"]).then((r) => {
			const boq = r.message || {};
			frm.set_value({
				project: boq.project || frm.doc.project,
				company: boq.company || frm.doc.company,
				currency: boq.currency || frm.doc.currency,
			});
		});
	},

	scope_type(frm) {
		toggleWorkOrderSections(frm);
		if (frm.doc.scope_type === "Standalone") {
			frm.set_value("boq", "");
		}
		frm.trigger("calculate_totals");
	},

	standalone_contract_value(frm) {
		frm.trigger("calculate_totals");
	},

	calculate_totals(frm) {
		let boqAmount = 0;
		let scAmount = 0;
		(frm.doc.items || []).forEach((row) => {
			boqAmount += fltValue(row.boq_amount);
			scAmount += fltValue(row.sc_amount);
		});

		if (frm.doc.scope_type === "Standalone") {
			boqAmount = 0;
			scAmount = fltValue(frm.doc.standalone_contract_value);
		}

		const marginAmount = boqAmount - scAmount;
		frm.set_value("boq_amount", boqAmount);
		frm.set_value("sc_amount", scAmount);
		frm.set_value("margin_amount", marginAmount);
		frm.set_value("contract_value", scAmount);
		frm.set_value("margin_percent", boqAmount ? (marginAmount / boqAmount) * 100 : 0);
		frm.set_value("balance_amount", Math.max(scAmount - fltValue(frm.doc.total_billed), 0));
	},
});

frappe.ui.form.on("SC Work Order Item", {
	boq_item(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row || !row.boq_item || !frm.doc.boq) return;

		frappe.call({
			method: `${SC_WORK_ORDER_METHOD}.get_boq_item_details`,
			args: {
				boq: frm.doc.boq,
				boq_item: row.boq_item,
			},
			callback(r) {
				if (!r.message || !r.message.boq_item) {
					frappe.msgprint(__("Unable to fetch BOQ Item details."));
					return;
				}
				Object.keys(r.message).forEach((fieldname) => {
					frappe.model.set_value(cdt, cdn, fieldname, r.message[fieldname]);
				});
				calculateWorkOrderRow(frm, cdt, cdn);
			},
		});
	},

	assigned_qty: calculateWorkOrderRow,
	sc_rate: calculateWorkOrderRow,
	items_remove(frm) {
		frm.trigger("calculate_totals");
	},
});
