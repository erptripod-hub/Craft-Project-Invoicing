import frappe
from frappe.utils import flt


def on_submit(doc, method):
	if doc.items and doc.sales_order:
		so_doc = frappe.get_doc("Sales Order", doc.sales_order)
		if so_doc.enable_project_invoicing:
			retention_account = frappe.db.get_value(
				"Item Default", {"parent": "Retention", "company": doc.company}, "income_account")
			adv_account = frappe.db.get_value(
				"Item Default", {"parent": "Advance", "company": doc.company}, "income_account")

			# Post reverse journal entry for advance invoice
			if doc.items and len(doc.items) == 1 and doc.items[0].item_code == "Advance":
				if not adv_account:
					frappe.throw(
						title="Advance Account Not Found",
						msg="Deafult income account not found in item <b>Advance</b>"
					)
				adv_amount = doc.items[0].get("amount")
				if not doc.items[0].get("income_account") == adv_account:
					ge_doc = frappe.get_doc({
						"doctype": "Journal Entry",
						"voucher_type": "Journal Entry",
						"company": doc.company,
						"posting_date": doc.posting_date,
						"sales_order_reference": doc.sales_order
					})
					ge_doc.append("accounts", {
						"account": doc.items[0].get("income_account"),
						"debit_in_account_currency": adv_amount,
						"credit_in_account_currency": 0,
						"project": doc.project,
						"cost_center": doc.items[0].get("cost_center")
					})
					ge_doc.append("accounts", {
						"account": adv_account,
						"debit_in_account_currency": 0,
						"credit_in_account_currency": adv_amount,
						"project": doc.project,
						"cost_center": doc.items[0].get("cost_center")
					})
					ge_doc.insert(ignore_permissions=True,
								  ignore_mandatory=True)
					ge_doc.submit()
					doc.db_set("ref_journal_entry", ge_doc.name)

				so_doc.db_set({
					"advance_billed": 1,
					"advance_ref_doc": doc.name,
					"advance_billed_amount": adv_amount,
					# "remaining_advance": adv_amount
				})

			# Post reverse journal entry for on Retention invoice
			elif doc.items and len(doc.items) == 1 and doc.items[0].item_code == "Retention":
				if not retention_account:
					frappe.throw(
						title="Retention Account Not Found",
						msg="Deafult income account not found in item <b>Retention</b>"
					)
				ret_amount = doc.items[0].get("amount")
				if not doc.items[0].get("income_account") == retention_account:
					ge_doc = frappe.get_doc({
						"doctype": "Journal Entry",
						"voucher_type": "Journal Entry",
						"company": doc.company,
						"posting_date": doc.posting_date,
						"sales_order_reference": doc.sales_order
					})
					ge_doc.append("accounts", {
						"account": doc.items[0].get("income_account"),
						"debit_in_account_currency": ret_amount,
						"credit_in_account_currency": 0,
						"project": doc.project,
						"cost_center": doc.items[0].get("cost_center")
					})
					ge_doc.append("accounts", {
						"account": retention_account,
						"debit_in_account_currency": 0,
						"credit_in_account_currency": ret_amount,
						"project": doc.project,
						"cost_center": doc.items[0].get("cost_center")
					})
					ge_doc.insert(ignore_permissions=True,
								  ignore_mandatory=True)
					ge_doc.submit()
					doc.db_set("ref_journal_entry", ge_doc.name)

				so_doc.db_set({
					"retention_billed": 1,
					"retention_ref_doc": doc.name,
					"retention_billed_amount": ret_amount,
					# "remaining_retention": 0
				})

			# Post reverse journal entry for on multiple delivery invoices
			elif doc.items and len(doc.items) > 0:
				actual_delivery_amount = so_doc.base_net_total * \
					so_doc.on_delivery_percentage / 100
				so_doc.db_set("delivery_ref_doc", doc.name if not so_doc.delivery_ref_doc else (
					str(so_doc.delivery_ref_doc) + ", " + str(doc.name)))
				total = 0
				consumed_advance = 0
				# remaining_advance = 0
				consumed_retention = 0
				# remaining_retention = 0

				for t in doc.taxes:
					if t.is_advance and t.tax_amount:
						consumed_advance = so_doc.consumed_advance + \
							abs(t.tax_amount)
						# remaining_advance = so_doc.advance_billed_amount - (consumed_advance if consumed_advance else 0)
					elif t.is_retention and t.tax_amount:
						consumed_retention = so_doc.consumed_retention + \
							abs(t.tax_amount)
						# remaining_retention = (so_doc.base_net_total * (so_doc.retention_percentage/100)) - (consumed_retention if consumed_retention else 0)

					if t.is_advance or t.is_retention:
						total = total + t.tax_amount
				if actual_delivery_amount <= (float(so_doc.delivery_billed_amount if so_doc.delivery_billed_amount else 0) + doc.total + total):
					so_doc.db_set("on_delivery_billed", 1)
				so_doc.db_set({
					"delivery_billed_amount": so_doc.delivery_billed_amount + (doc.total + total),
					"consumed_advance": consumed_advance,
					"consumed_retention": consumed_retention,
					# "remaining_advance": remaining_advance,
					# "remaining_retention": remaining_retention
				})

