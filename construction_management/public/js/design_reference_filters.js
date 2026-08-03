(() => {
	const parent_tables = {
		"BOQ": ["items"],
		"Sales Order": ["items"],
		"Purchase Order": ["items"],
		"Purchase Invoice": ["items"],
		"Material Request": ["items"],
		"Stock Entry": ["items"],
		"Purchase Receipt": ["items"],
		"RA Bill": ["items"],
		"SC Work Order": ["items"],
		"SC Bill": ["items"],
	};

	const child_tables = [
		"BOQ Item",
		"Sales Order Item",
		"Purchase Order Item",
		"Purchase Invoice Item",
		"Material Request Item",
		"Stock Entry Detail",
		"Purchase Receipt Item",
		"RA Bill Item",
		"SC Work Order Item",
		"SC Bill Item",
	];

	function set_revision_query(frm, tablefield) {
		frm.set_query("drawing_revision", tablefield, (doc, cdt, cdn) => {
			const row = locals[cdt] && locals[cdt][cdn];
			const filters = {
				ifc: 1,
				status: "Issued For Construction",
			};
			if (row && row.drawing) {
				filters.drawing = row.drawing;
			}
			return { filters };
		});
	}

	Object.keys(parent_tables).forEach((doctype) => {
		frappe.ui.form.on(doctype, {
			setup(frm) {
				(parent_tables[doctype] || []).forEach((tablefield) => {
					if (frm.fields_dict[tablefield]) {
						set_revision_query(frm, tablefield);
					}
				});
			},
		});
	});

	child_tables.forEach((doctype) => {
		frappe.ui.form.on(doctype, {
			drawing_revision(frm, cdt, cdn) {
				const row = locals[cdt] && locals[cdt][cdn];
				if (!row) {
					return;
				}
				row.ifc_revision = row.drawing_revision || "";
				frm.refresh_field(row.parentfield || "items");
			},
		});
	});
})();
