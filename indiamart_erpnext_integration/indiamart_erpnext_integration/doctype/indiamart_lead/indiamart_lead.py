# Copyright (c) 2021, GreyCube Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
import json
from frappe.utils.background_jobs import enqueue
from frappe import _
from indiamart_erpnext_integration.indiamart_erpnext_controller import make_erpnext_lead_from_inidamart


class IndiamartLead(Document):
		def after_insert(self):
			frappe.db.set_value('Indiamart Lead', self.name, 'created_on', self.creation)
			try:
				indiamart_lead_json = json.loads(self.indiamart_lead_json or "{}")
				make_erpnext_lead_from_inidamart(indiamart_lead_json, self.name)
			except Exception:
				frappe.log_error(title=_("Indiamart Error"), message=frappe.get_traceback())
				frappe.db.set_value("Indiamart Lead", self.name, {
					"status": "Failed",
					"output": "Prospect creation failed. Check Error Log.",
				})

		@frappe.whitelist()
		def retry_lead_creation(self):
			try:
				indiamart_lead_json = json.loads(self.indiamart_lead_json)
				output = make_erpnext_lead_from_inidamart(indiamart_lead_json, self.name)
				if output:
					frappe.msgprint(_("Output is {0}.").format(frappe.bold(output)), alert=False, indicator="green")
				else:
					frappe.msgprint(_("Error occured. Please check error log."), alert=False, indicator="red")
			except Exception:
				frappe.log_error(title=_("Indiamart Error"), message=frappe.get_traceback())
				frappe.msgprint(_("Error occured. Please check error log."), alert=False, indicator="red")

@frappe.whitelist()
def get_connected_indiamart_lead(query_id_cf):
	il_list=[]
	il_results=frappe.db.sql("""SELECT  distinct india_lead.name as il FROM  `tabIndiamart Lead` india_lead
where india_lead.query_id =%s""",
        (query_id_cf),as_dict=True)
	if len(il_results)>0:
		for il in il_results:
			il_list.append(il.il)
		return il_list
	else:
		return []  			

@frappe.whitelist()
def get_connected_error_log(indiamart_lead):
	el_list=[]
	el_results=frappe.db.sql("""SELECT  distinct name as el FROM  `tabError Log` error_log
where error_log.error like %s""",
        ("%" + indiamart_lead + "%"),as_dict=True)
	if len(el_results)>0:
		for el in el_results:
			el_list.append(el.el)
		return el_list
	else:
		return []  		


@frappe.whitelist()
def get_connected_indiamart_lead_for_integration_request(integration_request):
	il_list=[]
	il_results=frappe.db.sql("""SELECT  distinct india_lead.name as il FROM  `tabIndiamart Lead` india_lead
where india_lead.integration_request =%s""",
        (integration_request),as_dict=True)
	if len(il_results)>0:
		for il in il_results:
			il_list.append(il.il)
		return il_list
	else:
		return []  			

@frappe.whitelist()
def get_connected_lead_for_indiamart_lead(query_id_cf):
	l_list=[]
	l_results=frappe.db.sql("""SELECT  distinct lead.name as l FROM  `tabLead` lead
where lead.query_id_cf =%s""",
        (query_id_cf),as_dict=True)
	if len(l_results)>0:
		for l in l_results:
			l_list.append(l.l)
		return l_list
	else:
		return []


@frappe.whitelist()
def get_connected_prospect_for_indiamart_lead(query_id_cf):
	if not query_id_cf or not frappe.get_meta("Prospect").has_field("query_id_cf"):
		return []
	return frappe.db.get_all(
		"Prospect",
		filters={"query_id_cf": query_id_cf},
		pluck="name",
	) 