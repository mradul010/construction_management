(function () {
	const NAMESPACE = "enhanced_list_view";
	const ENABLED_DOCTYPES = ["Sales Invoice", "Purchase Invoice"];
	const MIN_WIDTH = 72;
	const MAX_WIDTH = 520;
	const DEFAULT_WIDTH = 140;

	const config = (window.construction_management_enhanced_list_view =
		window.construction_management_enhanced_list_view || {});
	config.enabled_doctypes = config.enabled_doctypes || ENABLED_DOCTYPES;

	function is_enabled(listview) {
		return Boolean(
			listview &&
				listview.view_name === "List" &&
				config.enabled_doctypes.includes(listview.doctype) &&
				!frappe.is_mobile()
		);
	}

	function clamp_width(width) {
		width = cint(width) || DEFAULT_WIDTH;
		return Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, width));
	}

	function get_layout(listview) {
		const layout = frappe.get_user_settings(listview.doctype, listview.view_name)?.[NAMESPACE] || {};
		return $.extend(true, {}, layout);
	}

	function save_layout(listview, layout) {
		if (!layout) {
			return clear_layout(listview);
		}

		const value = {};
		value[NAMESPACE] = layout;
		return listview.save_view_user_settings(value);
	}

	function clear_layout(listview) {
		const user_settings = $.extend(true, {}, frappe.get_user_settings(listview.doctype) || {});
		user_settings[listview.view_name] = user_settings[listview.view_name] || {};
		delete user_settings[listview.view_name][NAMESPACE];
		return frappe.model.user_settings.update(listview.doctype, user_settings);
	}

	function get_column_key(col) {
		if (col.type === "Status") return "status_field";
		if (col.type === "Tag") return "_user_tags";
		return col.df?.fieldname;
	}

	function get_column_label(listview, key) {
		if (key === "status_field") return __("Status");
		if (key === "_user_tags") return __("Tags");
		const df = get_docfield(listview, key);
		return __(df?.label || key, null, df?.parent || listview.doctype);
	}

	function get_docfield(listview, fieldname) {
		if (!fieldname) return null;
		return (
			frappe.meta.get_docfield(listview.doctype, fieldname) ||
			(frappe.model.std_fields || []).find((df) => df.fieldname === fieldname) ||
			null
		);
	}

	function get_subject_field(listview) {
		if (listview.meta.title_field) {
			return get_docfield(listview, listview.meta.title_field.trim());
		}
		return get_docfield(listview, "name") || { label: __("ID"), fieldname: "name" };
	}

	function get_default_columns(listview) {
		const subject = get_subject_field(listview);
		const columns = [
			{
				key: subject.fieldname,
				label: __(subject.label || "ID", null, listview.doctype),
				required: true,
			},
		];

		if (frappe.has_indicator(listview.doctype)) {
			columns.push({ key: "status_field", label: __("Status") });
		}

		(listview.meta.fields || []).forEach((df) => {
			if (
				!df.fieldname ||
				df.fieldname === subject.fieldname ||
				df.is_virtual ||
				frappe.model.no_value_type.includes(df.fieldtype) ||
				!frappe.perm.has_perm(listview.doctype, df.permlevel, "read")
			) {
				return;
			}
			columns.push({
				key: df.fieldname,
				label: __(df.label || df.fieldname, null, df.parent || listview.doctype),
			});
		});

		if (!columns.some((column) => column.key === "name")) {
			columns.push({ key: "name", label: __("ID") });
		}

		return columns.uniqBy((column) => column.key);
	}

	function get_current_visible_keys(listview) {
		return (listview.columns || []).map(get_column_key).filter(Boolean);
	}

	function build_custom_columns(listview, layout) {
		const subject = get_subject_field(listview);
		let visible = (layout.columns || [])
			.filter((column) => column.visible !== false)
			.sort((a, b) => (cint(a.order) || 0) - (cint(b.order) || 0))
			.map((column) => column.fieldname)
			.filter(Boolean);

		if (!visible.includes(subject.fieldname)) {
			visible.unshift(subject.fieldname);
		}

		return visible
			.map((fieldname) => {
				if (fieldname === subject.fieldname) {
					return { type: "Subject", df: subject };
				}
				if (fieldname === "status_field" && frappe.has_indicator(listview.doctype)) {
					return { type: "Status" };
				}
				if (fieldname === "_user_tags") {
					return { type: "Tag" };
				}

				const df = get_docfield(listview, fieldname);
				if (!df || !frappe.model.is_value_type(df.fieldtype)) return null;
				return { type: "Field", df };
			})
			.filter(Boolean)
			.uniqBy(get_column_key);
	}

	function get_widths(layout) {
		const widths = Object.assign({}, layout.widths || {});
		(layout.columns || []).forEach((column) => {
			if (column.fieldname && column.width) {
				widths[column.fieldname] = column.width;
			}
		});
		return widths;
	}

	function measure_column(listview, key) {
		const cell = listview.$result
			?.find("[data-cmelv-fieldname]")
			.filter((index, element) => element.dataset.cmelvFieldname === key)
			.get(0);
		return cell ? Math.round(cell.getBoundingClientRect().width) : DEFAULT_WIDTH;
	}

	function annotate_columns(listview) {
		const columns = listview.columns || [];
		const $headers = listview.$result.find(".list-row-head .list-header-subject > .list-row-col");
		$headers.each((index, element) => {
			const key = get_column_key(columns[index]);
			if (key) {
				element.dataset.cmelvFieldname = key;
				element.dataset.cmelvIndex = index;
			}
		});

		listview.$result.find(".list-row .level-left").each((row_index, row) => {
			$(row)
				.children(".list-row-col")
				.each((index, element) => {
					const key = get_column_key(columns[index]);
					if (key) {
						element.dataset.cmelvFieldname = key;
						element.dataset.cmelvIndex = index;
					}
				});
		});
	}

	function apply_widths(listview) {
		if (!is_enabled(listview)) return;

		const layout = get_layout(listview);
		const widths = get_widths(layout);
		let total_width = 0;

		(listview.columns || []).forEach((column, index) => {
			const key = get_column_key(column);
			if (!key) return;

			const width = widths[key] ? clamp_width(widths[key]) : null;
			if (!width) return;

			total_width += width;
			listview.$result
				.find(`[data-cmelv-index="${index}"]`)
				.css({
					width: width + "px",
					"min-width": MIN_WIDTH + "px",
					flex: `0 0 ${width}px`,
				});
		});

		if (total_width) {
			listview.$result
				.find(".list-row .level-left, .list-row-head .list-header-subject")
				.css("--cmelv-left-width", total_width + "px");
		}
	}

	function enhance_dom(listview) {
		if (!is_enabled(listview) || !listview.$result) return;

		listview.$frappe_list.addClass("cmelv-enabled");
		annotate_columns(listview);
		apply_widths(listview);
		add_resize_handles(listview);
	}

	function add_resize_handles(listview) {
		const $headers = listview.$result.find(".list-row-head [data-cmelv-fieldname]");
		$headers.each((index, element) => {
			const $cell = $(element);
			if (!$cell.find(".cmelv-resize-handle").length) {
				$cell.append(
					`<span class="cmelv-resize-handle" role="separator" title="${__(
						"Drag to resize column"
					)}" aria-label="${__("Drag to resize column")}" style="display: inline-flex; align-items: center; justify-content: center; position: absolute; right: 4px; top: 50%; transform: translateY(-50%); min-width: 34px; height: 22px; border: 1px solid #2490ef; border-radius: 11px; background: #fff; color: #2490ef; cursor: col-resize; z-index: 20; font-size: 10px; font-weight: 600; line-height: 1; box-shadow: 0 1px 5px rgba(0,0,0,.22);">Drag</span>`
				);
			}
		});

		if (listview.__cmelv_resize_bound) return;
		listview.__cmelv_resize_bound = true;

		listview.$result.on("mousedown", ".cmelv-resize-handle", (event) => {
			event.preventDefault();
			event.stopPropagation();

			const header = event.currentTarget.closest("[data-cmelv-fieldname]");
			const fieldname = header?.dataset.cmelvFieldname;
			const index = header?.dataset.cmelvIndex;
			if (!fieldname || index == null) return;

			const start_x = event.clientX;
			const start_width = header.getBoundingClientRect().width;
			let next_width = start_width;
			let frame = null;

			const move = (move_event) => {
				next_width = clamp_width(start_width + move_event.clientX - start_x);
				if (frame) return;
				frame = window.requestAnimationFrame(() => {
					frame = null;
					listview.$result.find(`[data-cmelv-index="${index}"]`).css({
						width: next_width + "px",
						"min-width": MIN_WIDTH + "px",
						flex: `0 0 ${next_width}px`,
					});
				});
			};

			const up = () => {
				$(document).off(".cmelv-resize");
				const layout = get_layout(listview);
				layout.version = 1;
				layout.widths = Object.assign({}, layout.widths || {}, {
					[fieldname]: clamp_width(next_width),
				});
				save_layout(listview, layout);
			};

			$(document).on("mousemove.cmelv-resize", move);
			$(document).on("mouseup.cmelv-resize", up);
		});
	}

	function show_settings_dialog(listview) {
		const layout = get_layout(listview);
		const widths = get_widths(layout);
		const visible_keys = layout.custom_columns
			? (layout.columns || [])
					.filter((column) => column.visible !== false)
					.map((column) => column.fieldname)
			: get_current_visible_keys(listview);
		const saved_order = (layout.columns || []).map((column) => column.fieldname);
		const defaults = get_default_columns(listview);
		const ordered = defaults
			.slice()
			.sort((a, b) => {
				const a_index = saved_order.indexOf(a.key);
				const b_index = saved_order.indexOf(b.key);
				return (a_index === -1 ? 9999 : a_index) - (b_index === -1 ? 9999 : b_index);
			});

		const dialog = new frappe.ui.Dialog({
			title: __("Customize Columns"),
			fields: [{ fieldtype: "HTML", fieldname: "columns_html" }],
		});

		const rows = ordered
			.map((column) => {
				const width = clamp_width(widths[column.key] || measure_column(listview, column.key));
				const checked = visible_keys.includes(column.key) || column.required ? "checked" : "";
				const disabled = column.required ? "disabled" : "";
				return `
					<div class="cmelv-settings-row" data-fieldname="${frappe.utils.escape_html(column.key)}">
						<div class="cmelv-settings-drag">${frappe.utils.icon("drag", "xs")}</div>
						<label class="cmelv-settings-visible">
							<input type="checkbox" ${checked} ${disabled}>
						</label>
						<div class="cmelv-settings-field ellipsis" title="${frappe.utils.escape_html(column.label)}">
							${frappe.utils.escape_html(column.label)}
						</div>
						<div class="cmelv-settings-width">
							<input class="form-control input-xs" type="number" min="${MIN_WIDTH}" max="${MAX_WIDTH}" value="${width}">
						</div>
					</div>
				`;
			})
			.join("");

		dialog.fields_dict.columns_html.$wrapper.html(`
			<div class="cmelv-settings">
				<div class="cmelv-settings-head">
					<span></span>
					<span>${__("Visible")}</span>
					<span>${__("Field")}</span>
					<span>${__("Width")}</span>
				</div>
				<div class="cmelv-settings-body">${rows}</div>
			</div>
		`);

		const body = dialog.fields_dict.columns_html.$wrapper
			.find(".cmelv-settings-body")
			.get(0);
		if (window.Sortable && body) {
			new Sortable(body, {
				handle: ".cmelv-settings-drag",
				draggable: ".cmelv-settings-row",
			});
		}

		dialog.set_secondary_action(() => {
			reset_layout(listview);
			dialog.hide();
		});
		dialog.set_secondary_action_label(__("Reset to Default"));

		dialog.set_primary_action(__("Save"), () => {
			const columns = [];
			dialog.fields_dict.columns_html.$wrapper.find(".cmelv-settings-row").each((order, row) => {
				const $row = $(row);
				const fieldname = $row.attr("data-fieldname");
				const required = fieldname === get_subject_field(listview).fieldname;
				columns.push({
					fieldname,
					visible: required || $row.find('input[type="checkbox"]').prop("checked"),
					width: clamp_width($row.find('input[type="number"]').val()),
					order,
				});
			});

			const next_layout = {
				version: 1,
				custom_columns: true,
				widths: columns.reduce((out, column) => {
					out[column.fieldname] = column.width;
					return out;
				}, {}),
				columns,
			};

			save_layout(listview, next_layout).then(() => {
				dialog.hide();
				refresh_with_fields(listview);
			});
		});

		dialog.show();
	}

	function reset_layout(listview) {
		save_layout(listview, null).then(() => refresh_with_fields(listview));
	}

	function refresh_with_fields(listview) {
		Promise.resolve(listview.setup_fields?.()).then(() => {
			listview.setup_columns();
			listview.refresh(true);
		});
	}

	function patch_listview() {
		if (!frappe.views?.ListView || frappe.views.ListView.__cmelv_patched) return Boolean(frappe.views?.ListView);

		const proto = frappe.views.ListView.prototype;
		frappe.views.ListView.__cmelv_patched = true;

		const original_set_fields = proto.set_fields;
		proto.set_fields = async function () {
			await original_set_fields.apply(this, arguments);
			if (!is_enabled(this)) return;

			const layout = get_layout(this);
			if (!layout.custom_columns) return;

			await Promise.all(
				(layout.columns || [])
				.filter((column) => column.visible !== false)
				.map((column) => {
					if (["status_field", "_user_tags"].includes(column.fieldname)) {
						return Promise.resolve();
					}

					const df = get_docfield(this, column.fieldname);
					if (
						df &&
						df.fieldtype === "Link" &&
						frappe.boot.link_title_doctypes.includes(df.options)
					) {
						return new Promise((resolve) => {
							frappe.model.with_doctype(df.options, () => {
								const meta = frappe.get_meta(df.options);
								if (meta.show_title_field_in_link && meta.title_field) {
									this.link_field_title_fields[df.fieldname] = meta.title_field;
								}
								this._add_field(df.fieldname);
								resolve();
							});
						});
					}

					this._add_field(column.fieldname);
					return Promise.resolve();
				})
			);
		};

		const original_setup_columns = proto.setup_columns;
		proto.setup_columns = function () {
			original_setup_columns.apply(this, arguments);
			if (!is_enabled(this)) return;

			const layout = get_layout(this);
			if (layout.custom_columns) {
				this.columns = build_custom_columns(this, layout);
			}
		};

		const original_get_header_html = proto.get_header_html;
		proto.get_header_html = function () {
			if (!is_enabled(this)) {
				return original_get_header_html.apply(this, arguments);
			}

			if (!this.columns) return;

			let $columns = this.columns
				.map((col) => {
					const fieldname = get_column_key(col);
					const df = col.df || {};
					const label = get_column_label(this, fieldname);
					const classes = [
						"list-row-col ellipsis",
						col.type === "Subject" ? "list-subject level" : "hidden-xs",
						col.type === "Tag" ? `tag-col ${!this.tags_shown ? "hide" : ""}` : "",
						df && frappe.model.is_numeric_field(df) ? "text-right" : "",
						fieldname,
					].join(" ");

					let html = "";
					if (col.type === "Subject") {
						html = `
							<span class="level-item select-like">
								<input class="list-header-checkbox list-check-all" type="checkbox" title="${__("Select All")}">
							</span>
							<span class="level-item" data-sort-by="${fieldname}"
								title="${__("Click to sort by {0}", [label])}">
								${label}
							</span>
						`;
					} else {
						const attrs =
							fieldname && !["status_field", "_user_tags"].includes(fieldname)
								? `data-sort-by="${fieldname}" title="${__("Click to sort by {0}", [label])}"`
								: "";
						html = `<span ${attrs}>${label}</span>`;
					}

					return `<div class="${classes}">${html}</div>`;
				})
				.join("");

			if (this.settings.button) $columns += '<div class="list-row-col hidden-xs"></div>';
			if (this.settings.dropdown_button) $columns += '<div class="list-row-col hidden-xs"></div>';

			const right_html = `
				<span class="list-count" style=""></span>
				<span class="level-item list-liked-by-me hidden-xs">
					<span title="${__("Liked by me")}">
						<svg class="icon icon-sm like-icon"><use href="#icon-heart"></use></svg>
					</span>
				</span>
			`;

			return this.get_header_html_skeleton($columns, right_html);
		};

		const original_render_list = proto.render_list;
		proto.render_list = function () {
			const result = original_render_list.apply(this, arguments);
			window.requestAnimationFrame(() => enhance_dom(this));
			return result;
		};

		const original_render_header = proto.render_header;
		proto.render_header = function () {
			const result = original_render_header.apply(this, arguments);
			window.requestAnimationFrame(() => enhance_dom(this));
			return result;
		};

		const original_get_menu_items = proto.get_menu_items;
		proto.get_menu_items = function () {
			const items = original_get_menu_items.apply(this, arguments) || [];
			if (!is_enabled(this)) return items;

			items.push({
				label: __("Customize Columns"),
				action: () => show_settings_dialog(this),
				standard: true,
			});
			items.push({
				label: __("Reset List View Layout"),
				action: () => reset_layout(this),
				standard: true,
			});

			return items;
		};

		return true;
	}

	function boot_patch(attempts) {
		if (patch_listview()) return;
		if (attempts > 0) {
			window.setTimeout(() => boot_patch(attempts - 1), 100);
		}
	}

	boot_patch(50);
})();
