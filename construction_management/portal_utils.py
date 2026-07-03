import frappe
from frappe import _


def require_portal_customer():
	if frappe.session.user == "Guest":
		frappe.throw(_("Please login."), frappe.PermissionError)

	return get_customer_for_portal_user()


def get_customer_for_portal_user(user=None):
	user = user or frappe.session.user
	user_ids = get_portal_user_ids(user)

	for user_id in user_ids:
		customer = get_customer_from_contact_email(user_id)
		if customer:
			return customer

	for user_id in user_ids:
		customer = get_customer_from_contact(user_id)
		if customer:
			return customer

	for user_id in user_ids:
		customer = get_customer_from_portal_user(user_id)
		if customer:
			return customer

	customer = get_default_customer_from_erpnext(user)
	if customer:
		return customer

	frappe.throw(_("No Customer is linked with this portal user."), frappe.PermissionError)


def get_portal_user_ids(user):
	if user == "Guest":
		return [user]

	values = [user]
	user_doc = frappe.db.get_value("User", user, ["name", "email", "username"], as_dict=True)

	if not user_doc:
		user_doc = frappe.db.get_value(
			"User",
			{"username": user},
			["name", "email", "username"],
			as_dict=True,
		)

	if user_doc:
		values.extend([user_doc.name, user_doc.email, user_doc.username])

	return list(dict.fromkeys(value for value in values if value))


def get_customer_from_user():
	return get_customer_for_portal_user()


def get_customer_from_contact_email(email):
	contacts = frappe.get_all(
		"Contact Email",
		filters={"email_id": email},
		pluck="parent",
	)

	return get_customer_from_contacts(contacts)


def get_customer_from_contact(email):
	contacts = frappe.get_all(
		"Contact",
		filters={"email_id": email},
		pluck="name",
	)

	return get_customer_from_contacts(contacts)


def get_customer_from_contacts(contacts):
	for contact in contacts or []:
		customer = frappe.db.get_value(
			"Dynamic Link",
			{
				"parenttype": "Contact",
				"parent": contact,
				"link_doctype": "Customer",
			},
			"link_name",
		)
		if customer:
			return customer

		customer = get_matching_customer_for_contact(contact)
		if customer:
			return customer


def get_matching_customer_for_contact(contact):
	if frappe.db.exists("Customer", contact):
		return contact

	contact_name = frappe.db.get_value("Contact", contact, "full_name")
	if contact_name:
		return frappe.db.get_value("Customer", {"customer_name": contact_name}, "name")


def get_customer_from_portal_user(user):
	return frappe.db.get_value(
		"Portal User",
		{
			"parenttype": "Customer",
			"user": user,
		},
		"parent",
	)


def get_default_customer_from_erpnext(user):
	try:
		from erpnext.utilities import get_default_customer
	except Exception:
		return None

	try:
		return get_default_customer(user)
	except Exception:
		return None


def get_boq_customer_field():
	meta = frappe.get_meta("BOQ")
	if meta.has_field("client"):
		return "client"
	if meta.has_field("customer"):
		return "customer"

	frappe.throw(_("BOQ does not have a Customer field."))


def validate_boq_customer(boq_name, customer):
	if not boq_name:
		frappe.throw(_("Document not specified."))

	boq_customer = frappe.db.get_value("BOQ", boq_name, get_boq_customer_field())
	if not boq_customer or boq_customer != customer:
		frappe.throw(_("Not permitted."), frappe.PermissionError)


def validate_ra_bill_customer(ra_bill_name, customer):
	if not ra_bill_name:
		frappe.throw(_("Document not specified."))

	ra_bill_customer = frappe.db.get_value("RA Bill", ra_bill_name, "customer")
	if not ra_bill_customer or ra_bill_customer != customer:
		frappe.throw(_("Not permitted."), frappe.PermissionError)


def log_portal_access(customer):
	try:
		frappe.logger("construction_management.portal").debug(
			{
				"portal_user": frappe.session.user,
				"detected_customer": customer,
				"route": getattr(frappe.local, "request", None).path
				if getattr(frappe.local, "request", None)
				else "",
			}
		)
	except Exception:
		pass
