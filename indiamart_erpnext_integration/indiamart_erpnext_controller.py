from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.integrations.utils import create_request_log,make_post_request
from frappe.utils import get_datetime,now_datetime,format_datetime,cstr
from datetime import timedelta
import datetime
from frappe.utils.password import get_decrypted_password
from frappe.model.document import Document
import json
from six import string_types
import traceback,sys
from erpnext.crm.doctype.lead.lead import make_opportunity
from indiamart_erpnext_integration.indiamart_prospect import make_erpnext_prospect_from_indiamart


MIN_API_INTERVAL_MINUTES = 6


# manually pull leads for given time frame
@frappe.whitelist()
def manual_pull_indiamart_leads(start_time,end_time):
	try:
		indiamart_settings=get_indiamart_configuration()
		if indiamart_settings!='disabled':
			api_url,now_api_call_time=get_indiamart_api_url(indiamart_settings,start_time,end_time)
			if api_url:
				fetch_indiamart_data_and_make_integration_request(api_url,now_api_call_time)
	except Exception as e:
		title=_('Indiamart Error')
		seperator = "--" * 50
		error = "\n".join([format_datetime(now_datetime(),'d-MMM-y  HH:mm:ss'), "manual_pull_indiamart_leads",str(sys.exc_info()[1]), seperator,frappe.get_traceback()])
		frappe.log_error(message=error, title=title)

# entry point for scheduler 
@frappe.whitelist()
def auto_pull_indiamart_leads():
	try:
		indiamart_settings=get_indiamart_configuration()
		if indiamart_settings!='disabled':
			if _called_too_recently(indiamart_settings):
				return
			api_url,now_api_call_time=get_indiamart_api_url(indiamart_settings)
			if api_url:
				fetch_indiamart_data_and_make_integration_request(api_url,now_api_call_time)
	except Exception as e:
		title=_('Indiamart Error')
		seperator = "--" * 50
		error = "\n".join([format_datetime(now_datetime(),'d-MMM-y  HH:mm:ss'), "auto_pull_indiamart_leads",str(sys.exc_info()[1]), seperator,frappe.get_traceback()])
		frappe.log_error(message=error, title=title)


def get_indiamart_configuration():
	if frappe.db.get_single_value("Indiamart Settings", "enabled"):
		indiamart_settings = frappe.get_doc("Indiamart Settings")
		return {
			"glusr_mobile": indiamart_settings.glusr_mobile,
			"glusr_mobile_key": indiamart_settings.glusr_mobile_key,
			"last_api_call_time": indiamart_settings.last_api_call_time
		}
	return "disabled"


def _called_too_recently(indiamart_settings):
	last_call = indiamart_settings.get("last_api_call_time")
	if not last_call:
		return False
	elapsed = (now_datetime() - get_datetime(last_call)).total_seconds()
	return elapsed < MIN_API_INTERVAL_MINUTES * 60


def get_indiamart_api_url(indiamart_settings,start_time=None,end_time=None):
	URL_DATETIME_FORMAT = 'd-MMM-yHH:mm:ss'
	# INDIAMART_URL = 'https://mapi.indiamart.com/wservce/enquiry/listing/GLUSR_MOBILE/{0}/GLUSR_MOBILE_KEY/{1}/Start_Time/{2}/End_Time/{3}/'
	INDIAMART_URL = 'https://mapi.indiamart.com/wservce/crm/crmListing/v2/?glusr_crm_key={1}&start_time={2}&end_time={3}'

	#  scheduler flow
	if start_time==None:
		# set start time as minus 5 minutes the last api call time
		if indiamart_settings.get('last_api_call_time'):
			start_time=get_datetime(indiamart_settings.get('last_api_call_time')) - datetime.timedelta(minutes=5)
		else:
			# first time, last_api_call_time will be empty
			start_time= now_datetime() - datetime.timedelta(minutes=5)

		start_time=format_datetime(start_time,URL_DATETIME_FORMAT)
		now_api_call_time=now_datetime()
		end_time=format_datetime(now_api_call_time,URL_DATETIME_FORMAT)
	# manual pull flow
	else:
		start_time=format_datetime(start_time,URL_DATETIME_FORMAT)
		end_time=format_datetime(end_time,URL_DATETIME_FORMAT)
		# we don't change last call time as it is a manual attempt
		now_api_call_time=indiamart_settings.get('last_api_call_time') or now_datetime()
	#  to do : put in config
	api_url = INDIAMART_URL.format(
				indiamart_settings.get('glusr_mobile'),
				get_decrypted_password('Indiamart Settings','Indiamart Settings','glusr_mobile_key'),
				start_time,
				end_time)
	return api_url,now_api_call_time



