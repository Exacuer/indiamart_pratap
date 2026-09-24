# Copyright (c) 2026, GreyCube Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import json

import frappe
from frappe import _
from frappe.utils import cstr, format_datetime, now_datetime


# fieldname, label, fieldtype, IndiaMART source key, insert_after hint group
INDIAMART_PROSPECT_FIELDS = [
	("indiamart_section", "Indiamart Details", "Section Break", None),
	("query_id_cf", "Query ID", "Data", "UNIQUE_QUERY_ID"),
	("custom_query_type", "Query Type", "Data", "QUERY_TYPE"),
	("custom_query_time", "Query Time", "Data", "QUERY_TIME"),
	("custom_subject", "Subject", "Small Text", "SUBJECT"),
	("custom_query_product_name", "Product Name", "Small Text", "QUERY_PRODUCT_NAME"),
	("custom_query_mcat_name", "MCAT Name", "Data", "QUERY_MCAT_NAME"),
	("custom_sender_name", "Sender Name", "Data", "SENDER_NAME"),
	("custom_sender_company", "Sender Company", "Data", "SENDER_COMPANY"),
	("custom_sender_email", "Sender Email", "Data", "SENDER_EMAIL"),
	("custom_sender_email_alt", "Sender Email Alt", "Data", "SENDER_EMAIL_ALT"),
	("custom_sender_mobile", "Sender Mobile", "Data", "SENDER_MOBILE"),
	("custom_sender_mobile_alt", "Sender Mobile Alt", "Data", "SENDER_MOBILE_ALT"),
	("custom_sender_phone", "Sender Phone", "Data", "SENDER_PHONE"),
	("custom_sender_phone_alt", "Sender Phone Alt", "Data", "SENDER_PHONE_ALT"),
	("custom_sender_address", "Sender Address", "Small Text", "SENDER_ADDRESS"),
	("custom_sender_city", "Sender City", "Data", "SENDER_CITY"),
	("custom_sender_state", "Sender State", "Data", "SENDER_STATE"),
	("custom_sender_pincode", "Sender Pincode", "Data", "SENDER_PINCODE"),
	("custom_sender_country_iso", "Sender Country ISO", "Data", "SENDER_COUNTRY_ISO"),
	("custom_call_duration", "Call Duration", "Data", "CALL_DURATION"),
	("custom_receiver_mobile", "Receiver Mobile", "Data", "RECEIVER_MOBILE"),
	("custom_receiver_catalog", "Receiver Catalog", "Small Text", "RECEIVER_CATALOG"),
	("custom_query_message", "Query Message", "Text", "QUERY_MESSAGE"),
	("indiamart_payload_cf", "IndiaMART Payload", "Code", None),
]


def ensure_prospect_custom_fields():
	insert_after = "company"
	created_or_moved = False
	for fieldname, label, fieldtype, _source in INDIAMART_PROSPECT_FIELDS:
		existing_name = frappe.db.exists("Custom Field", {"dt": "Prospect", "fieldname": fieldname})
		if existing_name:
			# Keep Indiamart block under Overview (after Company), not under Comments
			current_after = frappe.db.get_value("Custom Field", existing_name, "insert_after")
			if fieldname == "indiamart_section" and current_after != "company":
				frappe.db.set_value("Custom Field", existing_name, "insert_after", "company")
				created_or_moved = True
			insert_after = fieldname
			continue

		doc = frappe.get_doc(
			{
				"doctype": "Custom Field",
				"dt": "Prospect",
				"fieldname": fieldname,
				"label": label,
				"fieldtype": fieldtype,
				"insert_after": insert_after,
				"read_only": 1,
				"collapsible": 1 if fieldtype == "Section Break" else 0,
				"options": "JSON" if fieldname == "indiamart_payload_cf" else None,
			}
		)
		doc.insert(ignore_permissions=True)
		insert_after = fieldname
		created_or_moved = True

	if created_or_moved:
		frappe.clear_cache(doctype="Prospect")
		frappe.db.commit()


def ensure_indiamart_lead_prospect_column():
	columns = frappe.db.get_table_columns("Indiamart Lead")
	if "prospect" in columns:
		return

	frappe.reload_doctype("Indiamart Lead", force=True)
	columns = frappe.db.get_table_columns("Indiamart Lead")
	if "prospect" in columns:
		return

	frappe.db.sql("ALTER TABLE `tabIndiamart Lead` ADD COLUMN `prospect` varchar(140)")
	frappe.clear_cache(doctype="Indiamart Lead")


def get_prospect_owner():
	settings = frappe.get_cached_doc("Indiamart Settings")
	return (
		settings.get("default_prospect_owner")
		or settings.get("default_lead_owner")
		or frappe.session.user
	)


