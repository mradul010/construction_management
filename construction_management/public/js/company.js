const construction_account_filters = {
	default_ra_bill_receivable_account: { account_type: "Receivable" },
	default_retention_receivable_account: { account_type: "Receivable" },
	default_customer_advance_account: { account_type: "Receivable" },
	default_advance_recovery_account: { account_type: "Receivable" },
	default_construction_receipt_account: { root_type: "Asset" },
	default_ra_bill_income_account: { root_type: "Income" },
	default_subcontractor_payable_account: { account_type: "Payable" },
	default_subcontractor_retention_payable_account: { account_type: "Payable" },
	default_subcontractor_advance_account: { account_type: "Payable" },
	default_subcontract_expense_account: { root_type: "Expense" },
};

frappe.ui.form.on("Company", {
	setup(frm) {
		Object.entries(construction_account_filters).forEach(([fieldname, extra_filters]) => {
			frm.set_query(fieldname, () => ({
				filters: {
					company: frm.doc.name,
					is_group: 0,
					disabled: 0,
					...extra_filters,
				},
			}));
		});

		frm.set_query("default_project_cost_center", () => ({
			filters: {
				company: frm.doc.name,
				is_group: 0,
				disabled: 0,
			},
		}));
	},
});
