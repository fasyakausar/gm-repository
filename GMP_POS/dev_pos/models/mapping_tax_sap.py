from odoo import models, fields, api

class MappingTax(models.Model):
    _name = 'mapping.tax'
    _description = 'Mapping Tax'
    _rec_name = 'gm_warehouse_id'

    company_id = fields.Many2one(
        'res.company', string="Company",
        required=True,
        default=lambda self: self.env.company
    )
    gm_warehouse_id = fields.Many2one(
        'stock.warehouse', string="Warehouse",
        required=True,
        domain="[('company_id', '=', company_id)]"
    )
    gm_tax_code = fields.Many2one(
        'account.tax', string="Tax Code",
        domain="[('company_id', '=', company_id), ('type_tax_use', '=', 'sale')]"
    )
    gm_tax_code_0 = fields.Many2one(
        'account.tax', string="Tax Code 0",
        domain="[('company_id', '=', company_id), ('type_tax_use', '=', 'sale')]"
    )

    _sql_constraints = [
        ('warehouse_unique', 'UNIQUE(gm_warehouse_id)',
         'Mapping tax untuk warehouse ini sudah ada!')
    ]