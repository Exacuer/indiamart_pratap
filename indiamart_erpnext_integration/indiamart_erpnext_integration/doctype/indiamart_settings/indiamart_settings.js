// Copyright (c) 2021, GreyCube Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('Indiamart Settings', {
	refresh: function (frm) {
		if (frm.is_new() == undefined && frm.doc.enabled == 1) {
			frm.add_custom_button(__('Manually Pull Prospects'), () => {
				let d = new frappe.ui.Dialog({
					title: __('Retrigger IndiaMART pull for a time frame'),
					fields: [{
							label: __('Start Date Time'),
							fieldname: 'start_time',
							fieldtype: 'Datetime',
							default: moment(frappe.datetime.now_datetime()).subtract({
								minutes: 6
							}),
							reqd: 1
						},
						{
							label: __('End Date Time'),
							fieldname: 'end_time',
							fieldtype: 'Datetime',
							default: frappe.datetime.now_datetime(),
							reqd: 1
						}
					],
					primary_action_label: __('Fetch'),
					primary_action(values) {
						frappe.call({
							method: 'indiamart_erpnext_integration.indiamart_erpnext_controller.manual_pull_indiamart_leads',
							args: {
								start_time: values.start_time,
								end_time: values.end_time
							},
							callback: () => {
								frappe.msgprint(__('Execution started successfully'));
							}
						});
						d.hide();
					}
				});
				d.show();
			});
		}
	}
});
