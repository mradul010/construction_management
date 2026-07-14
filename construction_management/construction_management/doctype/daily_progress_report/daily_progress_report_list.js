frappe.listview_settings["Daily Progress Report"] = {
	add_fields: ["status", "docstatus", "publish_to_portal"],
	get_indicator(doc) {
		if (doc.docstatus === 2 || doc.status === "Cancelled") {
			return [__("Cancelled"), "red", "docstatus,=,2"];
		}
		if (doc.docstatus === 1 || ["Submitted", "Published"].includes(doc.status)) {
			return [__(doc.status || "Submitted"), "green", "docstatus,=,1"];
		}
		return [__("Draft"), "gray", "docstatus,=,0"];
	},
};
