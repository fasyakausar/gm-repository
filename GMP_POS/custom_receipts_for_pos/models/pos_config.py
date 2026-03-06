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