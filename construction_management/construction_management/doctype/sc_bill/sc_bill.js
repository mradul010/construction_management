const SC_BILL_METHOD =
	"construction_management.construction_management.doctype.sc_bill.sc_bill";

function scBillNumber(value) {
	const parsed = parseFloat(value);
	return isNaN(parsed) ? 0 : parsed;
}

function toggleScBillSections(frm) {
	const isMeasured = frm.doc.billing_type === "Measured";
	frm.toggle_display("bill_items_section", isMeasured);
	frm.toggle_display("amount_entry_section", !isMeasured);
}

function calculateScBillRow(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row) return;

	const currentQty = scBillNumber(row.current_qty);
	const previousQty = scBillNumber(row.previous_qty);
	const assignedQty = scBillNumber(row.assigned_qty);
	const rate = scBillNumber(row.sc_rate);
	const currentAmount = currentQty * rate;
	const previousAmount = scBillNumber(row.previous_amount);

	frappe.model.set_value(cdt, cdn, "current_amount", currentAmount);
	frappe.model.set_value(cdt, cdn, "cumulative_qty", previousQty + currentQty);
	frappe.model.set_value(cdt, cdn, "balance_qty", Math.max(assignedQty - previousQty - currentQty, 0));
	frappe.model.set_value(cdt, cdn, "cumulative_amount", previousAmount + currentAmount);
	frappe.model.set_value(cdt, cdn, "balance_amount", Math.max(assignedQty * rate - previousAmount - currentAmount, 0));
	frappe.model.set_value(cdt, cdn, "bill_amount", currentAmount);
	frm.trigger("calculate_totals");
}

function calculateScBillTotals(frm) {
	let grossAmount = 0;
	if (frm.doc.billing_type === "Measured") {
		(frm.doc.items || []).forEach((row) => {
			grossAmount += scBillNumber(row.current_amount);
		});
	} else {
		grossAmount = scBillNumber(frm.doc.bill_amount);
	}

	const retentionAmount = grossAmount * (scBillNumber(frm.doc.retention_percent) / 100);
	const netPayable = grossAmount - retentionAmount - scBillNumber(frm.doc.ld_deduction);
	const previousBilled = scBillNumber(frm.doc.previous_billed);
	const cumulativeBilled = previousBilled + grossAmount;

	frm.set_value("gross_amount", grossAmount);
	frm.set_value("retention_amount", retentionAmount);
	frm.set_value("net_payable", netPayable);
	frm.set_value("cumulative_billed", cumulativeBilled);
	frm.set_value("balance_amount", Math.max(scBillNumber(frm.doc.contract_value) - cumulativeBilled, 0));
}

function loadWorkOrderContext(frm) {
	if (!frm.doc.sc_work_order) return;

	frappe.call({
		method: `${SC_BILL_METHOD}.get_work_order_context`,
		args: {
			sc_work_order: frm.doc.sc_work_order,
		},
		callback(r) {
			const context = r.message || {};
			frm.set_value({
				project: context.project,
				supplier: context.supplier,
				billing_type: context.billing_type,
				boq: context.boq,
				company: context.company,
				currency: context.currency,
				contract_value: context.contract_value,
			});

			if (context.billing_type === "Measured" && frm.doc.docstatus === 0 && !(frm.doc.items || []).length) {
				(context.items || []).forEach((source) => {
					const row = frm.add_child("items");
					Object.keys(source).forEach((fieldname) => {
						row[fieldname] = source[fieldname];
					});
					row.current_qty = 0;
					row.current_amount = 0;
				});
				frm.refresh_field("items");
			}

			toggleScBillSections(frm);
			calculateScBillTotals(frm);
		},
	});
}

frappe.ui.form.on("SC Bill", {
	setup(frm) {
		frm.set_query("sc_work_order", function () {
			return {
				filters: {
					docstatus: 1,
				},
			};
		});
	},

	refresh(frm) {
		toggleScBillSections(frm);

		if (frm.doc.docstatus === 1 && frm.doc.status === "Submitted") {
			frm.add_custom_button(
				__("Approve"),
				function () {
					frm.call("approve").then(() => frm.reload_doc());
				},
				__("Status"),
			);
		}

		if (frm.doc.docstatus === 1 && frm.doc.status === "Approved" && !frm.doc.purchase_invoice) {
			frm.add_custom_button(
				__("Create Purchase Invoice"),
				function () {
					frm.call("create_purchase_invoice").then(() => frm.reload_doc());
				},
				__("Create"),
			);
		}

		if (frm.doc.purchase_invoice) {
			frm.add_custom_button(
				__("View Purchase Invoice"),
				function () {
					frappe.set_route("Form", "Purchase Invoice", frm.doc.purchase_invoice);
				},
				__("View"),
			);
		}
	},

	sc_work_order(frm) {
		loadWorkOrderContext(frm);
	},

	billing_type(frm) {
		toggleScBillSections(frm);
		calculateScBillTotals(frm);
	},

	bill_amount: calculateScBillTotals,
	retention_percent: calculateScBillTotals,
	ld_deduction: calculateScBillTotals,
	calculate_totals: calculateScBillTotals,
});

frappe.ui.form.on("SC Bill Item", {
	current_qty: calculateScBillRow,
	items_remove(frm) {
		frm.trigger("calculate_totals");
	},
});
