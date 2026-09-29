frappe.ui.form.on("Daily Progress Report", {
	refresh(frm) {
		frm.set_query("project", () => ({
			filters: {
				status: ["!=", "Cancelled"],
			},
		}));

		frm.set_query("work_location", "tasks_completed", () => {
			if (!frm.doc.project) {
				return {
					filters: {
						disabled: 0,
					},
				};
			}

			return {
				filters: {
					disabled: 0,
					project: ["in", [frm.doc.project, ""]],
				},
			};
		});
	},
});

const dpr_worker_fields = [
	"fitter",
	"welder",
	"gas_cutter",
	"rigger",
	"grinder",
	"helper",
	"khalasi",
	"electrician",
	"foreman",
];

frappe.ui.form.on("DPR Task Completed", {
	fitter: update_dpr_task_row,
	welder: update_dpr_task_row,
	gas_cutter: update_dpr_task_row,
	rigger: update_dpr_task_row,
	grinder: update_dpr_task_row,
	helper: update_dpr_task_row,
	khalasi: update_dpr_task_row,
	electrician: update_dpr_task_row,
	foreman: update_dpr_task_row,
	target_quantity: update_dpr_task_row,
	completed_quantity: update_dpr_task_row,
});

function update_dpr_task_row(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const total_workers = dpr_worker_fields.reduce(
		(total, fieldname) => total + cint(row[fieldname] || 0),
		0
	);
	frappe.model.set_value(cdt, cdn, "total_workers", total_workers);
	frappe.model.set_value(
		cdt,
		cdn,
		"balance_quantity",
		flt(row.target_quantity || 0) - flt(row.completed_quantity || 0)
	);
}
