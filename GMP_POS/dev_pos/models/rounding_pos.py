from odoo import models, fields, api
import json

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    # Auto Rounding Configuration
    enable_auto_rounding = fields.Boolean(
        "Enable Auto Rounding", 
        config_parameter="pos.enable_auto_rounding", 
        help="Enable automatic rounding when clicking payment button"
    )
    
    rounding_value = fields.Integer(
        string="Rounding Value", 
        config_parameter="pos.rounding_value",
        default=100,
        help="Value to round to (e.g., 100 for hundreds, 1000 for thousands)"
    )
    
    rounding_product_id = fields.Many2one(
        'product.product',
        string="Rounding Product",
        config_parameter="pos.rounding_product_id",
        help="Product used for rounding adjustment line"
    )

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        config = self.env['ir.config_parameter'].sudo()
        config.set_param('pos.rounding_product_id', self.rounding_product_id.id if self.rounding_product_id else False)

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        config = self.env['ir.config_parameter'].sudo()
        rounding_product_id = config.get_param('pos.rounding_product_id')
        res.update(
            rounding_product_id=int(rounding_product_id) if rounding_product_id and rounding_product_id.isdigit() else False,
        )
        return res
    
    @api.model
    def get_config_settings(self):
        try:
            config = self.env['ir.config_parameter'].sudo()
            manager_id = config.get_param('pos.manager_id')

            rounding_product_id = config.get_param('pos.rounding_product_id')
            rounding_product = self.env['product.product'].browse(int(rounding_product_id)) if rounding_product_id and rounding_product_id.isdigit() else None

            return {
                'enable_auto_rounding': config.get_param('pos.enable_auto_rounding') == 'True',
                'rounding_value': int(config.get_param('pos.rounding_value', 100)),
                'rounding_product_id': {
                    'id': rounding_product.id if rounding_product else None,
                    'name': rounding_product.name if rounding_product else None,
                } if rounding_product else None,
            }
        except Exception as e:
            return {'error': str(e)}