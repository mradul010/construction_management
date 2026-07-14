frappe.ready(function () {
	const pathname = window.location.pathname;

	if (pathname === "/portal") {
		setup_client_portal_home();
	}

	if (is_construction_portal_path(pathname)) {
		setup_construction_sidebar_toggle();
	}
});

function setup_client_portal_home() {
	document.body.classList.add("client-portal-home");
	document.querySelectorAll(
		'.web-sidebar a[href="/construction-projects"], .web-sidebar a[href="/dprs"], .web-sidebar a[href="/boq"], .web-sidebar a[href="/ra-bill"], .web-sidebar a[href="/work-progress"]'
	).forEach((link) => {
		const item = link.closest(".sidebar-item");
		if (item) {
			item.remove();
		}
	});
	normalize_portal_home_lists();

	if (document.getElementById("client-portal-home-style")) {
		return;
	}

	const style = document.createElement("style");
	style.id = "client-portal-home-style";
	style.textContent = `
		body.client-portal-home .container > .row {
			display: block;
		}

		body.client-portal-home .sidebar-column {
			display: block;
			flex: 0 0 100%;
			max-width: 100%;
			width: 100%;
		}

		body.client-portal-home .main-column {
			display: none;
		}

		body.client-portal-home .web-sidebar {
			position: static;
		}

		body.client-portal-home .web-sidebar .sidebar-items > ul {
			display: grid;
			gap: 18px;
			grid-template-columns: repeat(4, minmax(0, 1fr));
			margin: 0;
		}

		body.client-portal-home .web-sidebar .sidebar-group,
		body.client-portal-home .web-sidebar .sidebar-item {
			list-style: none;
			margin: 0;
		}

		body.client-portal-home .web-sidebar .title {
			border-bottom: 1px solid var(--border-color, #e5e7eb);
			font-size: 1.5rem;
			font-weight: 650;
			margin-bottom: 1.25rem;
			padding-bottom: 0.75rem;
		}

		body.client-portal-home .web-sidebar .sidebar-item a {
			align-items: center;
			background: var(--card-bg, #fff);
			border: 1px solid var(--border-color, #e5e7eb);
			border-radius: 14px;
			box-shadow: 0 8px 22px rgba(31, 39, 46, 0.06);
			color: var(--text-color, #1f272e);
			display: flex;
			font-size: 18px;
			font-weight: 600;
			justify-content: space-between;
			line-height: 1.2;
			min-height: 86px;
			min-width: 0;
			padding: 1.1rem 1.15rem 1.1rem 1.25rem;
			text-decoration: none;
			transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
			width: 100%;
		}

		body.client-portal-home .web-sidebar .sidebar-item a::after {
			color: var(--text-muted, #6c757d);
			content: "\\2197";
			font-size: 15px;
			font-weight: 500;
			line-height: 1;
			margin-left: 1rem;
		}

		body.client-portal-home .web-sidebar .sidebar-item a:hover,
		body.client-portal-home .web-sidebar .sidebar-item a.active {
			background: var(--subtle-fg, #f8f9fa);
			border-color: var(--primary, #2490ef);
			box-shadow: 0 10px 28px rgba(36, 144, 239, 0.12);
			color: var(--primary, #2490ef);
			transform: translateY(-1px);
		}

		body.client-portal-home .web-sidebar .sidebar-item a:hover::after,
		body.client-portal-home .web-sidebar .sidebar-item a.active::after {
			color: var(--primary, #2490ef);
		}

		@media (max-width: 575.98px) {
			body.client-portal-home .web-sidebar .sidebar-items > ul {
				grid-template-columns: 1fr;
			}

			body.client-portal-home .web-sidebar .sidebar-item,
			body.client-portal-home .web-sidebar .sidebar-item a {
				width: 100%;
			}
		}

		@media (min-width: 576px) and (max-width: 991.98px) {
			body.client-portal-home .web-sidebar .sidebar-items > ul {
				grid-template-columns: repeat(2, minmax(0, 1fr));
			}
		}
	`;
	document.head.appendChild(style);
}

function normalize_portal_home_lists() {
	const lists = Array.from(document.querySelectorAll(".web-sidebar .sidebar-items > ul"));
	if (lists.length < 2) {
		return;
	}

	const primary_list = lists[0];
	lists.slice(1).forEach((list) => {
		Array.from(list.children).forEach((item) => primary_list.appendChild(item));
		list.remove();
	});
}

function is_construction_portal_path(pathname) {
	return [
		"/construction-portal",
		"/construction-projects",
		"/construction-project-detail",
		"/boq",
		"/boq-detail",
		"/ra-bill",
		"/ra-bill-detail",
		"/work-progress",
		"/work-progress-detail",
		"/dprs",
		"/dpr-detail",
	].includes(pathname);
}

function setup_construction_sidebar_toggle() {
	document.body.classList.add("construction-portal-page");

	const saved_state = window.localStorage.getItem("construction_sidebar_collapsed");
	if (saved_state === "1") {
		document.body.classList.add("construction-sidebar-collapsed");
	}

	const wrapper = document.querySelector(".page-content-wrapper");
	if (!wrapper || document.querySelector(".construction-sidebar-toggle")) {
		return;
	}

	const button = document.createElement("button");
	button.type = "button";
	button.className = "construction-sidebar-toggle";
	button.title = "Toggle menu";

	const update_label = () => {
		const collapsed = document.body.classList.contains("construction-sidebar-collapsed");
		button.textContent = collapsed ? "\u203a" : "\u2039";
		button.setAttribute("aria-label", collapsed ? "Show menu" : "Hide menu");
		button.setAttribute("aria-expanded", collapsed ? "false" : "true");
	};

	button.addEventListener("click", () => {
		document.body.classList.toggle("construction-sidebar-collapsed");
		window.localStorage.setItem(
			"construction_sidebar_collapsed",
			document.body.classList.contains("construction-sidebar-collapsed") ? "1" : "0"
		);
		update_label();
	});

	update_label();
	wrapper.prepend(button);
}