def _normalize_indiamart_message(message):
	return " ".join(cstr(message).replace(",", ", ").split()).strip().lower()


def _is_rate_limit_message(message):
	text = _normalize_indiamart_message(message)
	return "every 5 minutes" in text or "crossed this limit" in text or "try again after 5 minutes" in text


def _is_no_leads_message(message):
	text = _normalize_indiamart_message(message)
	return "no leads" in text or "no lead" in text


def fetch_indiamart_data_and_make_integration_request(api_url,now_api_call_time):
	response = None
	try:
		response = make_post_request(api_url)
	except Exception:
		frappe.log_error(title=_("Indiamart Error"), message=frappe.get_traceback())
		return

	if not response:
		return

	if isinstance(response, string_types):
		try:
			response = json.loads(response)
		except Exception:
			frappe.log_error(title=_("Indiamart Error"), message=frappe.get_traceback())
			return
	response_result = response.get("RESPONSE") or []
	if not isinstance(response_result, list):
		response_result = []
	data={
		'api_url':api_url
	}
	request_log_data={
		'api_url':api_url,
		"reference_doctype":"Indiamart Lead"
	}
	error=None
	output={
		'output':response_result
	}

	if response.get('MESSAGE') and response.get('MESSAGE')!="":
		error=response.get('MESSAGE')
		
	if not error:
		integration_request=create_request_log(data=frappe._dict(request_log_data),integration_type="Remote",service_name="Indiamart")
		frappe.db.set_value('Integration Request', integration_request.name, 'output',json.dumps(output) )
	else:
		integration_request=create_request_log(data=frappe._dict(request_log_data),integration_type="Remote",service_name="Indiamart",error=frappe._dict({"error":error}))
		frappe.db.set_value('Integration Request', integration_request.name, 'output', json.dumps(output))

	error_message=response.get('MESSAGE')
	status=None

	if not error_message:
		status='Queued'
	elif _is_rate_limit_message(error_message):
		frappe.db.set_value('Integration Request', integration_request.name, 'status', 'Cancelled')
		frappe.db.set_value('Indiamart Settings','Indiamart Settings', 'last_api_call_time', now_datetime())
		status='Failed'
	elif _is_no_leads_message(error_message):
		frappe.db.set_value('Integration Request', integration_request.name, 'status', 'Cancelled')
		frappe.db.set_value('Indiamart Settings','Indiamart Settings', 'last_api_call_time', now_api_call_time)
		status='Failed'
	else:
		frappe.db.set_value('Integration Request', integration_request.name, 'status', 'Failed')
		status='Failed'
		frappe.log_error(
			message=cstr(error_message) + '\nIntegration Request ID :' + integration_request.name,
			title=_("Indiamart Error"),
		)

	if 	status!='Failed':
		failed_count = 0
		for index in range(len(response_result)):
			try:
				lead_values = dict(response_result[index] or {})
				make_indiamart_lead_records(lead_values, integration_request.name)
			except Exception:
				failed_count += 1
				frappe.log_error(title=_("Indiamart Error"), message=frappe.get_traceback())
		status_value = 'Failed' if failed_count and failed_count == len(response_result) else 'Completed'
		frappe.db.set_value('Integration Request', integration_request.name, 'status', status_value)
		frappe.db.set_value('Indiamart Settings','Indiamart Settings', 'last_api_call_time', now_api_call_time)
	return

def make_indiamart_lead_records(lead_values,integration_request,status='Queued',output='Not Processed'):
	existing_indiamart_lead = frappe.db.get_value("Indiamart Lead", {"query_id": lead_values.get('UNIQUE_QUERY_ID')})
	if existing_indiamart_lead:
		existing_status = frappe.db.get_value("Indiamart Lead", existing_indiamart_lead, "status")
		if existing_status in ("Queued", "Failed", None, ""):
			make_erpnext_prospect_from_indiamart(lead_values, existing_indiamart_lead)
		return existing_indiamart_lead

	indiamart_lead=frappe.new_doc('Indiamart Lead')
	indiamart_lead.query_id=lead_values.get('UNIQUE_QUERY_ID',None)
	indiamart_lead.indiamart_lead_json=json.dumps(lead_values)
	indiamart_lead.status=status
	indiamart_lead.output=output
	indiamart_lead.integration_request=integration_request
	indiamart_lead.save(ignore_permissions=True)
	return indiamart_lead.name


