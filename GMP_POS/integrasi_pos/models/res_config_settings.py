from odoo import models, fields, api
import json

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ── Manager Validation ───────────────────────────────────────────────────
    manager_validation = fields.Boolean(
        string="Manager Validation",
        related='pos_config_id.manager_validation',
        readonly=False,
        help="Enable manager validation for specific actions."
    )
    manager_id = fields.Many2one(
        'hr.employee',
        string="Manager",
        related='pos_config_id.manager_id',
        readonly=False,
        help="Select a manager for validation."
    )
    validate_closing_pos = fields.Boolean(
        string="Closing Of POS",
        related='pos_config_id.validate_closing_pos',
        readonly=False,
        help="Allow manager to validate closing POS."
    )
    validate_order_line_deletion = fields.Boolean(
        string="Void Item",
        related='pos_config_id.validate_order_line_deletion',
        readonly=False,
        help="Allow manager to validate order line deletions."
    )
    validate_discount = fields.Boolean(
        string="Apply Discount",
        related='pos_config_id.validate_discount',
        readonly=False,
        help="Allow manager to validate discount applications."
    )
    validate_price_change = fields.Boolean(
        string="Price Change",
        related='pos_config_id.validate_price_change',
        readonly=False,
        help="Allow manager to validate price changes."
    )
    validate_order_deletion = fields.Boolean(
        string="Order Deletion",
        related='pos_config_id.validate_order_deletion',
        readonly=False,
        help="Allow manager to validate order deletions."
    )
    validate_add_remove_quantity = fields.Boolean(
        string="Add/Remove Quantity",
        related='pos_config_id.validate_add_remove_quantity',
        readonly=False,
        help="Allow manager to validate adding/removing quantities."
    )
    validate_payment = fields.Boolean(
        string="Payment",
        related='pos_config_id.validate_payment',
        readonly=False,
        help="Allow manager to validate payments."
    )
    validate_end_shift = fields.Boolean(
        string="End Shift",
        related='pos_config_id.validate_end_shift',
        readonly=False,
        help="Allow manager to validate end of shift."
    )
    validate_refund = fields.Boolean(
        string="Refund",
        related='pos_config_id.validate_refund',
        readonly=False,
        help="Allow manager to validate refund."
    )
    validate_close_session = fields.Boolean(
        string="Close Session",
        related='pos_config_id.validate_close_session',
        readonly=False,
        help="Allow manager to close session."
    )
    validate_discount_amount = fields.Boolean(
        string="Discount Amount",
        related='pos_config_id.validate_discount_amount',
        readonly=False,
        help="Allow manager to validate discount amount."
    )
    validate_void_sales = fields.Boolean(
        string="Void Sales",
        related='pos_config_id.validate_void_sales',
        readonly=False,
        help="Allow manager to reset order."
    )
    validate_member_schedule = fields.Boolean(
        string="Member/Schedule",
        related='pos_config_id.validate_member_schedule',
        readonly=False,
        help="Allow manager to validate member schedule."
    )
    validate_prefix_customer = fields.Boolean(
        string="Prefix Customer",
        related='pos_config_id.validate_prefix_customer',
        readonly=False,
        help="Allow manager to change prefix customer."
    )
    validate_cash_drawer = fields.Boolean(
        string="Cash Drawer",
        related='pos_config_id.validate_cash_drawer',
        readonly=False,
        help="Allow manager to validate cash drawer."
    )
    validate_reprint_receipt = fields.Boolean(
        string="Reprint Receipt",
        related='pos_config_id.validate_reprint_receipt',
        readonly=False,
        help="Allow manager to reprint receipt."
    )
    validate_pricelist = fields.Boolean(
        string="Pricelist",
        related='pos_config_id.validate_pricelist',
        readonly=False,
        help="Allow manager to validate pricelist."
    )
    validate_discount_button = fields.Boolean(
        string="Discount Button",
        related='pos_config_id.validate_discount_button',
        readonly=False,
        help="Allow manager to validate discount button."
    )
    one_time_password = fields.Boolean(
        string="One Time Password for an Order",
        related='pos_config_id.one_time_password',
        readonly=False,
        help="Require OTP for every function."
    )
    allow_multiple_global_discounts = fields.Boolean(
        string="Allow Multiple Discounts",
        related='pos_config_id.allow_multiple_global_discounts',
        readonly=False,
        help="Allow applying multiple discount rewards in a single order. WARNING: This can result in very high total discounts."
    )

    # ── Barcode Scanner Configuration ────────────────────────────────────────
    # Barcode tetap global (bukan per-POS) karena hardware scanner
    # biasanya sama untuk semua POS dalam satu toko
    multiple_barcode_activate = fields.Boolean(
        string="Multiple Barcode Activation",
        config_parameter="pos.multiple_barcode_activate",
        help="Enable multiple barcode activation."
    )
    digit_awal = fields.Integer(
        string="Digit Awal",
        config_parameter="pos.digit_awal",
        help="Starting position for weight extraction"
    )
    digit_akhir = fields.Integer(
        string="Digit Akhir",
        config_parameter="pos.digit_akhir",
        help="Ending position for weight extraction"
    )
    prefix_timbangan = fields.Char(
        string="Prefix Timbangan",
        config_parameter="pos.prefix_timbangan",
        help="Prefix for weight barcode"
    )
    panjang_barcode = fields.Integer(
        string="Panjang Barcode",
        config_parameter="pos.panjang_barcode",
        help="Length of the barcode weight portion"
    )
    pricelist_configuration = fields.Boolean(
        string="Pricelist Configuration",
        config_parameter="pos.pricelist_configuration",
        help="Please Configure Your Needs for Pricelist."
    )

    # ── Reward Point Digits (tetap global) ───────────────────────────────────
    reward_point_total_digits = fields.Integer(
        string="Total Digit (Reward Point)",
        config_parameter="reward_point_total_digits",
        default=16,
        help="Jumlah total digit untuk field Reward Point."
    )
    reward_point_decimal_digits = fields.Integer(
        string="Digit Desimal (Reward Point)",
        config_parameter="reward_point_decimal_digits",
        default=4,
        help="Jumlah digit desimal untuk field Reward Point."
    )

    # ── Override set_values & get_values ─────────────────────────────────────
    # Tidak perlu override set_values/get_values untuk manager_id
    # karena sudah handled otomatis oleh related field ke pos_config_id

    @api.model
    def get_config_settings(self):
        """
        Method ini masih bisa dipakai jika ada kode lama yang memanggilnya,
        tapi sebaiknya diganti dengan membaca langsung dari pos.config.
        Sekarang membaca dari pos_config_id (POS yang aktif/pertama).
        """
        try:
            # Ambil POS config pertama yang aktif sebagai fallback
            pos_config = self.env['pos.config'].search([], limit=1)
            if not pos_config:
                return {'error': 'No POS configuration found'}

            manager = pos_config.manager_id

            return {
                'manager_validation': pos_config.manager_validation,
                'manager_id': {
                    'id': manager.id if manager else None,
                    'name': manager.name if manager else None,
                    'pin': manager.pin if manager and hasattr(manager, 'pin') else None,
                } if manager else None,
                'validate_closing_pos': pos_config.validate_closing_pos,
                'validate_order_line_deletion': pos_config.validate_order_line_deletion,
                'validate_discount': pos_config.validate_discount,
                'validate_price_change': pos_config.validate_price_change,
                'validate_order_deletion': pos_config.validate_order_deletion,
                'validate_add_remove_quantity': pos_config.validate_add_remove_quantity,
                'validate_payment': pos_config.validate_payment,
                'validate_end_shift': pos_config.validate_end_shift,
                'validate_refund': pos_config.validate_refund,
                'validate_close_session': pos_config.validate_close_session,
                'validate_void_sales': pos_config.validate_void_sales,
                'validate_member_schedule': pos_config.validate_member_schedule,
                'validate_prefix_customer': pos_config.validate_prefix_customer,
                'one_time_password': pos_config.one_time_password,
                'validate_discount_amount': pos_config.validate_discount_amount,
                'multiple_barcode_activate': self.env['ir.config_parameter'].sudo().get_param('pos.multiple_barcode_activate') == 'True',
                'validate_pricelist': pos_config.validate_pricelist,
                'validate_cash_drawer': pos_config.validate_cash_drawer,
                'validate_reprint_receipt': pos_config.validate_reprint_receipt,
                'validate_discount_button': pos_config.validate_discount_button,
                'pricelist_configuration': self.env['ir.config_parameter'].sudo().get_param('pos.pricelist_configuration') == 'True',
                'allow_multiple_global_discounts': pos_config.allow_multiple_global_discounts,
            }
        except Exception as e:
            return {'error': str(e)}