def on_cancel(doc, method):
	invoice_type = {
		"Advance": "advance_billed",
		"Retention": "retention_billed"
	}
	invoice_references = {
		"Advance": "advance_ref_doc",
		"Retention": "retention_ref_doc"
	}
	billing_amounts = {
		"Advance": "advance_billed_amount",
		"Retention": "retention_billed_amount",
		"Delivery": "delivery_billed_amount"
	}
	if doc.ref_journal_entry:
		jv_doc_list = doc.ref_journal_entry.split(", ")
		for j in jv_doc_list:
			jv_doc = frappe.get_doc("Journal Entry", j)
			jv_doc.cancel()
	if doc.sales_order:
		so_doc = frappe.get_doc("Sales Order", doc.sales_order)
		if so_doc.enable_project_invoicing:
			delivery_ref_docs = None
			if doc.items and len(doc.items) == 1 and doc.items[0].item_code in ["Advance", "Retention"]:
				frappe.db.set_value("Sales Order", doc.sales_order, {
					invoice_type.get(doc.items[0].item_code): 0,
					invoice_references.get(doc.items[0].item_code): "",
					billing_amounts.get(doc.items[0].item_code): 0
				})
				if doc.items[0].item_code == "Retention":
					frappe.db.set_value("Sales Order", doc.sales_order, {
						"remaining_retention": float(so_doc.remaining_retention) - (doc.items[0].get("amount") if doc.items[0].get("amount") else 0)
					})
			elif doc.items and len(doc.items) > 0 and not doc.items[0].item_code in ["Advance", "Retention"]:
				frappe.db.set_value(
					"Sales Order", doc.sales_order, "on_delivery_billed", 0)
				delivery_ref_docs = frappe.db.get_value(
					"Sales Order", doc.sales_order, "delivery_ref_doc")

			if delivery_ref_docs:
				delivery_ref_doc_list = delivery_ref_docs.split(", ")
				delivery_ref_doc_list.remove(doc.name)
				frappe.db.set_value("Sales Order", doc.sales_order,
									"delivery_ref_doc", ", ".join(delivery_ref_doc_list))

				delivery_billed_amount = frappe.db.get_value(
					"Sales Order", doc.sales_order, "delivery_billed_amount")
				if delivery_billed_amount:
					total = 0
					consumed_advance = 0
					# remaining_advance = 0
					consumed_retention = 0
					# remaining_retention = 0
					for t in doc.taxes:
						if t.is_advance and t.tax_amount:
							consumed_advance = so_doc.consumed_advance - \
								abs(t.tax_amount)
							# remaining_advance = so_doc.advance_billed_amount - (consumed_advance if consumed_advance else 0)
						elif t.is_retention and t.tax_amount:
							consumed_retention = so_doc.consumed_retention - \
								abs(t.tax_amount)
							# remaining_retention = so_doc.retention_billed_amount - (consumed_retention if consumed_retention else 0)
						if t.is_advance or t.is_retention:
							total = total + t.tax_amount
					frappe.db.set_value("Sales Order", doc.sales_order, {
						billing_amounts.get("Delivery"): delivery_billed_amount - (doc.total + total),
						"consumed_advance": consumed_advance,
						"consumed_retention": consumed_retention,
						# "remaining_advance": remaining_advance,
						# "remaining_retention": remaining_retention
					})







