import frappe
import os


def after_install():
	create_boq_client_script()


def after_migrate():
	create_boq_client_script()


def create_boq_client_script():
	script_path = os.path.join(
		os.path.dirname(__file__),
		"client_script",
		"boq_client_script.js"
	)
	with open(script_path, "r") as f:
		script_content = f.read()

	if frappe.db.exists("Client Script", "BOQ-client-script"):
		doc = frappe.get_doc("Client Script", "BOQ-client-script")
		doc.script = script_content
		doc.enabled = 1
		doc.save()
	else:
		doc = frappe.get_doc({
			"doctype": "Client Script",
			"name": "BOQ-client-script",
			"dt": "BOQ",
			"script": script_content,
			"enabled": 1,
			"view": "Form"
		})
		doc.insert()
	frappe.db.commit()
	print("BOQ client script created/updated successfully")
