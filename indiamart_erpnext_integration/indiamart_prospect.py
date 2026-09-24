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

	cf_name = frappe.db.exists("Custom Field", {"dt": "Prospect", "fieldname": "custom_customer_source"})
	if not cf_name:
		frappe.get_doc(
			{
				"doctype": "Custom Field",
				"dt": "Prospect",
				"fieldname": "custom_customer_source",
				"label": "Customer Source",
				"fieldtype": "Link",
				"options": "Lead Source",
				"insert_after": "prospect_owner",
				"in_list_view": 1,
				"in_standard_filter": 1,
			}
		).insert(ignore_permissions=True)
		created_or_moved = True
	else:
		# Ensure Customer Source is a Link to Lead Source (older installs used Data).
		# Fieldtype change Data→Link is blocked by Custom Field.validate — update via DB.
		cf = frappe.db.get_value(
			"Custom Field",
			cf_name,
			["fieldtype", "options"],
			as_dict=True,
		)
		if cf and (cf.fieldtype != "Link" or cf.options != "Lead Source"):
			frappe.db.set_value(
				"Custom Field",
				cf_name,
				{"fieldtype": "Link", "options": "Lead Source"},
				update_modified=False,
			)
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


def ensure_lead_source(name):
	"""Return the actual Lead Source name (handles MySQL case-insensitive match)."""
	name = cstr(name).strip()
	if not name:
		return ""

	# Return canonical DB name (MySQL collation treats IndiaMART == IndiaMart)
	row = frappe.db.sql(
		"SELECT name FROM `tabLead Source` WHERE LOWER(name) = %s LIMIT 1",
		(name.lower(),),
	)
	if row:
		return row[0][0]

	doc = frappe.get_doc({"doctype": "Lead Source", "source_name": name})
	doc.insert(ignore_permissions=True)
	return doc.name


def get_customer_source():
	settings = frappe.get_cached_doc("Indiamart Settings")
	source = cstr(settings.get("default_customer_source")).strip() or "IndiaMart"
	return ensure_lead_source(source)


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

	if frappe.get_meta("Prospect").has_field("custom_customer_source"):
		doc.custom_customer_source = get_customer_source()

	# Overview Contact Person / Mobile / Email (pratap custom fields)
	_apply_overview_contact_fields(doc, lead_values)
	_apply_overview_location_fields(doc, lead_values)


def _normalize_phone(raw):
	"""Normalize to Frappe Phone control format: +91-XXXXXXXXXX (exactly one hyphen)."""
	raw = cstr(raw).strip()
	if not raw:
		return ""

	digits = "".join(ch for ch in raw if ch.isdigit())
	if not digits:
		return ""

	# Strip leading country code 91 when present
	if digits.startswith("91") and len(digits) > 10:
		digits = digits[2:]

	# Prefer last 10 digits (Indian mobile / phone)
	if len(digits) >= 10:
		digits = digits[-10:]
		return "+91-{0}".format(digits)

	return ""


def _safe_phone(raw):
	"""Return a Frappe-valid phone, or empty string if missing / invalid."""
	from frappe.utils import validate_phone_number

	raw = cstr(raw).strip()
	if not raw:
		return ""

	normalized = _normalize_phone(raw)
	if not normalized:
		return ""

	try:
		if validate_phone_number(normalized, throw=False):
			return normalized
	except Exception:
		pass
	return ""


def _collect_phones(lead_values):
	"""Return (valid [(phone, is_mobile), ...], invalid [raw, ...])."""
	candidates = [
		(lead_values.get("SENDER_MOBILE"), True),
		(lead_values.get("SENDER_MOBILE_ALT"), True),
		(lead_values.get("SENDER_PHONE"), False),
		(lead_values.get("SENDER_PHONE_ALT"), False),
	]
	valid = []
	invalid = []
	seen = set()
	for raw, is_mobile in candidates:
		raw = cstr(raw).strip()
		if not raw:
			continue
		phone = _safe_phone(raw)
		if not phone:
			if raw not in invalid:
				invalid.append(raw)
			continue
		if phone in seen:
			continue
		seen.add(phone)
		valid.append((phone, is_mobile))
	return valid, invalid


def _add_invalid_phone_comment(prospect_name, invalid_phones):
	"""Record skipped invalid phones on Prospect without blocking create."""
	if not prospect_name or not invalid_phones:
		return
	try:
		text = _("Invalid phone number(s) from IndiaMART (skipped): {0}").format(
			", ".join(frappe.utils.escape_html(p) for p in invalid_phones)
		)
		prospect = frappe.get_doc("Prospect", prospect_name)
		prospect.add_comment("Comment", text=text)
		prospect.append(
			"notes",
			{
				"note": "<div>{0}</div>".format(text),
				"added_by": frappe.session.user,
				"added_on": now_datetime(),
			},
		)
		prospect.flags.ignore_mandatory = True
		prospect.flags.ignore_permissions = True
		prospect.save()
	except Exception:
		frappe.log_error(title=_("Indiamart Invalid Phone Comment Error"), message=frappe.get_traceback())


