import requests
from datetime import datetime, timedelta
import pytz
from odoo import models, fields, api, SUPERUSER_ID
from odoo.exceptions import UserError

class ResPartner(models.Model):
    _inherit = 'res.partner'

    customer_code = fields.Char(string='Customer Code', tracking=True)
    is_integrated = fields.Boolean(string="Integrated", default=False, readonly=True, tracking=True)
    index_store = fields.Many2many('setting.config', string="Index Store", readonly=True)
    vit_customer_group = fields.Many2one('customer.group', string="Customer Group", tracking=True)

    @api.onchange('vit_customer_group')
    def _onchange_vit_customer_group(self):
        """Auto fill pricelist when customer group is selected"""
        if self.vit_customer_group and self.vit_customer_group.vit_pricelist_id:
            self.property_product_pricelist = self.vit_customer_group.vit_pricelist_id

    def write(self, vals):
        # Auto fill pricelist when customer group is updated via write
        if 'vit_customer_group' in vals and vals['vit_customer_group']:
            customer_group = self.env['customer.group'].browse(vals['vit_customer_group'])
            if customer_group and customer_group.vit_pricelist_id:
                vals['property_product_pricelist'] = customer_group.vit_pricelist_id.id
        
        # Log perubahan untuk field tertentu ke chatter
        for partner in self:
            changes = []
            
            # Track phone changes
            if 'phone' in vals:
                old_phone = partner.phone or 'Not Set'
                new_phone = vals['phone'] or 'Not Set'
                if old_phone != new_phone:
                    changes.append(f"Phone: {old_phone} → {new_phone}")
            
            # Track category_id changes
            if 'category_id' in vals:
                old_categories = ', '.join(partner.category_id.mapped('name')) if partner.category_id else 'Not Set'
                
                # Process new categories
                new_category_ids = vals['category_id']
                if new_category_ids:
                    # Handle different formats of many2many write
                    category_records = self.env['res.partner.category']
                    for command in new_category_ids:
                        if command[0] == 6:  # (6, 0, [ids])
                            category_records = self.env['res.partner.category'].browse(command[2])
                        elif command[0] == 4:  # (4, id)
                            category_records |= self.env['res.partner.category'].browse(command[1])
                        elif command[0] == 3:  # (3, id) - unlink
                            continue
                        elif command[0] == 5:  # (5,) - clear all
                            category_records = self.env['res.partner.category']
                            break
                    new_categories = ', '.join(category_records.mapped('name')) if category_records else 'Not Set'
                else:
                    new_categories = 'Not Set'
                
                if old_categories != new_categories:
                    changes.append(f"Tags: {old_categories} → {new_categories}")
            
            # Track customer_code changes
            if 'customer_code' in vals:
                old_code = partner.customer_code or 'Not Set'
                new_code = vals['customer_code'] or 'Not Set'
                if old_code != new_code:
                    changes.append(f"Customer Code: {old_code} → {new_code}")
            
            # Track index_store changes
            if 'index_store' in vals:
                old_stores = ', '.join(partner.index_store.mapped('name')) if partner.index_store else 'Not Set'
                
                # Process new stores
                new_store_ids = vals['index_store']
                if new_store_ids:
                    # Handle different formats of many2many write
                    store_records = self.env['setting.config']
                    for command in new_store_ids:
                        if command[0] == 6:  # (6, 0, [ids])
                            store_records = self.env['setting.config'].browse(command[2])
                        elif command[0] == 4:  # (4, id)
                            store_records |= self.env['setting.config'].browse(command[1])
                        elif command[0] == 3:  # (3, id) - unlink
                            continue
                        elif command[0] == 5:  # (5,) - clear all
                            store_records = self.env['setting.config']
                            break
                    new_stores = ', '.join(store_records.mapped('name')) if store_records else 'Not Set'
                else:
                    new_stores = 'Not Set'
                
                if old_stores != new_stores:
                    changes.append(f"Index Store: {old_stores} → {new_stores}")
            
            # Track customer group changes
            if 'vit_customer_group' in vals:
                old_group = partner.vit_customer_group.vit_group_name if partner.vit_customer_group else 'Not Set'
                new_group_id = vals['vit_customer_group']
                if new_group_id:
                    new_group_record = self.env['customer.group'].browse(new_group_id)
                    new_group = new_group_record.vit_group_name if new_group_record else 'Not Set'
                else:
                    new_group = 'Not Set'
                
                if old_group != new_group:
                    changes.append(f"Customer Group: {old_group} → {new_group}")
            
            # Track pricelist changes
            if 'property_product_pricelist' in vals:
                old_pricelist = partner.property_product_pricelist.name if partner.property_product_pricelist else 'Not Set'
                new_pricelist_id = vals['property_product_pricelist']
                if new_pricelist_id:
                    new_pricelist_record = self.env['product.pricelist'].browse(new_pricelist_id)
                    new_pricelist = new_pricelist_record.name if new_pricelist_record else 'Not Set'
                else:
                    new_pricelist = 'Not Set'
                
                if old_pricelist != new_pricelist:
                    changes.append(f"Pricelist: {old_pricelist} → {new_pricelist}")
            
            # Post message to chatter if there are changes
            if changes:
                message = '\n'.join(changes)
                partner.message_post(body=message, subject="Partner Information Updated")
        
        return super(ResPartner, self).write(vals)

    @api.model
    def create(self, vals):
        """Auto fill pricelist when creating partner with customer group"""
        # Auto-fill company_id if not provided
        if not vals.get('company_id'):
            # Try to get company from context
            company_id = self.env.context.get('company_id')
            
            if not company_id:
                # Get default company from current user
                company_id = self.env.company.id
            
            if not company_id:
                # Fallback: get first active company
                company = self.env['res.company'].search([('active', '=', True)], limit=1)
                if company:
                    company_id = company.id
            
            if company_id:
                vals['company_id'] = company_id
        
        if 'vit_customer_group' in vals and vals['vit_customer_group']:
            # Cari customer group berdasarkan vit_group_name
            customer_group = self.env['customer.group'].search([
                ('vit_group_name', '=', vals['vit_customer_group'])
            ], limit=1)
            
            if customer_group and customer_group.vit_pricelist_id and 'property_product_pricelist' not in vals:
                vals['property_product_pricelist'] = customer_group.vit_pricelist_id.id
        
        # Auto-generate customer_code if not provided
        if not vals.get('customer_code'):
            name = vals.get('name')
            mobile = vals.get('mobile')
            record_employee = self.env['hr.employee'].search([], order="id desc", limit=1)
            employee_name = record_employee.name if record_employee else ''
            employee_mobile_phone = record_employee.mobile_phone if record_employee else ''

            # Fetch system config for prefix flag
            validate_prefix = self.env['ir.config_parameter'].sudo().get_param('pos.validate_prefix_customer') == 'True'

            # Fetch warehouse prefix or fallback
            warehouse_name = 'VIT'
            warehouse = self.env['stock.warehouse'].search([], limit=1)
            if warehouse:
                warehouse_name = warehouse.prefix_code if (validate_prefix and warehouse.prefix_code) else warehouse.code or 'VIT'

            # Check different conditions
            if name != employee_name or (name == employee_name and mobile != employee_mobile_phone):
                sequence_code = 'res.partner.customer.code'
                customer_code_seq = self.env['ir.sequence'].next_by_code(sequence_code)
                if customer_code_seq:
                    vals['customer_code'] = f"{warehouse_name}{customer_code_seq}"
        
        return super(ResPartner, self).create(vals)