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

        # ✅ Inject custom address fields dari config_id langsung
        # Tidak menyentuh struktur res['pos.config'] agar tidak konflik
        config = self.config_id
        res['pos_receipt_address'] = {
            'receipt_store_name':   config.receipt_store_name   or '',
            'receipt_company_name': config.receipt_company_name or '',
            'receipt_street':       config.receipt_street       or '',
            'receipt_city_zip':     config.receipt_city_zip     or '',
            'receipt_phone':        config.receipt_phone        or '',
            'receipt_wa':           config.receipt_wa           or '',
            'receipt_npwp':         config.receipt_npwp         or '',
        }

        _logger.info("✅ [RECEIPT ADDRESS] Loaded: %s", res['pos_receipt_address'])

        return res