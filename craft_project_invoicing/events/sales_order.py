import frappe


def validate(doc, method):
	if doc.enable_project_invoicing and (doc.advance_percentage or doc.on_delivery_percentage or doc.retention_percentage):
		total = doc.advance_percentage or 0 + \
			doc.on_delivery_percentage or 0 + doc.retention_percentage or 0
		if total != 100:
			pass
			# frappe.throw(
			# 	title='Error',
			# 	msg='Total of Advance, On Delivery and Retention should be <b>100%</b>'
			# )
