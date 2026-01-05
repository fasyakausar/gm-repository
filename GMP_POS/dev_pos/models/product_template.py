from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)
  

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_integrated = fields.Boolean(string="Integrated", default=False)
    index_store = fields.Many2many('setting.config', string="Index Store")
    vit_sub_div = fields.Char(string="Sub Category")
    vit_item_kel = fields.Char(string="Kelompok")
    vit_item_type = fields.Char(string="Type")
    vit_is_discount = fields.Boolean(string="Discount")
    gm_is_dp = fields.Boolean(
        string="Is DP?",
        help="Check this if this is a Down Payment product"
    )
    gm_is_pelunasan = fields.Boolean(
        string="Is DP Pelunasan?",
        help="Check this if this is a Down Payment product"
    )
    gm_is_dp_payment = fields.Boolean(
        string="Is DP Payment?",
        help="Check this if this is a Down Payment Payment product"
    )
    brand = fields.Char(string="Brand", tracking=True)

    def _check_barcode_uniqueness(self):
        # Override untuk mematikan validasi barcode unik
        # Tidak akan pernah raise ValidationError lagi walaupun ada duplikat
        return True

    def write(self, vals):
        # Field-field yang readonly - tidak boleh diubah
        # readonly_fields = [
        #     'id_mc', 'vit_sub_div', 'vit_item_kel', 'vit_item_type', 'is_fixed_price', 'brand',
        #     'categ_id', 'standard_price', 'sale_ok', 'purchase_ok', 
        #     'taxes_id', 'detailed_type', 'invoice_policy', 'uom_id', 'uom_po_id'
        # ]
        
        # # Cek jika ada field readonly yang mencoba diubah
        # for field in readonly_fields:
        #     if field in vals:
        #         raise UserError(f"Cannot modify field '{self._fields[field].string}' as it is read-only.")
        
        # Simpan nilai lama SEBELUM super().write() dipanggil
        old_values = {}
        for record in self:
            old_values[record.id] = {
                'list_price': record.list_price,
                'product_tag_ids': record.product_tag_ids.mapped('name'),
                'gm_is_dp': record.gm_is_dp,
                'gm_is_dp_payment': record.gm_is_dp_payment,
            }
        
        # Panggil super write
        result = super(ProductTemplate, self).write(vals)
        
        # Sync gm_is_dp ke product.product variants
        if 'gm_is_dp' in vals:
            for record in self:
                # Update all variants of this template
                record.product_variant_ids.write({'gm_is_dp': vals['gm_is_dp']})
        
        # Sync gm_is_dp_payment ke product.product variants
        if 'gm_is_dp_payment' in vals:
            for record in self:
                # Update all variants of this template
                record.product_variant_ids.write({'gm_is_dp_payment': vals['gm_is_dp_payment']})
        
        # Log ke chatter untuk list_price dan product_tag_ids
        for record in self:
            message_body = ""
            
            # Log untuk list_price
            if 'list_price' in vals:
                old_price = old_values[record.id]['list_price']
                new_price = vals['list_price']
                message_body += f"Sales Price updated: {old_price} → To: {new_price}\n"
            
            # Log untuk product_tag_ids
            if 'product_tag_ids' in vals:
                old_tags = old_values[record.id]['product_tag_ids']
                new_tags_operation = vals.get('product_tag_ids', [])
                
                # Process the operation to get new tags
                new_tags = []
                for operation in new_tags_operation:
                    if operation[0] == 6:  # REPLACE
                        new_tags = self.env['product.tag'].browse(operation[2]).mapped('name')
                    elif operation[0] == 4:  # ADD
                        tag = self.env['product.tag'].browse(operation[1])
                        new_tags = list(set(old_tags + [tag.name]))
                    elif operation[0] == 3:  # REMOVE
                        tag = self.env['product.tag'].browse(operation[1])
                        new_tags = [tag_name for tag_name in old_tags if tag_name != tag.name]
                    elif operation[0] == 5:  # CLEAR ALL
                        new_tags = []
                
                old_tags_str = ', '.join(old_tags) if old_tags else 'None'
                new_tags_str = ', '.join(new_tags) if new_tags else 'None'
                message_body += f"Product tags updated: Old Tags: {old_tags_str} → New Tags: {new_tags_str}"
            
            # Log untuk gm_is_dp
            if 'gm_is_dp' in vals:
                old_dp = old_values[record.id]['gm_is_dp']
                new_dp = vals['gm_is_dp']
                message_body += f"\nIs DP? changed: {old_dp} → {new_dp}"
            
            # Log untuk gm_is_dp_payment
            if 'gm_is_dp_payment' in vals:
                old_dp_payment = old_values[record.id]['gm_is_dp_payment']
                new_dp_payment = vals['gm_is_dp_payment']
                message_body += f"\nIs DP Payment? changed: {old_dp_payment} → {new_dp_payment}"
            
            # Post message ke chatter jika ada perubahan
            if message_body:
                record.message_post(body=message_body)
        
        return result

    @api.model
    def create(self, vals):
        # Untuk create, log informasi ke chatter
        record = super(ProductTemplate, self).create(vals)
        
        # Sync gm_is_dp ke product.product variants saat create
        if 'gm_is_dp' in vals:
            record.product_variant_ids.write({'gm_is_dp': vals['gm_is_dp']})
        
        # Sync gm_is_dp_payment ke product.product variants saat create
        if 'gm_is_dp_payment' in vals:
            record.product_variant_ids.write({'gm_is_dp_payment': vals['gm_is_dp_payment']})
        
        message_body = "Product created with following information:\n"
        
        # Log list_price jika ada
        if 'list_price' in vals:
            message_body += f"- Sales Price: {vals['list_price']}\n"
        
        # Log product tags jika ada
        if 'product_tag_ids' in vals:
            tag_operations = vals.get('product_tag_ids', [])
            tag_names = []
            for operation in tag_operations:
                if operation[0] == 6:  # REPLACE
                    tags = self.env['product.tag'].browse(operation[2])
                    tag_names = tags.mapped('name')
                elif operation[0] == 4:  # ADD
                    tag = self.env['product.tag'].browse(operation[1])
                    tag_names.append(tag.name)
            
            if tag_names:
                message_body += f"- Tags: {', '.join(tag_names)}\n"
        
        # Log gm_is_dp jika ada
        if 'gm_is_dp' in vals:
            message_body += f"- Is DP?: {vals['gm_is_dp']}\n"
        
        # Log gm_is_dp_payment jika ada
        if 'gm_is_dp_payment' in vals:
            message_body += f"- Is DP Payment?: {vals['gm_is_dp_payment']}\n"
        
        record.message_post(body=message_body)
        
        return record


class ProductProductInherit(models.Model):
    _inherit = 'product.product'

    vit_is_discount = fields.Boolean(string="Is Discount", default=False)
    gm_is_dp = fields.Boolean(
        string="Is DP?",
        help="This is a Down Payment product",
        # Tidak perlu related karena kita sync manual untuk lebih reliable
    )
    gm_is_dp_payment = fields.Boolean(
        string="Is DP Payment?",
        help="This is a Down Payment Payment product",
        # Tidak perlu related karena kita sync manual untuk lebih reliable
    )

    def _check_barcode_uniqueness(self):
        # Override untuk mematikan validasi barcode unik
        # Tidak akan pernah raise ValidationError lagi walaupun ada duplikat
        return True