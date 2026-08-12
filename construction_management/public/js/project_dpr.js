frappe.ui.form.on("Project", {
	setup(frm) {
		const construction_account_filters = {
			default_ra_bill_receivable_account: { account_type: "Receivable" },
			default_retention_receivable_account: { root_type: "Asset", account_type: "" },
			default_customer_advance_account: { account_type: "Receivable" },
			default_advance_recovery_account: { account_type: "Receivable" },
			default_construction_receipt_account: { root_type: "Asset" },
			default_ra_bill_income_account: { root_type: "Income" },
			default_subcontractor_payable_account: { account_type: "Payable" },
			default_subcontractor_retention_payable_account: { account_type: "Payable" },
			default_subcontractor_advance_account: { account_type: "Payable" },
			default_subcontract_expense_account: { root_type: "Expense" },
		};

		Object.entries(construction_account_filters).forEach(([fieldname, extra_filters]) => {
			frm.set_query(fieldname, () => ({
				filters: {
					company: frm.doc.company,
					is_group: 0,
					disabled: 0,
					...extra_filters,
				},
			}));
		});
	},

	refresh(frm) {
		if (
			frm.is_new() ||
			(frappe.model.can_create && !frappe.model.can_create("Daily Progress Report"))
		) {
			return;
		}

		frm.add_custom_button(
			__("Daily Progress Report"),
			() => {
				const values = {
					project: frm.doc.name,
					dpr_date: frappe.datetime.get_today(),
					prepared_by: frappe.session.user,
				};

				if (frm.doc.customer) {
					values.customer = frm.doc.customer;
				}

				frappe.new_doc("Daily Progress Report", values);
			},
			__("Create")
		);

		if (!frappe.model.can_create || frappe.model.can_create("Design Package")) {
			frm.add_custom_button(
				__("Design Package"),
				() => {
					frappe.model.open_mapped_doc({
						method: "construction_management.design_management.design_management.make_design_package",
						frm,
					});
				},
				__("Create")
			);
		}
	},
});