def get_default_company():
	settings = frappe.get_cached_doc("Indiamart Settings")
	return (
		settings.get("default_company")
		or frappe.defaults.get_user_default("Company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
	)


def make_erpnext_prospect_from_indiamart(lead_values, indiamart_lead_name=None):
	try:
		ensure_prospect_custom_fields()
		ensure_indiamart_lead_prospect_column()
		lead_values = lead_values or {}
		query_id = cstr(lead_values.get("UNIQUE_QUERY_ID")).strip()
		company_name = _prospect_company_name(lead_values)
		note_html = _enquiry_note(lead_values)

		prospect_name = None
		if query_id and frappe.get_meta("Prospect").has_field("query_id_cf"):
			prospect_name = frappe.db.get_value("Prospect", {"query_id_cf": query_id})
		if not prospect_name:
			prospect_name = frappe.db.get_value("Prospect", {"company_name": company_name})

		if prospect_name:
			_update_existing_prospect(prospect_name, lead_values, note_html)
			output = _("Enquiry added to existing Prospect {0}").format(prospect_name)
		else:
			prospect_name = _create_prospect(lead_values, company_name, note_html)
			output = _("Prospect {0} is created.").format(prospect_name)

		_link_indiamart_lead(indiamart_lead_name, prospect_name, output, "Completed")
		return output
	except Exception as e:
		_handle_prospect_error(indiamart_lead_name, e)
		return None


def _prospect_company_name(lead_values):
	company_name = cstr(lead_values.get("SENDER_COMPANY")).strip()
	sender_name = cstr(lead_values.get("SENDER_NAME")).strip()
	query_id = cstr(lead_values.get("UNIQUE_QUERY_ID")).strip()
	if company_name:
		return company_name
	if sender_name and query_id:
		return "{0} - {1}".format(sender_name, query_id)
	return sender_name or "IndiaMART {0}".format(query_id or now_datetime())


def _enquiry_note(lead_values):
	important = [
		("UNIQUE_QUERY_ID", "Query ID"),
		("QUERY_TYPE", "Query Type"),
		("QUERY_TIME", "Query Time"),
		("SUBJECT", "Subject"),
		("QUERY_PRODUCT_NAME", "Product"),
		("QUERY_MCAT_NAME", "Category"),
		("QUERY_MESSAGE", "Message"),
		("SENDER_NAME", "Sender"),
		("SENDER_COMPANY", "Company"),
		("SENDER_EMAIL", "Email"),
		("SENDER_MOBILE", "Mobile"),
		("SENDER_PHONE", "Phone"),
		("SENDER_ADDRESS", "Address"),
		("SENDER_CITY", "City"),
		("SENDER_STATE", "State"),
		("SENDER_PINCODE", "Pincode"),
	]
	rows = []
	for key, label in important:
		value = lead_values.get(key)
		if value not in (None, ""):
			rows.append("<div>{0}: {1}</div>".format(frappe.bold(label), cstr(value)))
	return "\n".join(rows) or "<div>No IndiaMART details received.</div>"


def _apply_indiamart_fields(doc, lead_values):
	meta = frappe.get_meta("Prospect")
	if meta.has_field("indiamart_payload_cf"):
		doc.indiamart_payload_cf = json.dumps(lead_values, indent=2, ensure_ascii=False)

	for fieldname, _label, fieldtype, source_key in INDIAMART_PROSPECT_FIELDS:
		if not source_key or not meta.has_field(fieldname):
			continue
		value = lead_values.get(source_key)
		if value in (None, ""):
			continue
		text = cstr(value)
		if fieldname == "custom_query_message":
			doc.set(fieldname, text[:10000])
		elif fieldtype == "Data":
			doc.set(fieldname, text[:140])
		else:
			doc.set(fieldname, text)

	# Standard Prospect fields
	website = cstr(lead_values.get("RECEIVER_CATALOG")).strip()
	if website and not doc.website:
		doc.website = website[:140]

	territory = _resolve_territory(lead_values)
	if territory:
		doc.territory = territory

	settings = frappe.get_cached_doc("Indiamart Settings")
	if settings.get("default_customer_group") and not doc.customer_group:
		doc.customer_group = settings.default_customer_group

	owner = get_prospect_owner()
	if owner and not doc.prospect_owner:
		doc.prospect_owner = owner


def _resolve_territory(lead_values):
	settings = frappe.get_cached_doc("Indiamart Settings")
	state = cstr(lead_values.get("SENDER_STATE")).strip()
	city = cstr(lead_values.get("SENDER_CITY")).strip()

	for candidate in (state, city):
		if candidate and frappe.db.exists("Territory", candidate):
			return candidate

	if state:
		match = frappe.db.get_value("Territory", {"territory_name": ["like", "%{0}%".format(state)]}, "name")
		if match:
			return match

	return settings.get("default_territory")


def _create_prospect(lead_values, company_name, note_html):
	company = get_default_company()
	if not company:
		frappe.throw(_("Please set Default Company in Indiamart Settings (or Global Defaults)."))

	prospect = frappe.new_doc("Prospect")
	prospect.company_name = company_name
	prospect.company = company
	prospect.prospect_owner = get_prospect_owner()
	_apply_indiamart_fields(prospect, lead_values)
	prospect.append(
		"notes",
		{
			"note": note_html,
			"added_by": frappe.session.user,
			"added_on": now_datetime(),
		},
	)
	prospect.flags.ignore_mandatory = True
	prospect.flags.ignore_permissions = True
	prospect.insert()
	_create_prospect_contact(prospect.name, lead_values)
	return prospect.name


def _update_existing_prospect(prospect_name, lead_values, note_html):
	prospect = frappe.get_doc("Prospect", prospect_name)
	_apply_indiamart_fields(prospect, lead_values)
	prospect.append(
		"notes",
		{
			"note": note_html,
			"added_by": frappe.session.user,
			"added_on": now_datetime(),
		},
	)
	prospect.flags.ignore_mandatory = True
	prospect.flags.ignore_permissions = True
	prospect.save()
	_create_prospect_contact(prospect.name, lead_values)


def _existing_linked_docs(prospect_name, parenttype):
	return frappe.get_all(
		"Dynamic Link",
		filters={
			"link_doctype": "Prospect",
			"link_name": prospect_name,
			"parenttype": parenttype,
		},
		pluck="parent",
	)


def _create_prospect_contact(prospect_name, lead_values):
	sender_name = cstr(lead_values.get("SENDER_NAME") or prospect_name).strip()
	emails = [
		cstr(lead_values.get("SENDER_EMAIL")).strip(),
		cstr(lead_values.get("SENDER_EMAIL_ALT")).strip(),
	]
	phones = [
		(cstr(lead_values.get("SENDER_MOBILE")).strip(), True),
		(cstr(lead_values.get("SENDER_MOBILE_ALT")).strip(), True),
		(cstr(lead_values.get("SENDER_PHONE")).strip(), False),
		(cstr(lead_values.get("SENDER_PHONE_ALT")).strip(), False),
	]
	emails = [e for e in emails if e]
	phones = [p for p in phones if p[0]]

	if not emails and not phones:
		return

	try:
		existing_contacts = _existing_linked_docs(prospect_name, "Contact")
		if existing_contacts:
			contact = frappe.get_doc("Contact", existing_contacts[0])
			_sync_contact_details(contact, emails, phones)
			return

		contact = frappe.new_doc("Contact")
		parts = sender_name.split(None, 1)
		contact.first_name = parts[0][:140]
		if len(parts) > 1:
			contact.last_name = parts[1][:140]
		for idx, email_id in enumerate(emails):
			contact.append("email_ids", {"email_id": email_id, "is_primary": 1 if idx == 0 else 0})
		mobile_set = False
		phone_set = False
		for phone, is_mobile in phones:
			row = {"phone": phone}
			if is_mobile and not mobile_set:
				row["is_primary_mobile_no"] = 1
				mobile_set = True
			elif not is_mobile and not phone_set:
				row["is_primary_phone"] = 1
				phone_set = True
			contact.append("phone_nos", row)
		contact.append("links", {"link_doctype": "Prospect", "link_name": prospect_name})
		contact.flags.ignore_mandatory = True
		contact.flags.ignore_permissions = True
		contact.insert()
	except Exception:
		frappe.log_error(title=_("Indiamart Contact Error"), message=frappe.get_traceback())


def _sync_contact_details(contact, emails, phones):
	existing_emails = {cstr(d.email_id).lower() for d in contact.email_ids}
	for idx, email_id in enumerate(emails):
		if email_id.lower() not in existing_emails:
			contact.append(
				"email_ids",
				{"email_id": email_id, "is_primary": 1 if not contact.email_ids and idx == 0 else 0},
			)

	existing_phones = {cstr(d.phone) for d in contact.phone_nos}
	for phone, is_mobile in phones:
		if phone in existing_phones:
			continue
		row = {"phone": phone}
		if is_mobile:
			row["is_primary_mobile_no"] = 0 if any(d.is_primary_mobile_no for d in contact.phone_nos) else 1
		else:
			row["is_primary_phone"] = 0 if any(d.is_primary_phone for d in contact.phone_nos) else 1
		contact.append("phone_nos", row)

	contact.flags.ignore_mandatory = True
	contact.flags.ignore_permissions = True
	contact.save()


def _link_indiamart_lead(indiamart_lead_name, prospect_name, output, status):
	if not indiamart_lead_name:
		return
	values = {"output": output, "status": status}
	if "prospect" in frappe.db.get_table_columns("Indiamart Lead"):
		values["prospect"] = prospect_name
	frappe.db.set_value("Indiamart Lead", indiamart_lead_name, values)


def _handle_prospect_error(indiamart_lead_name, error):
	title = _("Indiamart Error")
	separator = "--" * 50
	message = "\n".join(
		[
			format_datetime(now_datetime(), "d-MMM-y  HH:mm:ss"),
			"make_erpnext_prospect_from_indiamart",
			"indiamart_lead_name: {0}".format(indiamart_lead_name),
			str(error),
			separator,
			frappe.get_traceback(),
		]
	)
	frappe.log_error(message=message, title=title)
	if indiamart_lead_name:
		frappe.db.set_value(
			"Indiamart Lead",
			indiamart_lead_name,
			{"status": "Failed", "output": str(error)[:140]},
		)
