# -*- coding: utf-8 -*-
from odoo import fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    receipt_design = fields.Many2one('pos.receipt', string='Receipt Design',
                                     help='Choose any receipt design')
    design_receipt = fields.Text(related='receipt_design.design_receipt',
                                 string='Receipt XML')
    logo = fields.Binary(related='company_id.logo', string='Logo',
                         readonly=False)
    is_custom_receipt = fields.Boolean(string='Is Custom Receipt',
                                       help='Indicates the receipt design is '
                                            'custom or not')

    # ── Logo ──────────────────────────────────────────────────────────────────
    receipt_show_logo   = fields.Boolean(string='Tampilkan Logo di Struk',
                                         default=True)
    receipt_logo_height = fields.Integer(string='Tinggi Logo (px)', default=60,
                                         help='Tinggi logo dalam pixel, misal: 60')

    # ── Bold per Section ──────────────────────────────────────────────────────
    receipt_bold_header    = fields.Boolean(string='Bold: Nama Toko & Alamat',
                                            default=True)
    receipt_bold_info      = fields.Boolean(string='Bold: Info Transaksi',
                                            default=True)
    receipt_bold_items     = fields.Boolean(string='Bold: Daftar Item',
                                            default=True)
    receipt_bold_total     = fields.Boolean(string='Bold: Total & Pembayaran',
                                            default=True)
    receipt_bold_summary   = fields.Boolean(string='Bold: Ringkasan & Footer',
                                            default=True)

    # ── Custom address fields ─────────────────────────────────────────────────
    receipt_store_name   = fields.Char(string='Nama Toko di Struk',
                                    help='Contoh: GMP Elektrik Lippo Cikarang')
    receipt_company_name = fields.Char(string='Nama Perusahaan di Struk',
                                    help='Contoh: PT GLOBAL MULTIPARTS')
    receipt_street       = fields.Char(string='Alamat',
                                    help='Contoh: Jl. Sriwijaya Ruko Olimpic Blok A.8 Cibatu')
    receipt_city_zip     = fields.Char(string='Kota & Kode Pos',
                                    help='Contoh: Lippo Cikarang 17550')
    receipt_phone        = fields.Char(string='Telepon (Tlp)',
                                    help='Contoh: (021) 89841952')
    receipt_wa           = fields.Char(string='WhatsApp (Wa)',
                                    help='Contoh: 0877-7909-0747')
    receipt_npwp         = fields.Char(string='NPWP',
                                    help='Contoh: 021.100.283.7-413.000')
    
    default_partner_id = fields.Many2one('res.partner', string="Select Customer")
    id_mc = fields.Char(string="ID MC", default=False)
    is_integrated = fields.Boolean(string="Integrated", tracking=True)
    is_updated = fields.Boolean(string="Updated", tracking=True)
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