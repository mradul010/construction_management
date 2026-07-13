const CONSTRUCTION_SALES_ORDER_METHOD =
	"construction_management.construction_management.integrations.sales_order";

frappe.ui.form.on("Sales Order", {
	setup(frm) {
		frm.set_query("boq", () => {
			const filters = {
				docstatus: 1,
				revision_status: ["in", ["Submitted", "Approved", "Active"]],
			};
			if (frm.doc.project) filters.project = frm.doc.project;
			if (frm.doc.customer) filters.client = frm.doc.customer;
			if (frm.doc.company) filters.company = frm.doc.company;
			return { filters };
		});
	},

	refresh(frm) {
		if (
			frm.doc.docstatus === 1 &&
			frm.doc.project &&
			frm.doc.boq &&
			frappe.model.can_create("RA Bill")
		) {
			frm.add_custom_button(
				__("RA Bill"),
				() =>
					frappe.model.open_mapped_doc({
						method: `${CONSTRUCTION_SALES_ORDER_METHOD}.make_ra_bill`,
						frm,
					}),
				__("Create")
			);
		}
	},

	boq(frm) {
		if (!frm.doc.boq || frm.doc.docstatus !== 0) return;
		frappe.db
			.get_value("BOQ", frm.doc.boq, ["project", "client", "company", "currency"])
			.then((r) => {
				const boq = r.message || {};
				const fields = {
					project: boq.project,
					customer: boq.client,
					company: boq.company,
					currency: boq.currency,
				};
				Object.entries(fields).forEach(([fieldname, value]) => {
					if (value && !frm.doc[fieldname]) frm.set_value(fieldname, value);
				});
			});
	},

	project: clear_incompatible_boq,
	customer: clear_incompatible_boq,
	company: clear_incompatible_boq,
});

function clear_incompatible_boq(frm) {
	if (!frm.doc.boq || frm.doc.docstatus !== 0) return;
	frappe.db.get_value("BOQ", frm.doc.boq, ["project", "client", "company"]).then((r) => {
		const boq = r.message || {};
		const incompatible =
			(frm.doc.project && boq.project && frm.doc.project !== boq.project) ||
			(frm.doc.customer && boq.client && frm.doc.customer !== boq.client) ||
			(frm.doc.company && boq.company && frm.doc.company !== boq.company);
		if (incompatible) {
			frm.set_value("boq", "");
			frappe.show_alert({
				message: __("The BOQ was cleared because it does not match the Sales Order."),
				indicator: "orange",
			});
		}
	});
}
