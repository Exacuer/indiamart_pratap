# Copyright (c) 2021, GreyCube Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.model.document import Document


class IndiamartSettings(Document):
	def validate(self):
		# Keep legacy field in sync for older code paths
		if self.get("default_prospect_owner"):
			self.default_lead_owner = self.default_prospect_owner
		elif self.get("default_lead_owner") and not self.get("default_prospect_owner"):
			self.default_prospect_owner = self.default_lead_owner

	def on_update(self):
		self.clear_cache()
