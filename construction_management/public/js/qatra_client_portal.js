(function () {
	function ready(fn) {
		if (window.frappe && frappe.ready) {
			frappe.ready(fn);
		} else if (document.readyState !== "loading") {
			fn();
		} else {
			document.addEventListener("DOMContentLoaded", fn);
		}
	}

	ready(function () {
		const body = document.body;
		const openButton = document.querySelector("[data-qatra-portal-open]");
		const collapseButton = document.querySelector("[data-qatra-portal-collapse]");
		const collapseIcon = document.querySelector("[data-qatra-collapse-icon]");
		const closeTargets = document.querySelectorAll("[data-qatra-portal-close]");
		const navLinks = document.querySelectorAll(".qatra-portal-nav-link");
		const signOutButtons = document.querySelectorAll("[data-qatra-portal-signout]");
		const sidebarStorageKey = "qatraClientPortalSidebarCollapsed";

		function setNavigation(open) {
			body.classList.toggle("qatra-portal-nav-open", open);
			if (openButton) {
				openButton.setAttribute("aria-expanded", open ? "true" : "false");
				openButton.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
			}
		}

		if (openButton) {
			openButton.addEventListener("click", function () {
				setNavigation(!body.classList.contains("qatra-portal-nav-open"));
			});
		}

		closeTargets.forEach(function (target) {
			target.addEventListener("click", function () {
				setNavigation(false);
			});
		});

		navLinks.forEach(function (link) {
			link.addEventListener("click", function () {
				setNavigation(false);
			});
		});

		signOutButtons.forEach(function (button) {
			button.addEventListener("click", function () {
				window.location.href = "/client-portal/logout";
			});
		});

		function setSidebarCollapsed(collapsed, persist) {
			body.classList.toggle("qatra-portal-sidebar-collapsed", collapsed);
			if (collapseButton) {
				collapseButton.setAttribute("aria-expanded", collapsed ? "false" : "true");
				collapseButton.setAttribute(
					"aria-label",
					collapsed ? "Expand navigation" : "Collapse navigation"
				);
			}
			if (collapseIcon) {
				collapseIcon.classList.toggle("qatra-portal-collapse-icon--collapsed", collapsed);
			}
			if (persist && window.localStorage) {
				window.localStorage.setItem(sidebarStorageKey, collapsed ? "1" : "0");
			}
		}

		if (window.localStorage && window.localStorage.getItem(sidebarStorageKey) === "1") {
			setSidebarCollapsed(true, false);
		}

		if (collapseButton) {
			collapseButton.addEventListener("click", function () {
				setSidebarCollapsed(!body.classList.contains("qatra-portal-sidebar-collapsed"), true);
			});
		}

		function getCellText(row) {
			return Array.from(row.querySelectorAll("span")).map(function (cell) {
				return cell.textContent.trim();
			});
		}

		function escapeCsvCell(value) {
			const normalized = String(value || "").replace(/\s+/g, " ").trim();
			if (/[",\n]/.test(normalized)) {
				return '"' + normalized.replace(/"/g, '""') + '"';
			}
			return normalized;
		}

		function getDownloadName(table) {
			const title = table.getAttribute("data-qatra-report-title") || "report-table";
			return (
				title
					.toLowerCase()
					.replace(/[^a-z0-9]+/g, "-")
					.replace(/^-|-$/g, "") || "report-table"
			) + ".csv";
		}

		function downloadCsv(table, rows) {
			const header = table.querySelector("[data-qatra-report-header]");
			const headings = header ? getCellText(header) : [];
			const csvRows = [headings].concat(rows.map(getCellText));
			const blob = new Blob(
				[csvRows.map(function (row) {
					return row.map(escapeCsvCell).join(",");
				}).join("\n")],
				{ type: "text/csv;charset=utf-8;" }
			);
			const link = document.createElement("a");
			link.href = URL.createObjectURL(blob);
			link.download = getDownloadName(table);
			link.click();
			URL.revokeObjectURL(link.href);
		}

		document.querySelectorAll("[data-qatra-report-table]").forEach(function (table) {
			const searchInput = table.querySelector("[data-qatra-report-search]");
			const pageSizeInput = table.querySelector("[data-qatra-report-page-size]");
			const downloadButton = table.querySelector("[data-qatra-report-download]");
			const previousButton = table.querySelector("[data-qatra-report-prev]");
			const nextButton = table.querySelector("[data-qatra-report-next]");
			const pageLabel = table.querySelector("[data-qatra-report-page]");
			const countLabel = table.querySelector("[data-qatra-report-count]");
			const rows = Array.from(table.querySelectorAll("[data-qatra-report-row]"));
			let page = 1;

			function getFilteredRows() {
				const query = searchInput ? searchInput.value.trim().toLowerCase() : "";
				if (!query) {
					return rows;
				}
				return rows.filter(function (row) {
					return row.textContent.toLowerCase().indexOf(query) !== -1;
				});
			}

			function renderTable() {
				const pageSize = pageSizeInput ? parseInt(pageSizeInput.value, 10) || 10 : 10;
				const filteredRows = getFilteredRows();
				const pageCount = Math.max(Math.ceil(filteredRows.length / pageSize), 1);
				page = Math.min(Math.max(page, 1), pageCount);
				const start = (page - 1) * pageSize;
				const end = start + pageSize;
				const visibleRows = new Set(filteredRows.slice(start, end));

				rows.forEach(function (row) {
					row.hidden = !visibleRows.has(row);
				});

				if (countLabel) {
					if (filteredRows.length) {
						countLabel.textContent =
							"Showing " +
							(start + 1) +
							"-" +
							Math.min(end, filteredRows.length) +
							" of " +
							filteredRows.length;
					} else {
						countLabel.textContent = "No rows found";
					}
				}
				if (pageLabel) {
					pageLabel.textContent = "Page " + page + " of " + pageCount;
				}
				if (previousButton) {
					previousButton.disabled = page <= 1;
				}
				if (nextButton) {
					nextButton.disabled = page >= pageCount;
				}
			}

			if (searchInput) {
				searchInput.addEventListener("input", function () {
					page = 1;
					renderTable();
				});
			}
			if (pageSizeInput) {
				pageSizeInput.addEventListener("change", function () {
					page = 1;
					renderTable();
				});
			}
			if (previousButton) {
				previousButton.addEventListener("click", function () {
					page -= 1;
					renderTable();
				});
			}
			if (nextButton) {
				nextButton.addEventListener("click", function () {
					page += 1;
					renderTable();
				});
			}
			if (downloadButton) {
				downloadButton.addEventListener("click", function () {
					downloadCsv(table, getFilteredRows());
				});
			}

			renderTable();
		});

		const projectSearch = document.querySelector("[data-qatra-project-search]");
		const projectStatus = document.querySelector("[data-qatra-project-status]");
		const projectCards = Array.from(document.querySelectorAll("[data-qatra-project-card]"));
		const projectEmptyState = document.querySelector("[data-qatra-project-empty]");

		function filterProjects() {
			if (!projectCards.length) {
				return;
			}

			const searchValue = (projectSearch && projectSearch.value ? projectSearch.value : "").trim().toLowerCase();
			const statusValue = projectStatus && projectStatus.value ? projectStatus.value : "";
			let visibleCount = 0;

			projectCards.forEach(function (card) {
				const haystack = (card.getAttribute("data-search") || "").toLowerCase();
				const cardStatus = card.getAttribute("data-status") || "";
				const matchesSearch = !searchValue || haystack.indexOf(searchValue) !== -1;
				const matchesStatus = !statusValue || cardStatus === statusValue;
				const visible = matchesSearch && matchesStatus;

				card.hidden = !visible;
				if (visible) {
					visibleCount += 1;
				}
			});

			if (projectEmptyState) {
				projectEmptyState.hidden = visibleCount > 0;
			}
		}

		if (projectSearch) {
			projectSearch.addEventListener("input", filterProjects);
		}

		if (projectStatus) {
			projectStatus.addEventListener("change", filterProjects);
		}

		document.addEventListener("keydown", function (event) {
			if (event.key === "Escape") {
				setNavigation(false);
			}
		});
	});
})();