def make_erpnext_lead_from_inidamart(lead_values,indiamart_lead_name=None):
	return make_erpnext_prospect_from_indiamart(lead_values, indiamart_lead_name)


def _legacy_make_erpnext_lead_from_inidamart(lead_values,indiamart_lead_name=None):
	try:
		output=None
		user=frappe.db.get_single_value('Indiamart Settings', 'default_lead_owner')
		country=frappe.get_value("Country", {"code": lead_values.get("SENDER_COUNTRY_ISO", "IN").lower()}) or 'India'
		state=lead_values.get('SENDER_STATE',None)
		city=lead_values.get('SENDER_CITY',None)
		email_id=lead_values.get('SENDER_EMAIL',None)
		mobile_no=lead_values.get('SENDER_MOBILE',None)		

		lead_owner=user
		lead_name = None
		lead_name = frappe.db.get_value("Lead", {"query_id_cf": lead_values.get('UNIQUE_QUERY_ID')})
		if not lead_name:
			source = ''
			if lead_values.get('QUERY_TYPE') == 'W':
				source = frappe.db.get_single_value('Indiamart Settings', 'direct_lead_source')
			elif lead_values.get('QUERY_TYPE') == 'B':
				source = frappe.db.get_single_value('Indiamart Settings', 'buy_lead_source')
			elif lead_values.get('QUERY_TYPE') == 'P':
				source = frappe.db.get_single_value('Indiamart Settings', 'call_lead_source')

			organization_lead = 1 if lead_values.get('SENDER_COMPANY') else 0
			company_name = lead_values.get('SENDER_COMPANY') if organization_lead else None
			address_type = 'Office' if organization_lead else 'Personal'
			address_title = 'Work'

			notes_html = f"""
        		<div>Product Name: {frappe.bold(lead_values.get('QUERY_PRODUCT_NAME', 'Not specified'))}</div>
        		<div>Subject: {frappe.bold(lead_values.get('SUBJECT', 'Not specified'))}</div>
        		<div>Message: {frappe.bold(lead_values.get('QUERY_MESSAGE', 'Not specified'))}</div>
        		<div>Lead Date: {frappe.bold(lead_values.get('QUERY_TIME', 'Not specified'))}</div>
        		<div>Alternate EmailID: {frappe.bold(lead_values.get('EMAIL_ALT', 'Not specified'))}</div>
        		<div>Alternate Mobile: {frappe.bold(lead_values.get('MOBILE_ALT', 'Not specified'))}</div>
        		<div>India Mart Query ID: {frappe.bold(lead_values.get('UNIQUE_QUERY_ID', 'Not specified'))}</div>
        		"""
			n = 140
			address = lead_values.get('SENDER_ADDRESS')
			pincode, address_line1, address_line2 = None, None, None

			if address:
				for word in address.rsplit():
					if word.isdigit() and len(word) == 6:
						pincode = int(word)
				address_line1 = address[:n] if len(address) > 0 else None
				address_line2 = address[n:2*n] if len(address) > n else None

			lead_doc = frappe.new_doc('Lead')
			lead_doc.lead_name = lead_values.get('SENDER_NAME')
			lead_doc.email_id = email_id
			lead_doc.mobile_no = mobile_no
			lead_doc.source = "IndiaMart"
			lead_doc.organization_lead = organization_lead
			lead_doc.company_name = company_name
			lead_doc.notes_html = notes_html
			lead_doc.state = state
			lead_doc.country = country
			lead_doc.city = city or 'Not specified'
			lead_doc.query_id_cf = lead_values.get('UNIQUE_QUERY_ID')
			lead_doc.address_title = address_title
			lead_doc.address_type = address_type
			lead_doc.address_line1 = address_line1 or 'Not specified'
			lead_doc.address_line2 = address_line2
			lead_doc.pincode = pincode
			lead_doc.contact_by = ''
			lead_doc.lead_owner = lead_owner

			lead_doc.flags.ignore_mandatory = True
			lead_doc.flags.ignore_permissions = True
			lead_doc.insert()

			output = f'Lead {lead_doc.name} is created.'
			frappe.db.set_value('Indiamart Lead', indiamart_lead_name, 'output', output)
			frappe.db.set_value('Indiamart Lead', indiamart_lead_name, 'status', 'Completed')
			return output
		else:
			output = f'Duplicate Query_ID. It is in existing Lead {lead_name}'
			frappe.db.set_value('Indiamart Lead', indiamart_lead_name, 'output', output)
			frappe.db.set_value('Indiamart Lead', indiamart_lead_name, 'status', 'Completed')
			return output
	except Exception as e:
		title = _('Indiamart Error')
		separator = "--" * 50
		error = "\n".join([
        format_datetime(now_datetime(), 'd-MMM-y  HH:mm:ss'),
        "make_erpnext_lead_from_indiamart",
        f"indiamart_lead_name: {indiamart_lead_name}",
        str(e),
        separator,
        frappe.get_traceback()
    	])
		frappe.log_error(message=error, title=title)

