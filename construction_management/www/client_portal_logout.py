no_cache = 1


def get_context(context):
	context.no_header = True
	context.no_breadcrumbs = True
	context.show_sidebar = False
	context.hide_login = True
	context.full_width = True
	context.title = "Signing Out"
	context.body_class = "qatra-client-portal"
