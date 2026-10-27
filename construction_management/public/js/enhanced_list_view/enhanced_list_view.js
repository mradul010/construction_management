(() => {
	const namespace = "enhanced_list_view";
	const states = new WeakMap();
	const key_for = (column) =>
		column?.df?.fieldname || { Status: "status_field", Tag: "_user_tags" }[column?.type];
	const minimum = (column) => (column?.type === "Subject" ? 160 : 96);
	const width_for = (value, column) =>
		Math.max(minimum(column), Math.min(1200, Number(value) || minimum(column)));
	const enabled = (view) => view.view_name === "List" && !frappe.is_mobile();

	function state_for(view) {
		if (!states.has(view)) {
			const layout = frappe.get_user_settings(view.doctype, "List")?.[namespace] || {};
			const widths = {};
			(layout.columns || []).forEach((column) => {
				if (column.fieldname && column.width) widths[column.fieldname] = column.width;
			});
			// Width-only saves take precedence over older custom-column layouts.
			Object.assign(widths, layout.widths || {});
			states.set(view, { widths, save: Promise.resolve() });
		}
		return states.get(view);
	}

	function apply(view, state) {
		const root = view.$result[0];
		let left_width = 0;
		const header = root.querySelector(".list-row-head .list-header-subject");
		if (!header || !header.getClientRects().length) return;
		Array.from(header.children)
			.filter((cell) => cell.classList.contains("list-row-col"))
			.forEach((cell, index) => {
				if (!cell.getClientRects().length) return;
				const column = view.columns[index];
				const key = key_for(column);
				const width = key
					? width_for(state.widths[key], column)
					: cell.getBoundingClientRect().width;
				if (key)
					root.querySelectorAll(`[data-cmelv-index="${index}"]`).forEach((target) => {
						target.style.width = `${width}px`;
						target.style.minWidth = `${minimum(column)}px`;
						target.style.flex = `0 0 ${width}px`;
					});
				const style = getComputedStyle(cell);
				left_width +=
					width +
					(parseFloat(style.marginLeft) || 0) +
					(parseFloat(style.marginRight) || 0);
			});
		const header_style = getComputedStyle(header);
		left_width +=
			(parseFloat(header_style.paddingLeft) || 0) +
			(parseFloat(header_style.paddingRight) || 0);
		let right_width = 0;
		root.querySelectorAll(".list-row .level-right").forEach((cell) => {
			right_width = Math.max(right_width, cell.getBoundingClientRect().width);
		});
		// Header metadata can flex into spare space. Measure its contents instead
		// of feeding that expanded width back into the next resize calculation.
		const metadata = root.querySelector(".list-row-head > .level-right");
		if (metadata) {
			const style = getComputedStyle(metadata);
			const content_width = Array.from(metadata.children).reduce((total, child) => {
				const child_style = getComputedStyle(child);
				return (
					total +
					child.getBoundingClientRect().width +
					(parseFloat(child_style.marginLeft) || 0) +
					(parseFloat(child_style.marginRight) || 0)
				);
			}, 0);
			right_width = Math.max(
				right_width,
				content_width +
					(parseFloat(style.paddingLeft) || 0) +
					(parseFloat(style.paddingRight) || 0)
			);
		}
		const row_style = getComputedStyle(header.closest(".list-row-head"));
		const padding =
			(parseFloat(row_style.paddingLeft) || 0) + (parseFloat(row_style.paddingRight) || 0);
		root.style.setProperty("--cmelv-left-width", `${left_width}px`);
		root.style.setProperty("--cmelv-row-width", `${left_width + right_width + padding}px`);
	}

	function save(view, state) {
		const widths = { ...state.widths };
		state.save = state.save
			.catch(() => {})
			.then(() => {
				const layout = {
					...(frappe.get_user_settings(view.doctype, "List")?.[namespace] || {}),
					widths,
				};
				return view.save_view_user_settings({ [namespace]: layout });
			})
			.catch(() =>
				frappe.msgprint(__("Column widths could not be saved. Please try resizing again."))
			);
	}

	function bind(view, state, root) {
		if (state.root === root) return;
		state.cancel?.();
		state.binding?.abort();
		state.root = root;
		state.binding = new AbortController();
		const options = { capture: true, signal: state.binding.signal };
		for (const type of ["click", "dblclick", "dragstart"])
			root.addEventListener(
				type,
				(event) => {
					if (
						!event.target.closest(".cmelv-resize-line") &&
						!(
							type === "click" &&
							state.suppress_click &&
							event.target.closest(".list-row-head")
						)
					)
						return;
					event.preventDefault();
					event.stopImmediatePropagation();
					state.suppress_click = false;
				},
				options
			);
		root.addEventListener(
			"pointerdown",
			(event) => {
				const handle = event.target.closest(".cmelv-resize-line");
				if (!handle || event.button !== 0 || !enabled(view)) return;
				event.preventDefault();
				event.stopImmediatePropagation();
				state.cancel?.();
				const index = Number(handle.parentElement.dataset.cmelvIndex);
				const key = key_for(view.columns[index]);
				const original = state.widths[key];
				const start = handle.parentElement.getBoundingClientRect().width;
				const x = event.clientX;
				const pointer = event.pointerId;
				const controller = new AbortController();
				const drag_options = { capture: true, signal: controller.signal };
				root.classList.add("cmelv-resizing");
				const finish = (cancelled) => {
					controller.abort();
					state.cancel = null;
					root.classList.remove("cmelv-resizing");
					state.suppress_click = true;
					setTimeout(() => {
						state.suppress_click = false;
					}, 0);
					if (cancelled) {
						state.widths[key] = original;
						apply(view, state);
					} else if (state.widths[key] !== original) save(view, state);
				};
				state.cancel = () => finish(true);
				document.addEventListener(
					"pointermove",
					(move) => {
						if (move.pointerId !== pointer) return;
						move.preventDefault();
						if (!root.isConnected || !handle.isConnected) {
							finish(true);
							return;
						}
						state.widths[key] = width_for(
							start + move.clientX - x,
							view.columns[index]
						);
						apply(view, state);
					},
					drag_options
				);
				document.addEventListener(
					"pointerup",
					(up) => {
						if (up.pointerId === pointer) {
							up.preventDefault();
							up.stopImmediatePropagation();
							finish(false);
						}
					},
					drag_options
				);
				document.addEventListener(
					"pointercancel",
					(cancel) => {
						if (cancel.pointerId === pointer) finish(true);
					},
					drag_options
				);
				window.addEventListener("blur", () => finish(true), { signal: controller.signal });
			},
			options
		);
	}

	function enhance(view) {
		if (!view.$result?.[0]) return;
		const root = view.$result[0];
		if (!enabled(view)) {
			const state = states.get(view);
			state?.cancel?.();
			state?.binding?.abort();
			if (state) state.root = null;
			root.classList.remove("cmelv-resizable");
			root.style.removeProperty("--cmelv-left-width");
			root.style.removeProperty("--cmelv-row-width");
			root.querySelectorAll(".cmelv-resize-line").forEach((handle) => handle.remove());
			root.querySelectorAll("[data-cmelv-index]").forEach((cell) => {
				for (const property of ["width", "min-width", "flex"])
					cell.style.removeProperty(property);
				delete cell.dataset.cmelvIndex;
			});
			return;
		}
		const state = state_for(view);
		root.classList.add("cmelv-resizable");
		const headers = root.querySelectorAll(
			".list-row-head .list-header-subject > .list-row-col"
		);
		headers.forEach((cell, index) => {
			const column = view.columns[index];
			const key = key_for(column);
			if (!key) return;
			cell.dataset.cmelvIndex = index;
			if (!state.widths[key] && cell.getClientRects().length)
				state.widths[key] = width_for(cell.getBoundingClientRect().width, column);
			if (cell.querySelector(":scope > .cmelv-resize-line")) return;
			const handle = document.createElement("span");
			handle.className = "cmelv-resize-line";
			handle.setAttribute("aria-hidden", "true");
			handle.title = __("Resize column");
			cell.appendChild(handle);
		});
		root.querySelectorAll(".list-row .level-left").forEach((row) => {
			Array.from(row.children)
				.filter((cell) => cell.classList.contains("list-row-col"))
				.forEach((cell, index) => {
					if (key_for(view.columns[index])) cell.dataset.cmelvIndex = index;
				});
		});
		apply(view, state);
		bind(view, state, root);
	}

	function patch(attempts = 50) {
		const ListView = frappe.views?.ListView;
		if (!ListView) {
			if (attempts) setTimeout(() => patch(attempts - 1), 100);
			return;
		}
		if (ListView.__cmelv_widths_only) return;
		ListView.__cmelv_widths_only = true;
		// Native headers, columns, menus and row rendering remain authoritative.
		for (const method of ["render_header", "render_list"]) {
			const original = ListView.prototype[method];
			ListView.prototype[method] = function (...args) {
				const result = original.apply(this, args);
				requestAnimationFrame(() => enhance(this));
				return result;
			};
		}
	}
	patch();
})();
