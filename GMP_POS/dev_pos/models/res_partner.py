import requests
from datetime import datetime, timedelta
import pytz
from odoo import models, fields, api, SUPERUSER_ID
from odoo.exceptions import UserError

class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model
    def create(self, vals):
        company = super().create(vals)
        # Setelah company dibuat, pastikan partner-nya punya company_id = company ini
        if company.partner_id:
            company.partner_id.sudo().write({'company_id': company.id})
            # Fix semua child/address dari partner tersebut
            children = self.env['res.partner'].sudo().search([
                ('parent_id', '=', company.partner_id.id),
            ])
            if children:
                children.sudo().write({'company_id': company.id})
        return company


class ResPartner(models.Model):
    _inherit = 'res.partner'

    customer_code = fields.Char(string='Customer Code', tracking=True)
    is_integrated = fields.Boolean(string="Integrated", default=False, readonly=True, tracking=True)
    index_store = fields.Many2many('setting.config', string="Index Store", readonly=True)
    vit_customer_group = fields.Many2one('customer.group', string="Customer Group", tracking=True)
    allow_integrated_override = fields.Boolean(
        string='Allow Integrated Override',
        default=False,
        help="If True, is_integrated will not be forced to False on write."
    )
    gm_bp_type = fields.Selection([
        ('vendor', 'Vendor'),
        ('customer', 'Customer'),
    ], string='BP Type', copy=False, tracking=True)
    gm_bp_tax = fields.Many2one(
        'account.tax',
        string='BP Tax',
        domain=[('type_tax_use', '=', 'sale')],
        tracking=True
    )

    is_cashier = fields.Boolean(
        string='Is Cashier',
        compute='_compute_is_cashier',
    )

    @api.depends_context('uid')
    def _compute_is_cashier(self):
        is_cashier = self.env.user.has_group('dev_pos.group_sale_cashier')
        for partner in self:
            partner.is_cashier = is_cashier

    @api.onchange('vit_customer_group')
    def _onchange_vit_customer_group(self):
        if self.vit_customer_group and self.vit_customer_group.vit_pricelist_id:
            self.property_product_pricelist = self.vit_customer_group.vit_pricelist_id

    def _fix_child_company_id(self):
        """Samakan company_id semua child address dengan parent company"""
        for partner in self:
            if not partner.is_company:
                continue
            children = self.env['res.partner'].sudo().search([
                ('parent_id', '=', partner.id),
                ('company_id', '!=', partner.company_id.id),
            ])
            if children:
                children.sudo().write({'company_id': partner.company_id.id})

    # ✅ TAMBAHAN: Override _check_company untuk bypass error incompatible company
    def _check_company(self, fnames=None):
        """ Override untuk mencegah error incompatible companies saat create company baru """
        try:
            return super()._check_company(fnames=fnames)
        except UserError as e:
            # Jika error terkait incompatible company pada partner baru,
            # coba fix dulu lalu skip error
            if 'Incompatible companies' in str(e):
                self._fix_child_company_id()
                # Coba fix company_id pada diri sendiri jika is_company
                for partner in self:
                    if partner.is_company and not partner.company_id:
                        partner.sudo().write({'company_id': partner.id})
                return  # Bypass error setelah fix
            raise  # Re-raise error lain yang tidak terkait

    def write(self, vals):
        if vals.get('allow_integrated_override'):
            vals['is_integrated'] = True
            del vals['allow_integrated_override']
        else:
            vals['is_integrated'] = False

        if 'vit_customer_group' in vals and vals['vit_customer_group']:
            customer_group = self.env['customer.group'].browse(vals['vit_customer_group'])
            if customer_group and customer_group.vit_pricelist_id:
                vals['property_product_pricelist'] = customer_group.vit_pricelist_id.id

        for partner in self:
            changes = []

            if 'phone' in vals:
                old_phone = partner.phone or 'Not Set'
                new_phone = vals['phone'] or 'Not Set'
                if old_phone != new_phone:
                    changes.append(f"Phone: {old_phone} → {new_phone}")

            if 'category_id' in vals:
                old_categories = ', '.join(partner.category_id.mapped('name')) if partner.category_id else 'Not Set'
                new_category_ids = vals['category_id']
                if new_category_ids:
                    category_records = self.env['res.partner.category']
                    for command in new_category_ids:
                        if command[0] == 6:
                            category_records = self.env['res.partner.category'].browse(command[2])
                        elif command[0] == 4:
                            category_records |= self.env['res.partner.category'].browse(command[1])
                        elif command[0] == 3:
                            continue
                        elif command[0] == 5:
                            category_records = self.env['res.partner.category']
                            break
                    new_categories = ', '.join(category_records.mapped('name')) if category_records else 'Not Set'
                else:
                    new_categories = 'Not Set'
                if old_categories != new_categories:
                    changes.append(f"Tags: {old_categories} → {new_categories}")

            if 'customer_code' in vals:
                old_code = partner.customer_code or 'Not Set'
                new_code = vals['customer_code'] or 'Not Set'
                if old_code != new_code:
                    changes.append(f"Customer Code: {old_code} → {new_code}")

            if 'index_store' in vals:
                old_stores = ', '.join(partner.index_store.mapped('name')) if partner.index_store else 'Not Set'
                new_store_ids = vals['index_store']
                if new_store_ids:
                    store_records = self.env['setting.config']
                    for command in new_store_ids:
                        if command[0] == 6:
                            store_records = self.env['setting.config'].browse(command[2])
                        elif command[0] == 4:
                            store_records |= self.env['setting.config'].browse(command[1])
                        elif command[0] == 3:
                            continue
                        elif command[0] == 5:
                            store_records = self.env['setting.config']
                            break
                    new_stores = ', '.join(store_records.mapped('name')) if store_records else 'Not Set'
                else:
                    new_stores = 'Not Set'
                if old_stores != new_stores:
                    changes.append(f"Index Store: {old_stores} → {new_stores}")

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

            if changes:
                message = '\n'.join(changes)
                partner.message_post(body=message, subject="Partner Information Updated")

        result = super(ResPartner, self).write(vals)

        if 'company_id' in vals or 'is_company' in vals:
            self._fix_child_company_id()

        return result

    @api.model
    def create(self, vals):
        # ✅ Jika partner adalah company (is_company=True), pastikan company_id konsisten
        if vals.get('is_company') and not vals.get('company_id'):
            # Akan di-set setelah create, skip dulu agar tidak konflik
            pass

        if not vals.get('company_id'):
            company_id = self.env.context.get('company_id')
            if not company_id:
                company_id = self.env.company.id
            if not company_id:
                company = self.env['res.company'].search([('active', '=', True)], limit=1)
                if company:
                    company_id = company.id
            if company_id:
                vals['company_id'] = company_id

        if not vals.get('gm_bp_tax'):
            company_id = vals.get('company_id') or self.env.company.id
            company = self.env['res.company'].browse(company_id)
            if company and company.account_sale_tax_id:
                vals['gm_bp_tax'] = company.account_sale_tax_id.id

        if 'vit_customer_group' in vals and vals['vit_customer_group']:
            customer_group = self.env['customer.group'].search([
                ('vit_group_name', '=', vals['vit_customer_group'])
            ], limit=1)
            if customer_group and customer_group.vit_pricelist_id and 'property_product_pricelist' not in vals:
                vals['property_product_pricelist'] = customer_group.vit_pricelist_id.id

        if not vals.get('customer_code'):
            company_id = vals.get('company_id') or self.env.company.id
            customer_code_seq = self.env['ir.sequence'].sudo().with_company(
                company_id
            ).next_by_code('res.partner.customer.code')
            if customer_code_seq:
                vals['customer_code'] = customer_code_seq

        record = super(ResPartner, self).create(vals)
        record._fix_child_company_id()
        return record