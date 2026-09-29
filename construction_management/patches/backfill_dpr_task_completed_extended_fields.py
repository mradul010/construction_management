import frappe


def execute():
	if not frappe.db.table_exists("DPR Task Completed"):
		return

	frappe.db.sql(
		"""
		update `tabDPR Task Completed`
		set
			target_quantity = case
				when coalesce(target_quantity, 0) = 0 and coalesce(completed_quantity, 0) = 0
					then coalesce(quantity, 0)
				else coalesce(target_quantity, 0)
			end,
			completed_quantity = case
				when coalesce(target_quantity, 0) = 0 and coalesce(completed_quantity, 0) = 0
					then coalesce(quantity, 0)
				else coalesce(completed_quantity, 0)
			end,
			total_workers = (
				coalesce(fitter, 0)
				+ coalesce(welder, 0)
				+ coalesce(gas_cutter, 0)
				+ coalesce(rigger, 0)
				+ coalesce(grinder, 0)
				+ coalesce(helper, 0)
				+ coalesce(khalasi, 0)
				+ coalesce(electrician, 0)
				+ coalesce(foreman, 0)
			),
			balance_quantity = (
				case
					when coalesce(target_quantity, 0) = 0 and coalesce(completed_quantity, 0) = 0
						then coalesce(quantity, 0)
					else coalesce(target_quantity, 0)
				end
				-
				case
					when coalesce(target_quantity, 0) = 0 and coalesce(completed_quantity, 0) = 0
						then coalesce(quantity, 0)
					else coalesce(completed_quantity, 0)
				end
			),
			mark_no = coalesce(nullif(mark_no, ''), nullif(item_code, ''), nullif(item_name, ''), ''),
			item_code = coalesce(nullif(mark_no, ''), nullif(item_code, ''), nullif(item_name, ''), ''),
			item_name = coalesce(nullif(mark_no, ''), nullif(item_code, ''), nullif(item_name, ''), '')
		"""
	)