# @frappe.whitelist()
# def get_so_detail(sales_order, invoice_per=None):
# 	if not sales_order:
# 		return

# 	if invoice_per and isinstance(invoice_per, str):
# 		invoice_per = flt(invoice_per)

# 	so_doc = frappe.get_doc("Sales Order", sales_order)
# 	so_details = {}
# 	if so_doc and so_doc.items:
# 		for item in so_doc.items:
# 			detail_dict = frappe._dict({
# 				"so_detail": item.name,
# 				"so_qty": item.qty,
# 				"qty": item.qty * (invoice_per/100) if invoice_per else None
# 			})
# 			so_details[item.name] = detail_dict

# 	return so_details if so_details else None


@frappe.whitelist()
def get_so_detail(sales_order, invoice_per=None, items=None):
    if not sales_order:
        return

    from frappe.utils import flt
    import json

    # Handle JSON and data types
    if invoice_per and isinstance(invoice_per, str):
        invoice_per = flt(invoice_per)
    if items and isinstance(items, str):
        items = json.loads(items)

    # Map each Sales Order Item → specific invoice percentage
    item_percentage_map = {}
    if items:
        for i in items:
            item_percentage_map[i.get("so_detail")] = flt(i.get("custom_invoice_percentage")) or invoice_per

    so_doc = frappe.get_doc("Sales Order", sales_order)
    so_details = {}

    for item in so_doc.items:
        item_invoice_per = item_percentage_map.get(item.name) or invoice_per
        if not item_invoice_per:
            continue

        so_details[item.name] = {
            "so_detail": item.name,
            "so_qty": item.qty,
            "qty": flt(item.qty) * (flt(item_invoice_per) / 100)
        }

    return so_details


def before_submit(doc, method):
    # 1️⃣ Skip if current invoice is for Advance
    if len(doc.items) == 1 and doc.items[0].item_code == "Advance":
        return

    # 2️⃣ Ensure linked Sales Order exists
    if not doc.sales_order:
        return

    # 3️⃣ Fetch all previously submitted invoices for the same Sales Order (excluding current)
    previous_invoices = frappe.get_all(
        "Sales Invoice",
        filters={
            "sales_order": doc.sales_order,
            "docstatus": 1,
            "name": ["!=", doc.name]
        },
        fields=["name", "custom_invoice_percentage", "grand_total"],
        order_by="posting_date asc, creation asc"  # oldest → newest
    )

    valid_invoices = []

    # 4️⃣ Filter out Advance invoices
    for inv in previous_invoices:
        inv_doc = frappe.get_doc("Sales Invoice", inv.name)
        if len(inv_doc.items) == 1 and inv_doc.items[0].item_code == "Advance":
            continue
        valid_invoices.append(inv_doc)  # store full doc for tax calculations

    # 5️⃣ Add valid invoices to child table
    if valid_invoices:
        doc.custom_sales_invoice_child = []  # clear existing rows

        for v in valid_invoices:
            # Calculate advance, retention, and VAT totals from taxes
            advance_total = 0
            retention_total = 0
            vat_total = 0

            for tax in v.taxes:
                is_advance = getattr(tax, "is_advance", 0)
                is_retention = getattr(tax, "is_retention", 0)

                if is_advance:
                    advance_total += abs(tax.tax_amount or 0)
                elif is_retention:
                    retention_total += abs(tax.tax_amount or 0)
                else:
                    vat_total += abs(tax.tax_amount or 0)

            # Append all required data to child table
            doc.append("custom_sales_invoice_child", {
                "sales_invoice": v.name,
                "previous_progress": v.custom_invoice_percentage or 0,
                "invoice_total": v.grand_total or 0,
                "advance_total": advance_total,
                "retention_total": retention_total,
                "vat_total": vat_total
            })

        frappe.msgprint(f"Added {len(valid_invoices)} previous invoice(s) details including tax info.")
    else:
        frappe.msgprint("No valid previous invoices found (only Advance invoices exist).")



