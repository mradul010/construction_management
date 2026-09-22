frappe.ui.form.on("Construction BOM", {
	setup(frm) {
		frm.set_query("boq", () => {
			const filters = {};
			if (frm.doc.project) {
				filters.project = frm.doc.project;
			}
			return { filters };
		});
	},

	project(frm) {
		if (frm.doc.boq) {
			frappe.db.get_value("BOQ", frm.doc.boq, "project").then((response) => {
				const boqProject = response && response.message && response.message.project;
				if (boqProject && boqProject !== frm.doc.project) {
					frm.set_value("boq", "");
				}
			});
		}
	},

	boq(frm) {
		if (!frm.doc.boq || frm.doc.project) {
			return;
		}

		frappe.db.get_value("BOQ", frm.doc.boq, "project").then((response) => {
			const boqProject = response && response.message && response.message.project;
			if (boqProject) {
				frm.set_value("project", boqProject);
			}
		});
	},

	validate(frm) {
		sync_construction_bom_items(frm);
	},

	items_add(frm) {
		sync_construction_bom_items(frm);
	},

	items_remove(frm) {
		sync_construction_bom_items(frm);
	},

	items_move(frm) {
		sync_construction_bom_items(frm);
	},
});

frappe.ui.form.on("Construction BOM Item", {
	qty(frm, cdt, cdn) {
		update_construction_bom_item(frm, cdt, cdn);
	},

	unit_weight(frm, cdt, cdn) {
		update_construction_bom_item(frm, cdt, cdn);
	},
});

function sync_construction_bom_items(frm) {
	(frm.doc.items || []).forEach((row) => {
		row.serial_no = row.idx;
		row.total_weight = flt(row.qty) * flt(row.unit_weight);
		row.total_wt_mt = flt(row.total_weight) / 1000;
	});
	frm.refresh_field("items");
}

function update_construction_bom_item(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const totalWeight = flt(row.qty) * flt(row.unit_weight);
	frappe.model.set_value(cdt, cdn, "serial_no", row.idx);
	frappe.model.set_value(cdt, cdn, "total_weight", totalWeight);
	frappe.model.set_value(cdt, cdn, "total_wt_mt", totalWeight / 1000);
}
