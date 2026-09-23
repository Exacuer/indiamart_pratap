// Copyright (c) 2021, GreyCube Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('Indiamart Lead', {
	refresh: function (frm) {
		if (['Queued', 'Failed'].includes(frm.doc.status)) {
			frm.add_custom_button('Retry Prospect Creation', () => {
				frm.call('retry_lead_creation')
					.then(r => {
						console.log(r)
					})

			})
		}
		$('div').find('.document-link[data-doctype="ToDo"]').hide();
		// Error Log connection
		$('div').find('.document-link[data-doctype="Error Log"]').remove();
		if (frm.is_new() == undefined) {
			frappe.call('indiamart_erpnext_integration.indiamart_erpnext_integration.doctype.indiamart_lead.indiamart_lead.get_connected_error_log', {
				indiamart_lead: frm.doc.name
			}).then(r => {
				if (r.message && r.message != undefined) {
					let count = r.message.length
					let link = $(`
			<div class="document-link" data-doctype="Error Log">
				<div class="document-link-badge" data-doctype="Error Log"> <span class="count">${count}</span> <a
					class="badge-link">Error Log</a> </div> <span class="open-notification hidden"
				title="Open Error Log"> </span></div>
			`);
					link.on('click', function () {
						frappe.route_options = {
							'name': ['in', r.message]
						};
						frappe.set_route("List", "Error Log", "List");
					})
					$('div').find('.document-link[data-doctype="ToDo"]').after(link);
				}
			})
		}
		// Integration Request connection
		$('div').find('.document-link[data-doctype="Integration Request"]').remove();
		if (frm.is_new() == undefined && frm.doc.integration_request != undefined) {
			let count = 1
			let link = $(`
			<div class="document-link" data-doctype="Integration Request">
				<div class="document-link-badge" data-doctype="Integration Request"> <span class="count">${count}</span> <a
					class="badge-link">Integration Request</a> </div> <span class="open-notification hidden"
				title="Open Integration Request"> </span></div>
			`);
			link.on('click', function () {
				frappe.route_options = {
					'name': ['in', frm.doc.integration_request]
				};
				frappe.set_route("List", "Integration Request", "List");
			})
			$('div').find('.document-link[data-doctype="ToDo"]').after(link);
		}
		// Prospect connection
		$('div').find('.document-link[data-doctype="Prospect"]').remove();
		if (frm.is_new() == undefined && frm.doc.query_id != undefined) {
			frappe.call('indiamart_erpnext_integration.indiamart_erpnext_integration.doctype.indiamart_lead.indiamart_lead.get_connected_prospect_for_indiamart_lead', {
				query_id_cf: frm.doc.query_id
			}).then(r => {
				if (r.message && r.message != undefined) {
					let count = r.message.length
					let link = $(`
			<div class="document-link" data-doctype="Prospect">
				<div class="document-link-badge" data-doctype="Prospect"> <span class="count">${count}</span> <a
					class="badge-link">Prospect</a> </div> <span class="open-notification hidden"
				title="Open Prospect"> </span></div>
			`);
					link.on('click', function () {
						frappe.route_options = {
							'name': ['in', r.message]
						};
						frappe.set_route("List", "Prospect", "List");
					})
					$('div').find('.document-link[data-doctype="ToDo"]').after(link);
				}
			})
		}
	}
});