# ---------------------------------------------------------------------------
# Sales Order billing percentage
#
# ERPNext computes Sales Order.per_billed by mapping each Sales Invoice Item
# back to a Sales Order Item via so_detail, and caps each line's billed_amt at
# that line's own amount. That model does not fit percentage / milestone
# invoicing, where a claim may sit on a single line (Advance, Retention) or on
# a line carrying zero value. The capped lines are discarded and the order
# under-reports how much has been billed.
#
# Here per_billed is derived from invoice totals instead:
#
#     per_billed = SUM(base_net_total of submitted Sales Invoices for the SO)
#                  / Sales Order.base_net_total * 100
#
# An invoice is considered linked to the order if either the header field
# `sales_order` points at it, or any of its item rows do. Each invoice is
# counted once regardless of how it was matched. Credit notes (is_return = 1)
# carry a negative base_net_total, so summing straight over them already nets
# the returned value back out of the total, which is correct.
#
# This mirrors the manual System Console routine used to backfill historical
# orders, so a document produces the same per_billed whether it is corrected
# in bulk or recalculated live here.
# ---------------------------------------------------------------------------


def get_linked_sales_orders(doc):
	"""Every Sales Order this invoice touches, via header or item links."""
	orders = set()
	if doc.get("sales_order"):
		orders.add(doc.get("sales_order"))
	for row in doc.get("items") or []:
		if row.get("sales_order"):
			orders.add(row.get("sales_order"))
	return orders


def get_invoiced_amount(sales_order):
	"""Total submitted invoice value linked to this Sales Order."""
	conditions = ["exists (select 1 from `tabSales Invoice Item` sii where sii.parent = si.name and sii.sales_order = %(so)s)"]

	# `sales_order` on Sales Invoice is a custom field owned by this app; guard
	# against it being absent so the hook cannot break invoice submission.
	if frappe.db.has_column("Sales Invoice", "sales_order"):
		conditions.insert(0, "si.sales_order = %(so)s")

	return frappe.db.sql(
		"""
		select ifnull(sum(si.base_net_total), 0)
		from `tabSales Invoice` si
		where si.docstatus = 1 and ({0})
		""".format(" or ".join(conditions)),
		{"so": sales_order},
	)[0][0] or 0


def recalculate_so_billing(sales_order):
	"""Recompute per_billed and billed_amt for one Sales Order."""
	so = frappe.db.get_value(
		"Sales Order", sales_order, ["name", "base_net_total", "docstatus"], as_dict=True
	)
	if not so or so.docstatus != 1 or not flt(so.base_net_total):
		return

	invoiced = flt(get_invoiced_amount(sales_order))

	item_total = frappe.db.sql(
		"select ifnull(sum(amount), 0) from `tabSales Order Item` where parent = %s",
		sales_order,
	)[0][0] or 0

	# Spread the invoiced value across the order lines in proportion to their
	# own value, so line-level reporting agrees with the header. Done in one
	# statement rather than per row; orders here can run to hundreds of lines.
	if flt(item_total):
		frappe.db.sql(
			"""
			update `tabSales Order Item`
			set billed_amt = round(amount / %(item_total)s * %(invoiced)s, 2)
			where parent = %(so)s
			""",
			{"item_total": flt(item_total), "invoiced": invoiced, "so": sales_order},
		)

	frappe.db.set_value(
		"Sales Order",
		sales_order,
		"per_billed",
		flt(invoiced / flt(so.base_net_total) * 100, 2),
		update_modified=False,
	)


def update_so_billing(doc, method=None):
	"""Hooked to Sales Invoice on_submit / on_cancel.

	Runs after ERPNext's own update_billing_status, overwriting the capped
	value with one derived from invoice totals.
	"""
	for sales_order in get_linked_sales_orders(doc):
		try:
			recalculate_so_billing(sales_order)
		except Exception:
			# Billing percentage is a reporting figure. It must never be the
			# reason an invoice fails to submit or cancel.
			frappe.log_error(
				title="Failed to update billing percentage for {0}".format(sales_order),
				message=frappe.get_traceback(),
			)
