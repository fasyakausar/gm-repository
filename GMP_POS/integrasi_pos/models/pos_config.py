# -*- coding: utf-8 -*-
from odoo import fields, models


class PosConfigInherit(models.Model):
    _inherit = 'pos.config'

    default_partner_id = fields.Many2one('res.partner', string="Select Customer")
    id_mc = fields.Char(string="ID MC", default=False)
    is_integrated = fields.Boolean(string="Integrated", tracking=True)
    is_updated = fields.Boolean(string="Updated", tracking=True)
    is_store = fields.Many2one('setting.config', string="Send Store")
    vit_trxid = fields.Char(string="Transaction ID", default=False)

    manager_validation = fields.Boolean("Manager Validation", default=False)
    manager_id = fields.Many2one('hr.employee', string="Manager")
    validate_closing_pos = fields.Boolean("Closing Of POS", default=False)
    validate_order_line_deletion = fields.Boolean("Void Item", default=False)
    validate_discount = fields.Boolean("Apply Discount", default=False)
    validate_price_change = fields.Boolean("Price Change", default=False)
    validate_order_deletion = fields.Boolean("Order Deletion", default=False)
    validate_add_remove_quantity = fields.Boolean("Add/Remove Quantity", default=False)
    validate_payment = fields.Boolean("Payment", default=False)
    validate_end_shift = fields.Boolean("End Shift", default=False)
    validate_refund = fields.Boolean("Refund", default=False)
    validate_close_session = fields.Boolean("Close Session", default=False)
    validate_discount_amount = fields.Boolean("Discount Amount", default=False)
    validate_void_sales = fields.Boolean("Void Sales", default=False)
    validate_member_schedule = fields.Boolean("Member/Schedule", default=False)
    validate_prefix_customer = fields.Boolean("Prefix Customer", default=False)
    validate_cash_drawer = fields.Boolean("Cash Drawer", default=False)
    validate_reprint_receipt = fields.Boolean("Reprint Receipt", default=False)
    validate_pricelist = fields.Boolean("Pricelist", default=False)
    validate_discount_button = fields.Boolean("Discount Button", default=False)
    one_time_password = fields.Boolean("One Time Password", default=False)
    allow_multiple_global_discounts = fields.Boolean("Allow Multiple Discounts", default=False)
    enable_auto_rounding = fields.Boolean("Auto Rounding", default=False)
    rounding_value = fields.Integer("Rounding Value", default=100)
    rounding_product_id = fields.Many2one('product.product', string="Rounding Product")