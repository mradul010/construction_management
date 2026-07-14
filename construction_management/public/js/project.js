function cmParseDate(value) {
	return value ? frappe.datetime.str_to_obj(value) : null;
}

function cmDateAfter(first, second) {
	first = cmParseDate(first);
	second = cmParseDate(second);
	return first && second && first > second;
}

function cmDateBefore(first, second) {
	first = cmParseDate(first);
	second = cmParseDate(second);
	return first && second && first < second;
}

function cmShowDateError(message, fieldname) {
	frappe.msgprint({
		title: __("Invalid Date"),
		indicator: "red",
		message,
	});
	if (cur_frm && fieldname) {
		cur_frm.scroll_to_field(fieldname);
	}
}

frappe.ui.form.on("Project", {
	validate(frm) {
		if (cmDateAfter(frm.doc.expected_start_date, frm.doc.expected_end_date)) {
			cmShowDateError(__("Project Start Date cannot be after Expected End Date."), "expected_start_date");
			frappe.validated = false;
			return;
		}
		if (cmDateBefore(frm.doc.actual_start_date, frm.doc.expected_start_date)) {
			cmShowDateError(__("Actual Start Date cannot be before Project Start Date."), "actual_start_date");
			frappe.validated = false;
			return;
		}
		if (cmDateAfter(frm.doc.actual_start_date, frm.doc.actual_end_date)) {
			cmShowDateError(__("Actual End Date cannot be before Actual Start Date."), "actual_end_date");
			frappe.validated = false;
			return;
		}
		if (cmDateBefore(frm.doc.actual_end_date, frm.doc.expected_start_date)) {
			cmShowDateError(__("Actual End Date cannot be before Project Start Date."), "actual_end_date");
			frappe.validated = false;
		}
	},
});
