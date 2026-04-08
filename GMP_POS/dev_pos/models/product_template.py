from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class UomUom(models.Model):
    _inherit = 'uom.uom'

    @api.model
    def get_uom_id_from_identifier(self, identifier):
        """
        Mencari UOM berdasarkan identifier (string).
        Pencarian dilakukan pada field: name, code, symbol (case insensitive).
        Return ID UOM jika ditemukan, else False.
        """
        if not identifier:
            return False
        domain = [('name', '=ilike', identifier)]
        uom = self.sudo().search(domain, limit=1)
        return uom.id if uom else False


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # ==== FIELD TAMBAHAN ====
    is_integrated = fields.Boolean(string="Integrated", default=False)
    index_store = fields.Many2many('setting.config', string="Index Store")
    vit_sub_div = fields.Char(string="Sub Category")
    vit_item_kel = fields.Char(string="Kelompok")
    vit_item_type = fields.Char(string="Type")
    vit_is_discount = fields.Boolean(string="Discount")
    gm_is_fixed_price = fields.Boolean(string="Fixed Price?")
    gm_is_dp = fields.Boolean(string="Is DP?", help="Check this if this is a Down Payment product")
    gm_is_pelunasan = fields.Boolean(string="Is DP Pelunasan?", help="Check this if this is a Down Payment product")
    gm_is_dp_payment = fields.Boolean(string="Is DP Payment?", help="Check this if this is a Down Payment Payment product")
    gm_is_rounding = fields.Boolean(string="Is Rounding Product?", help="Check this if this is a Rounding Adjustment product (will not appear on receipt)")
    brand = fields.Char(string="Brand", tracking=True)
    gm_sub_category = fields.Char(string="Sub Category", tracking=True)
    gm_class = fields.Char(string="Class", tracking=True)
    gm_manufacturer = fields.Char(string="Manufacturer", tracking=True)

    # ==== OVERRIDE ====
    def _check_barcode_uniqueness(self):
        return True

    def _check_uom(self):
        if self.env.context.get('force_uom_update'):
            return True
        return super()._check_uom()

    def write(self, vals):
        # FORCE UPDATE UOM: bypass pengecekan stock moves jika context force_uom_update=True
        if 'uom_id' in vals and self.env.context.get('force_uom_update'):
            uom_val = vals.pop('uom_id')
            # Tulis field lainnya terlebih dahulu
            result = super(ProductTemplate, self).write(vals)
            # Update uom_id langsung ke database (tanpa melalui write() Odoo)
            for record in self:
                self.env.cr.execute(
                    "UPDATE product_template SET uom_id = %s WHERE id = %s",
                    (uom_val, record.id)
                )
                record.invalidate_recordset(['uom_id'])
            return result

        # ===== KODE ASLI ANDA DI BAWAH INI (tidak diubah) =====
        # Simpan nilai lama SEBELUM super().write() dipanggil
        old_values = {}
        for record in self:
            old_values[record.id] = {
                'list_price': record.list_price,
                'product_tag_ids': record.product_tag_ids.mapped('name'),
                'gm_is_dp': record.gm_is_dp,
                'gm_is_dp_payment': record.gm_is_dp_payment,
                'gm_is_pelunasan': record.gm_is_pelunasan,
                'gm_is_rounding': record.gm_is_rounding,
            }
        
        # Panggil super write
        result = super(ProductTemplate, self).write(vals)
        
        # Sync gm_is_dp ke product.product variants
        if 'gm_is_dp' in vals:
            for record in self:
                record.product_variant_ids.write({'gm_is_dp': vals['gm_is_dp']})
        
        if 'gm_is_dp_payment' in vals:
            for record in self:
                record.product_variant_ids.write({'gm_is_dp_payment': vals['gm_is_dp_payment']})
        
        if 'gm_is_pelunasan' in vals:
            for record in self:
                record.product_variant_ids.write({'gm_is_pelunasan': vals['gm_is_pelunasan']})
        
        if 'gm_is_rounding' in vals:
            for record in self:
                record.product_variant_ids.write({'gm_is_rounding': vals['gm_is_rounding']})
        
        # Log ke chatter
        for record in self:
            message_body = ""
            if 'list_price' in vals:
                old_price = old_values[record.id]['list_price']
                new_price = vals['list_price']
                message_body += f"Sales Price updated: {old_price} → To: {new_price}\n"
            
            if 'product_tag_ids' in vals:
                old_tags = old_values[record.id]['product_tag_ids']
                new_tags_operation = vals.get('product_tag_ids', [])
                new_tags = []
                for operation in new_tags_operation:
                    if operation[0] == 6:
                        new_tags = self.env['product.tag'].browse(operation[2]).mapped('name')
                    elif operation[0] == 4:
                        tag = self.env['product.tag'].browse(operation[1])
                        new_tags = list(set(old_tags + [tag.name]))
                    elif operation[0] == 3:
                        tag = self.env['product.tag'].browse(operation[1])
                        new_tags = [tag_name for tag_name in old_tags if tag_name != tag.name]
                    elif operation[0] == 5:
                        new_tags = []
                old_tags_str = ', '.join(old_tags) if old_tags else 'None'
                new_tags_str = ', '.join(new_tags) if new_tags else 'None'
                message_body += f"Product tags updated: Old Tags: {old_tags_str} → New Tags: {new_tags_str}"
            
            if 'gm_is_dp' in vals:
                message_body += f"\nIs DP? changed: {old_values[record.id]['gm_is_dp']} → {vals['gm_is_dp']}"
            if 'gm_is_dp_payment' in vals:
                message_body += f"\nIs DP Payment? changed: {old_values[record.id]['gm_is_dp_payment']} → {vals['gm_is_dp_payment']}"
            if 'gm_is_pelunasan' in vals:
                message_body += f"\nIs Pelunasan? changed: {old_values[record.id]['gm_is_pelunasan']} → {vals['gm_is_pelunasan']}"
            if 'gm_is_rounding' in vals:
                message_body += f"\nIs Rounding Product? changed: {old_values[record.id]['gm_is_rounding']} → {vals['gm_is_rounding']}"
            
            if message_body:
                record.message_post(body=message_body)
        
        return result

    @api.model
    def create(self, vals):
        record = super(ProductTemplate, self).create(vals)
        if 'gm_is_dp' in vals:
            record.product_variant_ids.write({'gm_is_dp': vals['gm_is_dp']})
        if 'gm_is_dp_payment' in vals:
            record.product_variant_ids.write({'gm_is_dp_payment': vals['gm_is_dp_payment']})
        if 'gm_is_pelunasan' in vals:
            record.product_variant_ids.write({'gm_is_pelunasan': vals['gm_is_pelunasan']})
        if 'gm_is_rounding' in vals:
            record.product_variant_ids.write({'gm_is_rounding': vals['gm_is_rounding']})
        
        message_body = "Product created with following information:\n"
        if 'list_price' in vals:
            message_body += f"- Sales Price: {vals['list_price']}\n"
        if 'product_tag_ids' in vals:
            tag_operations = vals.get('product_tag_ids', [])
            tag_names = []
            for operation in tag_operations:
                if operation[0] == 6:
                    tags = self.env['product.tag'].browse(operation[2])
                    tag_names = tags.mapped('name')
                elif operation[0] == 4:
                    tag = self.env['product.tag'].browse(operation[1])
                    tag_names.append(tag.name)
            if tag_names:
                message_body += f"- Tags: {', '.join(tag_names)}\n"
        if 'gm_is_dp' in vals:
            message_body += f"- Is DP?: {vals['gm_is_dp']}\n"
        if 'gm_is_dp_payment' in vals:
            message_body += f"- Is DP Payment?: {vals['gm_is_dp_payment']}\n"
        if 'gm_is_pelunasan' in vals:
            message_body += f"- Is Pelunasan?: {vals['gm_is_pelunasan']}\n"
        if 'gm_is_rounding' in vals:
            message_body += f"- Is Rounding Product?: {vals['gm_is_rounding']}\n"
        record.message_post(body=message_body)
        return record


class ProductProductInherit(models.Model):
    _inherit = 'product.product'

    vit_is_discount = fields.Boolean(string="Is Discount", default=False)
    gm_is_dp = fields.Boolean(string="Is DP?", help="This is a Down Payment product")
    gm_is_dp_payment = fields.Boolean(string="Is DP Payment?", help="This is a Down Payment Payment product")
    gm_is_pelunasan = fields.Boolean(string="Is DP Pelunasan?", help="This is a Down Payment Pelunasan product (will not appear on receipt)")
    gm_is_rounding = fields.Boolean(string="Is Rounding Product?", help="This is a Rounding Adjustment product (will not appear on receipt)")

    def _check_barcode_uniqueness(self):
        return True

    def _check_uom(self):
        if self.env.context.get('force_uom_update'):
            return True
        return super()._check_uom()