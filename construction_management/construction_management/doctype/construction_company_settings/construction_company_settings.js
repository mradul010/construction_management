frappe.ui.form.on("Construction Company Settings", {
	setup(frm) {
		const accountFields = [
			"retention_receivable_account",
			"retention_payable_account",
			"customer_advance_account",
			"supplier_advance_account",
			"ra_bill_receivable_account",
			"ra_bill_income_account",
			"construction_receipt_account",
			"subcontractor_payable_account",
			"subcontract_expense_account",
		];

		accountFields.forEach((fieldname) => {
			frm.set_query(fieldname, () => ({
				filters: {
					company: frm.doc.company,
					is_group: 0,
				},
			}));
		});

		frm.set_query("default_cost_center", () => ({
			filters: {
				company: frm.doc.company,
				is_group: 0,
			},
		}));

		frm.set_query("default_sales_taxes_and_charges_template", () => ({
			filters: {
				company: frm.doc.company,
			},
		}));

		frm.set_query("default_purchase_taxes_and_charges_template", () => ({
			filters: {
				company: frm.doc.company,
			},
		}));
	},
});