def _apply_overview_contact_fields(doc, lead_values):
	"""Fill Prospect Overview fields used on Desk (not only Indiamart custom_* sender fields)."""
	from frappe.utils import validate_email_address

	meta = frappe.get_meta("Prospect")
	sender_name = cstr(lead_values.get("SENDER_NAME")).strip()
	email = cstr(lead_values.get("SENDER_EMAIL")).strip() or cstr(lead_values.get("SENDER_EMAIL_ALT")).strip()
	valid_phones, _invalid = _collect_phones(lead_values)
	mobile = valid_phones[0][0] if valid_phones else ""
	company_name = cstr(lead_values.get("SENDER_COMPANY")).strip() or cstr(doc.company_name).strip()

	if meta.has_field("custom_contact_person") and sender_name:
		doc.custom_contact_person = sender_name[:140]
	if meta.has_field("custom_email") and email:
		try:
			validate_email_address(email, throw=True)
			doc.custom_email = email[:140]
		except Exception:
			# Keep Indiamart custom_sender_email; skip Overview Email if invalid
			pass
	if meta.has_field("custom_mobile_no") and mobile:
		doc.custom_mobile_no = mobile
	if meta.has_field("custom_customer_name") and company_name and not doc.get("custom_customer_name"):
		doc.custom_customer_name = company_name[:140]


def _apply_overview_location_fields(doc, lead_values):
	"""Fill Address & Contact tab location links from IndiaMART / Pincode master."""
	meta = frappe.get_meta("Prospect")
	city = cstr(lead_values.get("SENDER_CITY")).strip()
	state = cstr(lead_values.get("SENDER_STATE")).strip()
	pincode = cstr(lead_values.get("SENDER_PINCODE")).strip()
	country_iso = cstr(lead_values.get("SENDER_COUNTRY_ISO")).strip().upper()
	country = "India" if country_iso in ("", "IN") else (frappe.db.get_value("Country", {"code": country_iso}, "name") or "India")

	# Prefer Pincode master (has city / territory / country)
	pin_row = None
	if pincode and frappe.db.exists("DocType", "Pincode") and frappe.db.exists("Pincode", pincode):
		pin_row = frappe.db.get_value(
			"Pincode",
			pincode,
			["city", "territiry", "country"],
			as_dict=True,
		)

	if meta.has_field("custom_country"):
		doc.custom_country = (pin_row.country if pin_row and pin_row.country else country) or "India"

	if meta.has_field("custom_postalcode") and pincode and frappe.db.exists("Pincode", pincode):
		doc.custom_postalcode = pincode

	resolved_city = (pin_row.city if pin_row and pin_row.city else city) or ""
	if meta.has_field("custom_city_territory") and resolved_city:
		if frappe.db.exists("Cities", resolved_city):
			doc.custom_city_territory = resolved_city
		else:
			match = frappe.db.get_value("Cities", {"city": ["like", "%{0}%".format(resolved_city)]}, "name")
			if match:
				doc.custom_city_territory = match

	resolved_state = (pin_row.territiry if pin_row and pin_row.territiry else state) or ""
	if meta.has_field("custom_territory_state") and resolved_state:
		if frappe.db.exists("Territory", resolved_state):
			doc.custom_territory_state = resolved_state
		else:
			match = frappe.db.get_value(
				"Territory",
				{"territory_name": ["like", "%{0}%".format(resolved_state)]},
				"name",
			)
			if match:
				doc.custom_territory_state = match
				resolved_state = match

	if meta.has_field("custom_region") and doc.get("custom_territory_state"):
		region = frappe.db.get_value("Territory", doc.custom_territory_state, "custom_region")
		if region:
			doc.custom_region = region


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
	_, invalid_phones = _collect_phones(lead_values)
	_add_invalid_phone_comment(prospect.name, invalid_phones)
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
	_, invalid_phones = _collect_phones(lead_values)
	_add_invalid_phone_comment(prospect.name, invalid_phones)


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
	emails = [e for e in emails if e]
	phones, _invalid = _collect_phones(lead_values)

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
			if not phone or not cstr(phone).strip():
				continue
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
		if not phone or not cstr(phone).strip() or phone in existing_phones:
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
