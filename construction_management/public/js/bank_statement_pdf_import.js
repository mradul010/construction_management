(() => {
	const method =
		"construction_management.construction_management.bank_statement_pdf_import";

	function money(value) {
		return format_currency(flt(value), "AED");
	}

	function summary_html(result) {
		const s = result.summary;
		return `<div class="alert alert-info">
			<b>${__("Parser")}:</b> ${frappe.utils.escape_html(result.parser)} (${frappe.utils.escape_html(result.extraction_engine)})<br>
			<b>${__("Transactions")}:</b> ${s.total_transactions} &nbsp;
			<b>${__("Valid")}:</b> ${s.valid_transactions} &nbsp;
			<b>${__("Duplicates")}:</b> ${s.duplicates} &nbsp;
			<b>${__("Possible Duplicates")}:</b> ${s.possible_duplicates} &nbsp;
			<b>${__("Invalid")}:</b> ${s.invalid_transactions}<br>
			<b>${__("Deposits")}:</b> ${money(s.total_deposits)} &nbsp;
			<b>${__("Withdrawals")}:</b> ${money(s.total_withdrawals)} &nbsp;
			<b>${__("Opening Balance")}:</b> ${result.opening_balance == null ? __("Not Available") : money(result.opening_balance)} &nbsp;
			<b>${__("Closing Balance")}:</b> ${result.closing_balance == null ? __("Not Available") : money(result.closing_balance)}
		</div>`;
	}

	function open_reconciliation(company, bank_account) {
		frappe.route_options = {company, bank_account};
		frappe.set_route("Form", "Bank Reconciliation Tool");
	}

	function preview(result) {
		const dialog = new frappe.ui.Dialog({
			title: __("Review PDF Bank Transactions"),
			size: "extra-large",
			fields: [
				{fieldtype: "HTML", fieldname: "summary", options: summary_html(result)},
				{
					fieldtype: "Table",
					fieldname: "transactions",
					label: __("Extracted Transactions"),
					cannot_add_rows: true,
					cannot_delete_rows: true,
					in_place_edit: true,
					data: result.rows,
					fields: [
						{fieldtype: "Check", fieldname: "selected", label: __("Import"), in_list_view: 1, columns: 1},
						{fieldtype: "Date", fieldname: "date", label: __("Date"), in_list_view: 1, columns: 1},
						{fieldtype: "Small Text", fieldname: "description", label: __("Description"), in_list_view: 1, columns: 3},
						{fieldtype: "Data", fieldname: "reference", label: __("Reference"), in_list_view: 1, columns: 2},
						{fieldtype: "Currency", fieldname: "withdrawal", label: __("Withdrawal"), in_list_view: 1, columns: 1},
						{fieldtype: "Currency", fieldname: "deposit", label: __("Deposit"), in_list_view: 1, columns: 1},
						{fieldtype: "Currency", fieldname: "balance", label: __("Balance"), in_list_view: 1, columns: 1},
						{fieldtype: "Data", fieldname: "validation_status", label: __("Validation"), in_list_view: 1, read_only: 1, columns: 2},
						{fieldtype: "Check", fieldname: "balance_reviewed", label: __("Balance Reviewed")},
						{fieldtype: "Check", fieldname: "duplicate_reviewed", label: __("Duplicate Reviewed")},
						{fieldtype: "Data", fieldname: "row_id", hidden: 1},
						{fieldtype: "Data", fieldname: "transaction_id", hidden: 1},
						{fieldtype: "Data", fieldname: "duplicate_status", hidden: 1},
					],
				},
			],
			primary_action_label: __("Import Selected Transactions"),
			primary_action() {
				const rows = dialog.fields_dict.transactions.grid.get_data().map((row) => ({...row}));
				frappe.call({
					method: `${method}.import_transactions`,
					args: {preview_token: result.preview_token, rows: JSON.stringify(rows)},
					freeze: true,
					freeze_message: __("Importing selected bank transactions..."),
				}).then(({message}) => {
					dialog.hide();
					const counts = message.counts;
					frappe.msgprint({
						title: __("PDF Bank Statement Import"),
						indicator: counts.failed ? "orange" : "green",
						message: __("Imported: {0}<br>Skipped: {1}<br>Failed: {2}", [counts.imported, counts.skipped, counts.failed]),
						primary_action: {
							label: __("Open Bank Reconciliation"),
							action: () => open_reconciliation(result.company, result.bank_account),
						},
					});
					if (result.data_import && window.cur_frm?.doc?.name === result.data_import) {
						window.cur_frm.reload_doc();
					}
				});
			},
		});
		dialog.show();
		dialog.$wrapper.find(".modal-dialog").css("max-width", "95vw");
		dialog.$wrapper.find(".modal-content").css({"max-height": "92vh", "overflow": "hidden"});
		dialog.$wrapper.find(".modal-body").css({"overflow-y": "auto", "overflow-x": "hidden"});
		const table_wrapper = dialog.fields_dict.transactions.$wrapper;
		table_wrapper.css({"overflow-x": "auto", "padding-bottom": "8px"});
		table_wrapper.find(".form-grid, .grid-heading-row, .grid-row").css({"min-width": "1800px"});
		const bottom_scroll = $('<div class="pdf-bank-bottom-scroll"><div></div></div>').css({
			"overflow-x": "scroll", height: "20px", margin: "0 20px 6px", "flex-shrink": 0,
		});
		bottom_scroll.children().css({width: "1800px", height: "1px"});
		dialog.$wrapper.find(".modal-footer").before(bottom_scroll);
		let syncing = false;
		bottom_scroll.on("scroll", () => {
			if (syncing) return;
			syncing = true;
			table_wrapper.scrollLeft(bottom_scroll.scrollLeft());
			syncing = false;
		});
		table_wrapper.on("scroll", () => {
			if (syncing) return;
			syncing = true;
			bottom_scroll.scrollLeft(table_wrapper.scrollLeft());
			syncing = false;
		});
	}

	function upload_dialog(frm) {
		const dialog = new frappe.ui.Dialog({
			title: __("Import PDF Bank Statement"),
			fields: [
				{fieldtype: "Link", fieldname: "company", label: __("Company"), options: "Company", reqd: 1, default: frm.doc.company},
				{fieldtype: "Link", fieldname: "bank_account", label: __("Bank Account"), options: "Bank Account", reqd: 1, default: frm.doc.bank_account,
					get_query: () => ({filters: {company: dialog.get_value("company")}})},
				{fieldtype: "Attach", fieldname: "pdf_statement", label: __("Private PDF Statement"), reqd: 1,
					options: {make_attachments_public: false, allow_toggle_private: false, allow_web_link: false,
						allow_google_drive: false, allow_take_photo: false,
						restrictions: {allowed_file_types: [".pdf"], max_file_size: 20 * 1024 * 1024}}},
			],
			primary_action_label: __("Extract and Preview"),
			primary_action(values) {
				frappe.call({
					method: `${method}.extract_preview`,
					args: {company: values.company, bank_account: values.bank_account, file_url: values.pdf_statement,
						data_import: frm.is_new() ? null : frm.doc.name},
					freeze: true,
					freeze_message: __("Extracting the private PDF statement..."),
				}).then(({message}) => {
					dialog.hide();
					preview(message);
				});
			},
		});
		dialog.show();
	}

	function extract_form_pdf(frm) {
		if (!frm.doc.company || !frm.doc.bank_account || !frm.doc.custom_pdf_statement) {
			frappe.msgprint(__("Select the Company, Bank Account and private PDF statement first."));
			return;
		}
		frappe.call({
			method: `${method}.extract_preview`,
			args: {company: frm.doc.company, bank_account: frm.doc.bank_account, file_url: frm.doc.custom_pdf_statement,
				data_import: frm.is_new() ? null : frm.doc.name},
			freeze: true,
			freeze_message: __("Extracting the private PDF statement..."),
		}).then(({message}) => preview(message));
	}

	function toggle_import_format(frm) {
		const pdf = frm.doc.custom_import_source === "PDF (QATRA Mashreq)";
		["import_mt940_fromat", "custom_delimiters", "delimiter_options", "google_sheets_url", "refresh_google_sheet",
			"html_5", "import_file", "download_template", "section_import_preview", "import_preview"].forEach((field) =>
			frm.toggle_display(field, !pdf)
		);
		frm.toggle_display("custom_pdf_statement", pdf);
		frm.toggle_display("custom_extract_pdf", pdf);
		if (pdf && frm.doc.import_file && frm.doc.import_file.toLowerCase().endsWith(".pdf")) {
			const uploaded_pdf = frm.doc.import_file;
			frm.set_value("import_file", null).then(() => frm.set_value("custom_pdf_statement", uploaded_pdf));
		}
	}

	frappe.ui.form.on("Bank Statement Import", {
		setup(frm) {
			const field = frm.get_field("custom_pdf_statement");
			if (field) {
				field.df.options = {make_attachments_public: false, allow_toggle_private: false, allow_web_link: false,
					allow_google_drive: false, allow_take_photo: false,
					restrictions: {allowed_file_types: [".pdf"], max_file_size: 20 * 1024 * 1024}};
			}
		},
		refresh(frm) {
			frm.add_custom_button(__("PDF Import"), () => upload_dialog(frm), __("Import"));
			toggle_import_format(frm);
		},
		custom_import_source: toggle_import_format,
		custom_extract_pdf: extract_form_pdf,
	});
})();