def update_existing_lead(lead_name,lead_values):
		existing_lead_output=None
		lead_status = frappe.db.get_value('Lead', lead_name, 'status')

		if lead_status not in ['Converted','Quotation']:
			notes_html="<br><br><div><B>New Requirement</B></div><div>Product Name :{0}</div><div>Subject :{1}</div><div>Message :{2}</div><div>Lead Date :{3}</div><div>Alternate EmailID :{4}</div><div>Alternate Mobile :{5}</div><div>India Mart Query ID :{6}</div>" \
			.format( \
								frappe.bold(lead_values.get('QUERY_PRODUCT_NAME','Not specified')),
								frappe.bold(lead_values.get('SUBJECT','Not specified')),
								frappe.bold(lead_values.get('QUERY_MESSAGE','Not specified')),
								frappe.bold(lead_values.get('QUERY_TIME','Not specified')),
								frappe.bold(lead_values.get('EMAIL_ALT','Not specified')),
								frappe.bold(lead_values.get('MOBILE_ALT','Not specified')),
								frappe.bold(lead_values.get('UNIQUE_QUERY_ID','Not specified'))
								)

			lead=frappe.get_doc('Lead', lead_name)
			lead.reload()
			if lead.notes:
				lead.notes_html=lead.notes+notes_html
			else:
				lead.notes_html=notes_html
			lead.query_id_cf=lead_values.get('UNIQUE_QUERY_ID')
			lead.status='Lead'
			lead.flags.ignore_mandatory = True
			lead.flags.ignore_permissions = True
			lead.contact_date=''
			lead.contact_by=''
			lead.save()	
			existing_lead_output='Lead notes updated for {0}'.format(lead_name)
			return existing_lead_output	
		else:
			to_discuss_html="New Requirement \n Product Name : {0} \n Subject :{1} \n Message :{2} \n Lead Date :{3} \n Alternate EmailID :{4} \n Alternate Mobile :{5} \n India Mart Query ID :{6}" \
			.format( \
								frappe.bold(lead_values.get('QUERY_PRODUCT_NAME','Not specified')),
								frappe.bold(lead_values.get('SUBJECT','Not specified')),
								frappe.bold(lead_values.get('QUERY_MESSAGE','Not specified')),
								frappe.bold(lead_values.get('QUERY_TIME','Not specified')),
								frappe.bold(lead_values.get('EMAIL_ALT','Not specified')),
								frappe.bold(lead_values.get('MOBILE_ALT','Not specified')),
								frappe.bold(lead_values.get('UNIQUE_QUERY_ID','Not specified'))
								)

			opportunity=make_opportunity(source_name=lead_name)
			opportunity.flags.ignore_mandatory = True
			opportunity.flags.ignore_permissions = True
			opportunity.to_discuss=to_discuss_html
			opportunity.sales_stage= frappe.db.get_single_value('Indiamart Settings', 'default_opportunity_sales_stage')
			opportunity.save()			

			opportunity_html='<br><br><div><B>New Oppurtunity {0} was created</B>'.format(opportunity.name)
			lead=frappe.get_doc('Lead', lead_name)
			lead.reload()
			lead.query_id_cf=lead_values.get('UNIQUE_QUERY_ID')
			if lead.notes:
				lead.notes_html=lead.notes+opportunity_html
			else:
				lead.notes_html=opportunity_html
			lead.contact_date=''
			lead.contact_by=''
			lead.flags.ignore_mandatory = True
			lead.flags.ignore_permissions = True
			lead.save()		
			existing_lead_output='Opportunity is {0} created for Lead{1}'.format(opportunity.name,lead_name)
			return existing_lead_output			



def get_integration_request_dashboard_data(data):
	if len(data.get("transactions"))>0:
		for d in data.get("transactions",[]):
			d.update({"items":d.get("items") +["ToDo"]})
	else:
		data.get("transactions").append({"items":["ToDo"]})
	return data
