app_name = "construction_management"
app_title = "Construction Management"
app_icon = "octicon octicon-tools"
app_color = "blue"
app_publisher = "Vigisolvo Private Limited"
app_description = "Construction Management app build by vigisolvo private limited"
app_email = "mradulmishra010@gmail.com"
app_license = "mit"

fixtures = [{"dt": "Custom Field", "filters": [["module", "=", "Construction Management"]]}]

add_to_apps_screen = [
    {
        "name": "construction_management",
        "logo": "/assets/construction_management/techsolvo_logo.jpeg",
        "title": "Construction Management",
        "route": "/app/construction-management",
        
    }
]

portal_menu_items = [
    {
        "title": "Construction Portal",
        "route": "/construction-portal",
        "role": "Customer",
    },
]

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "construction_management",
# 		"logo": "/assets/construction_management/logo.png",
# 		"title": "Construction Management",
# 		"route": "/construction_management",
# 		"has_permission": "construction_management.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_css = "/assets/construction_management/css/report.css"
app_include_js = "/assets/construction_management/js/report_summary.js"

doctype_js = {
    "Project": "public/js/project_dpr.js",
}

# include js, css files in header of web template
web_include_css = "/assets/construction_management/css/portal.css"
web_include_js = "/assets/construction_management/js/portal.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "construction_management/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "construction_management/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "construction_management.utils.jinja_methods",
# 	"filters": "construction_management.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "construction_management.install.before_install"
after_install = "construction_management.construction_management.setup.after_install"
after_migrate = "construction_management.construction_management.setup.after_migrate"
on_session_creation = "construction_management.portal_utils.sync_customer_portal_user"

# Uninstallation
# ------------

# before_uninstall = "construction_management.uninstall.before_uninstall"
# after_uninstall = "construction_management.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "construction_management.utils.before_app_install"
# after_app_install = "construction_management.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "construction_management.utils.before_app_uninstall"
# after_app_uninstall = "construction_management.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "construction_management.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

permission_query_conditions = {
    "Daily Progress Report": "construction_management.construction_management.doctype.daily_progress_report.daily_progress_report.get_permission_query_conditions",
}

has_permission = {
    "Daily Progress Report": "construction_management.construction_management.doctype.daily_progress_report.daily_progress_report.has_permission",
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Sales Invoice": {
		"validate": [
			"construction_management.construction_management.doctype.retention_record.retention_record.validate_sales_invoice_references",
			"construction_management.construction_management.advance_management.validate_sales_invoice_advance_consistency",
		],
		"on_submit": [
			"construction_management.construction_management.doctype.retention_record.retention_record.on_sales_invoice_submit",
			"construction_management.construction_management.advance_management.on_sales_invoice_advance_change",
		],
		"on_cancel": [
			"construction_management.construction_management.doctype.retention_record.retention_record.on_sales_invoice_cancel",
			"construction_management.construction_management.advance_management.on_sales_invoice_advance_change",
		],
		"on_update_after_submit": [
			"construction_management.construction_management.doctype.retention_record.retention_record.on_sales_invoice_update_after_submit",
			"construction_management.construction_management.advance_management.on_sales_invoice_advance_change",
		],
	},
	"Payment Entry": {
		"on_submit": [
			"construction_management.construction_management.doctype.retention_record.retention_record.on_payment_entry_submit",
			"construction_management.construction_management.advance_management.on_payment_entry_advance_change",
		],
		"on_cancel": [
			"construction_management.construction_management.doctype.retention_record.retention_record.on_payment_entry_cancel",
			"construction_management.construction_management.advance_management.on_payment_entry_advance_change",
		],
		"on_update_after_submit": [
			"construction_management.construction_management.doctype.retention_record.retention_record.on_payment_entry_update_after_submit",
			"construction_management.construction_management.advance_management.on_payment_entry_advance_change",
		],
	},
	"Sales Order": {
		"on_submit": "construction_management.construction_management.advance_management.on_sales_order_advance_context_change",
		"on_cancel": "construction_management.construction_management.advance_management.on_sales_order_advance_context_change",
		"on_update_after_submit": "construction_management.construction_management.advance_management.on_sales_order_advance_context_change",
	},
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"construction_management.tasks.all"
# 	],
# 	"daily": [
# 		"construction_management.tasks.daily"
# 	],
# 	"hourly": [
# 		"construction_management.tasks.hourly"
# 	],
# 	"weekly": [
# 		"construction_management.tasks.weekly"
# 	],
# 	"monthly": [
# 		"construction_management.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "construction_management.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "construction_management.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "construction_management.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
override_doctype_dashboards = {
	"Project": "construction_management.construction_management.integrations.project_dashboard.get_data",
	"Sales Invoice": "construction_management.construction_management.integrations.sales_invoice_dashboard.get_data",
	"Sales Order": "construction_management.construction_management.integrations.sales_order_dashboard.get_data",
}

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["construction_management.utils.before_request"]
# after_request = ["construction_management.utils.after_request"]

# Job Events
# ----------
# before_job = ["construction_management.utils.before_job"]
# after_job = ["construction_management.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"construction_management.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
