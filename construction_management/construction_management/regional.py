import frappe
from frappe import _


CONSTRUCTION_COMPANY_SETTINGS_DOCTYPE = "Construction Company Settings"
INDIA_COMPLIANCE_APP = "india_compliance"
INDIA_COUNTRY = "India"
UAE_COUNTRY = "United Arab Emirates"
DEFAULT_CONSTRUCTION_SERVICE_ITEM = "RA Bill Services"
DEFAULT_CONSTRUCTION_ITEM_GROUP = "Services"
DEFAULT_CONSTRUCTION_UOM = "Nos"


def get_company_country(company):
	if not company:
		return None
	return frappe.get_cached_value("Company", company, "country")


def is_india_company(company):
	return get_company_country(company) == INDIA_COUNTRY


def is_uae_company(company):
	return get_company_country(company) == UAE_COUNTRY


def is_india_compliance_installed():
	try:
		return INDIA_COMPLIANCE_APP in frappe.get_installed_apps()
	except Exception:
		return False


def get_construction_company_settings(company):
	if not company:
		frappe.throw(_("Company is required to fetch Construction Company Settings."))

	country = get_company_country(company)
	if not _settings_doctype_ready():
		return frappe._dict({"company": company, "country": country})

	name = (
		frappe.db.exists(CONSTRUCTION_COMPANY_SETTINGS_DOCTYPE, {"company": company})
		or frappe.db.exists(CONSTRUCTION_COMPANY_SETTINGS_DOCTYPE, company)
	)
	if not name:
		return frappe._dict({"company": company, "country": country})

	return frappe.get_cached_doc(CONSTRUCTION_COMPANY_SETTINGS_DOCTYPE, name)


def get_construction_setting(company, fieldname, default=None):
	settings = get_construction_company_settings(company)
	return settings.get(fieldname) or default


def get_default_construction_service_item(company=None):
	return (
		get_construction_setting(company, "default_construction_service_item")
		if company
		else None
	) or DEFAULT_CONSTRUCTION_SERVICE_ITEM


def get_default_construction_item_group(company=None):
	return (
		get_construction_setting(company, "default_construction_item_group")
		if company
		else None
	) or DEFAULT_CONSTRUCTION_ITEM_GROUP


def get_default_construction_uom(company=None):
	return (
		get_construction_setting(company, "default_uom")
		if company
		else None
	) or DEFAULT_CONSTRUCTION_UOM


def get_default_service_hsn_sac(company=None):
	if not company:
		return None
	return get_construction_setting(company, "default_service_hsn_sac")


def item_requires_hsn_sac(company=None):
	if not is_india_compliance_installed():
		return False

	try:
		item_meta = frappe.get_meta("Item")
	except Exception:
		return False

	if not item_meta.has_field("gst_hsn_code"):
		return False

	return not company or is_india_company(company) or has_india_company()


def apply_regional_item_defaults(item, company=None):
	if not item or not item.meta.has_field("gst_hsn_code"):
		return

	hsn_sac = get_default_service_hsn_sac(company)
	if hsn_sac:
		item.gst_hsn_code = hsn_sac


def has_india_company():
	try:
		return bool(frappe.db.exists("Company", {"country": INDIA_COUNTRY}))
	except Exception:
		return False


def validate_construction_service_item_can_be_created(company=None):
	if item_requires_hsn_sac(company) and not get_default_service_hsn_sac(company):
		frappe.throw(
			_(
				"Default Service HSN/SAC is required for Company {0} before creating "
				"construction service Items. Configure it in Construction Company Settings."
			).format(frappe.bold(company or "")),
			title=_("Construction Company Settings Required"),
		)


def _settings_doctype_ready():
	try:
		return frappe.db.exists("DocType", CONSTRUCTION_COMPANY_SETTINGS_DOCTYPE) and frappe.db.table_exists(
			CONSTRUCTION_COMPANY_SETTINGS_DOCTYPE
		)
	except Exception:
		return False
