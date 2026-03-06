# -*- coding: utf-8 -*-
import logging
from odoo import models

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _loader_params_product_product(self):
        result = super()._loader_params_product_product()
        result['search_params']['fields'].append('qty_available')
        return result

    def _loader_params_pos_receipt(self):
        return {
            'search_params': {
                'fields': ['design_receipt', 'name'],
            },
        }

    def _get_pos_ui_pos_receipt(self, params):
        return self.env['pos.receipt'].search_read(**params['search_params'])

    def load_pos_data(self):
        res = super().load_pos_data()

        # ✅ Load hr.employee untuk salesperson mapping
        res['hr_employee'] = self.env['hr.employee'].search_read(
            domain=[('is_sales', '=', True)],
            fields=['name', 'user_id'],
        )

        config = self.config_id

        # ✅ Inject custom address fields + logo + font + bold settings
        res['pos_receipt_address'] = {
            # ── address ──────────────────────────────────────────────────────
            'receipt_store_name':   config.receipt_store_name   or '',
            'receipt_company_name': config.receipt_company_name or '',
            'receipt_street':       config.receipt_street       or '',
            'receipt_city_zip':     config.receipt_city_zip     or '',
            'receipt_phone':        config.receipt_phone        or '',
            'receipt_wa':           config.receipt_wa           or '',
            'receipt_npwp':         config.receipt_npwp         or '',

            # ── logo ─────────────────────────────────────────────────────────
            'receipt_show_logo':   config.receipt_show_logo,
            'receipt_logo_height': config.receipt_logo_height or 60,
            # logo binary dikirim sebagai base64 data-uri agar bisa dipakai di template
            'receipt_logo_data':   config.logo.decode('utf-8') if config.logo else '',

            # ── bold per section ─────────────────────────────────────────────
            'receipt_bold_header':  config.receipt_bold_header,
            'receipt_bold_info':    config.receipt_bold_info,
            'receipt_bold_items':   config.receipt_bold_items,
            'receipt_bold_total':   config.receipt_bold_total,
            'receipt_bold_summary': config.receipt_bold_summary,
        }

        _logger.info("✅ [RECEIPT ADDRESS] Loaded: %s", res['pos_receipt_address'])

        return res