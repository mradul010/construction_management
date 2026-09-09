from construction_management.portal_utils import setup_client_portal_context


no_cache = 1


def get_context(context):
	setup_client_portal_context(context, "gallery")
