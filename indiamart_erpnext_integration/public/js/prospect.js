frappe.ui.form.on('Prospect', {
    refresh: function (frm) {
		$('div').find('.document-link[data-doctype="Indiamart Lead"]').remove();
		if (frm.is_new() == undefined && frm.doc.query_id_cf != undefined) {
			frappe.call('indiamart_erpnext_integration.indiamart_erpnext_integration.doctype.indiamart_lead.indiamart_lead.get_connected_indiamart_lead', {
				query_id_cf: frm.doc.query_id_cf
			}).then(r => {
				if (r.message && r.message != undefined) {
					let count = r.message.length
					let link = $(`
			<div class="document-link" data-doctype="Indiamart Lead">
				<div class="document-link-badge" data-doctype="Indiamart Lead"> <span class="count">${count}</span> <a
					class="badge-link">Indiamart Lead</a> </div> <span class="open-notification hidden"
				title="Open Indiamart Lead"> </span></div>
			`);
					link.on('click', function () {
						frappe.route_options = {
							'name': ['in', r.message]
						};
						frappe.set_route("List", "Indiamart Lead", "List");
					})
					$('.form-dashboard-wrapper .connections-fetch').append(link);
					$('div').find('.document-link[data-doctype="Quotation"]').after(link);
				}
			})
		}
    }
})
