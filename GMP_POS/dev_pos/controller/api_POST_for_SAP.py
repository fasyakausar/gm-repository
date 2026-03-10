from odoo import http, api, SUPERUSER_ID
from concurrent.futures import ThreadPoolExecutor, as_completed
from odoo.http import request
import requests
from datetime import datetime
import json
import logging
import base64
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)


import json
from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class POSTMasterTax(http.Controller):
    @http.route('/api/master_tax', type='json', auth='none', methods=['POST'], csrf=False)
    def post_master_tax(self, **kw):
        try:
            config = request.env['setting.config'].sudo().search(
                [('vit_config_server', '=', 'mc')], limit=1
            )
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}
 
            uid = request.session.authenticate(
                request.session.db,
                config.vit_config_username,
                config.vit_config_password_api
            )
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}
 
            env = request.env(user=request.env.ref('base.user_admin').id)
 
            json_data = request.get_json_data()
            items = json_data.get('items', [])
            if isinstance(items, dict):
                items = [items]
            elif not isinstance(items, list):
                return {'status': "Failed", 'code': 400, 'message': "'items' must be a list."}
            if not items:
                return {'status': "Failed", 'code': 400, 'message': "'items' list is empty."}
 
            companies = env['res.company'].sudo().search([('active', '=', True)])
            if not companies:
                return {'status': "Failed", 'code': 404, 'message': "No active companies found."}
 
            created, updated, failed = [], [], []
 
            for item in items:
                try:
                    tax_name = item.get('name')
                    if not tax_name:
                        failed.append({
                            'data': item,
                            'message': "Missing tax 'name'",
                            'company_id': None,
                            'company_name': None,
                            'id': None
                        })
                        continue
 
                    valid_amount_types = ['percent', 'fixed', 'division', 'group']
                    amount_type = item.get('amount_type', 'percent')
                    if amount_type not in valid_amount_types:
                        failed.append({
                            'data': item,
                            'message': f"Invalid amount_type '{amount_type}'",
                            'company_id': None,
                            'company_name': None,
                            'id': None
                        })
                        continue
 
                    # ✅ Active/Archive boolean validation
                    active = item.get('active', True)
                    if not isinstance(active, bool):
                        if isinstance(active, str):
                            active = active.lower() not in ['false', '0', 'no']
                        else:
                            active = bool(active)
 
                    for company in companies:
                        savepoint_name = f'company_{company.id}_tax_{tax_name}'
                        try:
                            env.cr.execute(f'SAVEPOINT "{savepoint_name}"')
 
                            tax_group = env['account.tax.group'].sudo().search([
                                ('company_id', '=', company.id),
                                ('name', 'ilike', "Taxes")
                            ], limit=1)
 
                            # ✅ Cari juga tax yang sudah diarchive
                            existing_tax = env['account.tax'].sudo().with_context(active_test=False).search([
                                ('name', '=', tax_name),
                                ('company_id', '=', company.id)
                            ], limit=1)
 
                            tax_data = {
                                'name': tax_name,
                                'description': item.get('description'),
                                'amount_type': item.get('amount_type', 'percent'),
                                'active': active,  # ✅ TAMBAHAN
                                'amount': item.get('amount', 0),
                                'invoice_label': item.get('invoice_label'),
                                'company_id': company.id,
                                'create_uid': uid,
                                'tax_group_id': tax_group.id if tax_group else False,
                            }
 
                            if existing_tax:
                                update_data = {k: v for k, v in tax_data.items() if k != 'company_id'}
                                existing_tax.sudo().write(update_data)
                                updated.append({
                                    'id': existing_tax.id,
                                    'name': existing_tax.name,
                                    'company_id': company.id,
                                    'company_name': company.name,
                                    'active': existing_tax.active,  # ✅ TAMBAHAN
                                    'action': 'archived' if not existing_tax.active else 'updated'  # ✅ TAMBAHAN
                                })
                            else:
                                new_tax = env['account.tax'].sudo().create(tax_data)
                                created.append({
                                    'id': new_tax.id,
                                    'name': new_tax.name,
                                    'company_id': company.id,
                                    'company_name': company.name,
                                    'active': new_tax.active,  # ✅ TAMBAHAN
                                    'action': 'created'
                                })
 
                            env.cr.execute(f'RELEASE SAVEPOINT "{savepoint_name}"')
 
                        except Exception as e:
                            try:
                                env.cr.execute(f'ROLLBACK TO SAVEPOINT "{savepoint_name}"')
                            except:
                                pass
                            failed.append({
                                'data': item,
                                'company_id': company.id,
                                'company_name': company.name,
                                'message': f"Error: {str(e)}",
                                'id': None
                            })
 
                except Exception as e:
                    failed.append({
                        'data': item,
                        'company_id': None,
                        'company_name': None,
                        'message': f"Error: {str(e)}",
                        'id': None
                    })
 
            env.cr.commit()
 
            return {
                'code': 200 if not failed else 207,
                'status': 'success' if not failed else 'partial_success',
                'total_companies_processed': len(companies),
                'summary': {
                    'total_created': len(created),
                    'total_updated': len(updated),
                    'total_failed': len(failed)
                },
                'created_taxes': created,
                'updated_taxes': updated,
                'failed_taxes': failed
            }
 
        except Exception as e:
            try:
                request.env.cr.rollback()
            except:
                pass
            _logger.error(f"Failed to process tax: {str(e)}")
            return {'status': 'Failed', 'code': 500, 'message': f"Failed to process tax: {str(e)}"}
        
class POSTEmployee(http.Controller):
    @http.route('/api/hr_employee', type='http', auth='none', methods=['POST'], csrf=False)
    def post_employee(self, **kw):
        try:
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return request.make_json_response({'status': "Failed", 'code': 500, 'message': "Configuration not found."})
 
            uid = request.session.authenticate(request.session.db, config.vit_config_username, config.vit_config_password_api)
            if not uid:
                return request.make_json_response({'status': "Failed", 'code': 401, 'message': "Authentication failed."})
 
            env = request.env(user=request.env.ref('base.user_admin').id)
 
            data = json.loads(request.httprequest.data.decode('utf-8'))
 
            items = data.get('items', [])
            if not isinstance(items, list):
                return request.make_json_response({'status': "Failed", 'code': 400, 'message': "'items' must be a list."})
 
            companies = env['res.company'].sudo().search([('active', '=', True)])
            if not companies:
                return request.make_json_response({'status': "Failed", 'code': 404, 'message': "No active companies found."})
 
            created = []
            updated = []
            failed = []
 
            for data_item in items:
                try:
                    employee_code = data_item.get('employee_code')
                    if not employee_code:
                        failed.append({
                            'data': data_item,
                            'company_id': None,
                            'company_name': None,
                            'message': "Missing employee_code",
                            'id': None
                        })
                        continue
 
                    # ✅ Active/Archive boolean validation
                    active = data_item.get('active', True)
                    if not isinstance(active, bool):
                        if isinstance(active, str):
                            active = active.lower() not in ['false', '0', 'no']
                        else:
                            active = bool(active)
 
                    for company in companies:
                        try:
                            # ✅ Cari juga employee yang sudah diarchive
                            existing_employee = env['hr.employee'].sudo().with_context(active_test=False).search([
                                ('vit_employee_code', '=', employee_code),
                                ('company_id', '=', company.id)
                            ], limit=1)
 
                            department_id = data_item.get('department_id')
                            if department_id:
                                department = env['hr.department'].sudo().search([
                                    ('id', '=', department_id),
                                    '|',
                                    ('company_id', '=', company.id),
                                    ('company_id', '=', False)
                                ], limit=1)
                                if not department:
                                    failed.append({
                                        'data': data_item,
                                        'company_id': company.id,
                                        'company_name': company.name,
                                        'message': f"Department with ID '{department_id}' not found in company '{company.name}'.",
                                        'id': None
                                    })
                                    continue
 
                            employee_data = {
                                'vit_employee_code': employee_code,
                                'name': data_item.get('name'),
                                'work_email': data_item.get('work_email'),
                                'work_phone': data_item.get('work_phone'),
                                'mobile_phone': data_item.get('mobile_phone'),
                                'create_uid': uid,
                                'private_street': data_item.get('address_home_id'),
                                'gender': data_item.get('gender'),
                                'birthday': data_item.get('birthdate'),
                                'is_sales': data_item.get('is_sales', False),
                                'company_id': company.id,
                                'department_id': department_id if department_id else False,
                                'active': active,  # ✅ TAMBAHAN
                            }
 
                            if existing_employee:
                                existing_employee.write(employee_data)
                                updated.append({
                                    'id': existing_employee.id,
                                    'employee_code': existing_employee.vit_employee_code,
                                    'name': existing_employee.name,
                                    'company_id': company.id,
                                    'company_name': company.name,
                                    'active': existing_employee.active,  # ✅ TAMBAHAN
                                    'action': 'archived' if not existing_employee.active else 'updated'  # ✅ TAMBAHAN
                                })
                            else:
                                employee = env['hr.employee'].sudo().create(employee_data)
                                created.append({
                                    'id': employee.id,
                                    'employee_code': employee.vit_employee_code,
                                    'name': employee.name,
                                    'company_id': company.id,
                                    'company_name': company.name,
                                    'active': employee.active,  # ✅ TAMBAHAN
                                    'action': 'created'
                                })
 
                        except Exception as e:
                            failed.append({
                                'data': data_item,
                                'company_id': company.id,
                                'company_name': company.name,
                                'message': f"Error: {str(e)}",
                                'id': None
                            })
 
                except Exception as e:
                    failed.append({
                        'data': data_item,
                        'company_id': None,
                        'company_name': None,
                        'message': f"Error: {str(e)}",
                        'id': None
                    })
 
            return request.make_json_response({
                'code': 200 if not failed else 207,
                'status': 'success' if not failed else 'partial_success',
                'total_companies_processed': len(companies),
                'created_employees': created,
                'updated_employees': updated,
                'failed_employees': failed
            })
 
        except Exception as e:
            request.env.cr.rollback()
            _logger.error(f"Failed to process employees: {str(e)}", exc_info=True)
            return request.make_json_response({'status': "Failed", 'code': 500, 'message': f"Failed to process employees: {str(e)}"})


class POSTMasterBoM(http.Controller):
    @http.route('/api/master_bom', type='json', auth='none', methods=['POST'], csrf=False)
    def post_master_bom(self, **kw):
        try:
            # Authentication
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}
            
            uid = request.session.authenticate(request.session.db, config.vit_config_username, config.vit_config_password_api)
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)
            
            # Get all active companies
            companies = env['res.company'].sudo().search([('active', '=', True)])
            if not companies:
                return {
                    'status': "Failed", 
                    'code': 404, 
                    'message': "No active companies found."
                }

            data = request.get_json_data()
            items = data.get('items', [])
            if not isinstance(items, list):
                items = [items]

            created = []  # To store successfully created BoMs
            updated = []  # To store successfully updated BoMs
            failed = []   # To store failed BoMs

            # Process each item
            for data_item in items:
                try:
                    product_tmpl_id = data_item.get('product_tmpl_id')
                    product_id = data_item.get('product_id')
                    quantity = data_item.get('quantity')
                    reference = data_item.get('reference')
                    type = data_item.get('type')
                    move_lines = data_item.get('move_lines', [])

                    if not product_tmpl_id or not product_id:
                        failed.append({
                            'data': data_item,
                            'company_id': None,
                            'company_name': None,
                            'message': "Missing product_tmpl_id or product_id",
                            'id': None
                        })
                        continue

                    # Validate product template
                    product_tmpl = env['product.template'].sudo().search([('default_code', '=', product_tmpl_id)], limit=1)
                    if not product_tmpl:
                        failed.append({
                            'data': data_item,
                            'company_id': None,
                            'company_name': None,
                            'message': f"Product Template with code '{product_tmpl_id}' not found.",
                            'id': None
                        })
                        continue
                    
                    # Validate product variant
                    product_variant = env['product.product'].sudo().search([('default_code', '=', product_id)], limit=1)
                    if not product_variant:
                        failed.append({
                            'data': data_item,
                            'company_id': None,
                            'company_name': None,
                            'message': f"Product Variant with code '{product_id}' not found.",
                            'id': None
                        })
                        continue

                    # Validate all products in move_lines
                    missing_products = []
                    for line in move_lines:
                        product_code = line.get('product_code')
                        product = env['product.product'].sudo().search([('default_code', '=', product_code)], limit=1)
                        if not product:
                            missing_products.append(product_code)

                    if missing_products:
                        failed.append({
                            'data': data_item,
                            'company_id': None,
                            'company_name': None,
                            'message': f"Products with codes {', '.join(missing_products)} not found.",
                            'id': None
                        })
                        continue

                    # Loop through all companies
                    for company in companies:
                        try:
                            # Check if BoM already exists for this product and company
                            existing_bom = env['mrp.bom'].sudo().search([
                                ('product_tmpl_id', '=', product_tmpl.id),
                                ('product_id', '=', product_variant.id),
                                ('company_id', '=', company.id)
                            ], limit=1)
                            
                            bom_data = {
                                'product_tmpl_id': product_tmpl.id,
                                'product_id': product_variant.id,
                                'product_qty': quantity,
                                'code': reference,
                                'type': type,
                                'company_id': company.id
                            }

                            if existing_bom:
                                # Update existing BoM
                                existing_bom.write(bom_data)
                                
                                # Update BoM lines
                                if move_lines:
                                    # Clear existing lines
                                    existing_bom.bom_line_ids.unlink()
                                    
                                    # Create new lines
                                    bom_line_data = []
                                    for line in move_lines:
                                        line_product_code = line.get('product_code')
                                        line_product = env['product.product'].sudo().search([
                                            ('default_code', '=', line_product_code)
                                        ], limit=1)
                                        
                                        if line_product:
                                            bom_line_data.append((0, 0, {
                                                'product_id': line_product.id,
                                                'product_qty': line.get('product_qty', 1.0),
                                                'bom_id': existing_bom.id
                                            }))
                                    
                                    if bom_line_data:
                                        existing_bom.write({
                                            'bom_line_ids': bom_line_data
                                        })

                                updated.append({
                                    'id': existing_bom.id,
                                    'product_tmpl_id': product_tmpl.id,
                                    'product_id': product_variant.id,
                                    'code': existing_bom.code,
                                    'company_id': company.id,
                                    'company_name': company.name,
                                    'action': 'updated'
                                })
                            else:
                                # Create new BoM
                                bom_master = env['mrp.bom'].sudo().create(bom_data)

                                # Create BoM lines
                                if move_lines:
                                    bom_line_data = []
                                    for line in move_lines:
                                        line_product_code = line.get('product_code')
                                        line_product = env['product.product'].sudo().search([
                                            ('default_code', '=', line_product_code)
                                        ], limit=1)
                                        
                                        if line_product:
                                            bom_line_data.append((0, 0, {
                                                'product_id': line_product.id,
                                                'product_qty': line.get('product_qty', 1.0),
                                                'bom_id': bom_master.id
                                            }))
                                    
                                    if bom_line_data:
                                        bom_master.write({
                                            'bom_line_ids': bom_line_data
                                        })

                                created.append({
                                    'id': bom_master.id,
                                    'product_tmpl_id': product_tmpl.id,
                                    'product_id': product_variant.id,
                                    'code': bom_master.code,
                                    'company_id': company.id,
                                    'company_name': company.name,
                                    'action': 'created'
                                })

                        except Exception as e:
                            failed.append({
                                'data': data_item,
                                'company_id': company.id,
                                'company_name': company.name,
                                'message': f"Error: {str(e)}",
                                'id': None
                            })

                except Exception as e:
                    failed.append({
                        'data': data_item,
                        'company_id': None,
                        'company_name': None,
                        'message': f"Error: {str(e)}",
                        'id': None
                    })

            # Return response
            return {
                'code': 200,
                'status': 'success',
                'total_companies_processed': len(companies),
                'created_boms': created,
                'updated_boms': updated,
                'failed_boms': failed
            }

        except Exception as e:
            request.env.cr.rollback()
            _logger.error(f"Failed to process BoMs: {str(e)}", exc_info=True)
            return {
                'status': "Failed", 
                'code': 500, 
                'message': f"Failed to process BoMs: {str(e)}"
            }

class POSTMasterItem(http.Controller):
    @http.route('/api/master_item', type='json', auth='none', methods=['POST'], csrf=False)
    def post_master_item(self, **kw):
        try:
            # Autentikasi
            config = request.env['setting.config'].sudo().search(
                [('vit_config_server', '=', 'mc')], limit=1
            )
            if not config:
                return {
                    'code': 500,
                    'status': 'Failed',
                    'message': 'Configuration not found.'
                }

            uid = request.session.authenticate(
                request.session.db,
                config.vit_config_username,
                config.vit_config_password_api
            )
            if not uid:
                return {
                    'code': 401,
                    'status': 'Failed',
                    'message': 'Authentication failed.'
                }

            env = request.env(user=request.env.ref('base.user_admin').id)

            # Get all active companies
            companies = env['res.company'].sudo().search([('active', '=', True)])
            if not companies:
                return {
                    'status': "Failed",
                    'code': 404,
                    'message': "No active companies found."
                }

            json_data = request.get_json_data()
            items = json_data.get('items', [])
            if isinstance(items, dict):
                items = [items]
            elif not isinstance(items, list):
                return {
                    'code': 400,
                    'status': 'Failed',
                    'message': "'items' must be a list or object."
                }

            created = []
            updated = []
            failed = []

            # Process each item
            for data_item in items:
                try:
                    product_code = data_item.get('product_code')
                    if not product_code:
                        failed.append({
                            'data': data_item,
                            'company_id': None,
                            'company_name': None,
                            'message': "Missing product_code",
                            'id': None
                        })
                        continue

                    # ✅ Active/Archive boolean validation
                    active = data_item.get('active', True)
                    if not isinstance(active, bool):
                        if isinstance(active, str):
                            active = active.lower() not in ['false', '0', 'no']
                        else:
                            active = bool(active)

                    # Loop through all companies
                    for company in companies:
                        try:
                            # Start a new savepoint for each company iteration
                            savepoint_name = f'company_{company.id}_product_{product_code}'
                            env.cr.execute(f'SAVEPOINT {savepoint_name}')

                            # ✅ Cek apakah product sudah ada (termasuk yang sudah diarchive)
                            existing_product = env['product.template'].sudo().search([
                                ('default_code', '=', product_code),
                                ('company_id', '=', company.id),
                                '|',
                                ('active', '=', True),
                                ('active', '=', False),
                            ], limit=1)

                            # Cek kategori
                            category_name = data_item.get('category_name')
                            category_id = False
                            if category_name:
                                category = env['product.category'].sudo().search([
                                    ('complete_name', '=', category_name),
                                ], limit=1)
                                category_id = category.id if category else False

                            # UOM - Support string name
                            uom_id = data_item.get('uom_id', 1)
                            if isinstance(uom_id, str):
                                uom = env['uom.uom'].sudo().search([
                                    ('name', '=', uom_id)
                                ], limit=1)
                                if not uom:
                                    raise ValueError(f"UOM '{uom_id}' not found")
                                uom_id = uom.id

                            uom_po_id = data_item.get('uom_po_id', 1)
                            if isinstance(uom_po_id, str):
                                uom_po = env['uom.uom'].sudo().search([
                                    ('name', '=', uom_po_id)
                                ], limit=1)
                                if not uom_po:
                                    raise ValueError(f"UOM PO '{uom_po_id}' not found")
                                uom_po_id = uom_po.id

                            # POS Category
                            pos_categ_command = []
                            pos_categ_data = data_item.get('pos_categ_ids', data_item.get('pos_categ_id', []))
                            if not isinstance(pos_categ_data, list):
                                pos_categ_data = [pos_categ_data]

                            for categ_item in pos_categ_data:
                                if isinstance(categ_item, str):
                                    pos_category = env['pos.category'].sudo().search([
                                        ('name', '=', categ_item),
                                    ], limit=1)
                                    if pos_category:
                                        pos_categ_command.append((4, pos_category.id))
                                elif isinstance(categ_item, int):
                                    pos_category = env['pos.category'].sudo().search([
                                        ('id', '=', categ_item),
                                    ], limit=1)
                                    if pos_category:
                                        pos_categ_command.append((4, categ_item))

                            # Pajak
                            tax_command = []
                            tax_names = data_item.get('taxes_names', data_item.get('taxes_name', []))
                            if not isinstance(tax_names, list):
                                tax_names = [tax_names]
                            for tax_name in tax_names:
                                tax = env['account.tax'].sudo().search([
                                    ('name', '=', tax_name),
                                    '|',
                                    ('company_id', '=', company.id),
                                    ('company_id', '=', False)
                                ], limit=1)
                                if tax:
                                    tax_command.append((4, tax.id))

                            # Data produk
                            cost = data_item.get('standard_price', data_item.get('cost', 0.0))
                            product_data = {
                                'name': data_item.get('product_name'),
                                'active': active,  # ✅ Gunakan variable active yang sudah dinormalisasi
                                'default_code': product_code,
                                'detailed_type': data_item.get('product_type', 'product'),
                                'invoice_policy': data_item.get('invoice_policy', 'order'),
                                'create_date': data_item.get('create_date'),
                                'list_price': data_item.get('sales_price', 0.0),
                                'standard_price': cost,
                                'uom_id': uom_id,
                                'uom_po_id': uom_po_id,
                                'pos_categ_ids': [(6, 0, [x[1] for x in pos_categ_command])] if pos_categ_command else False,
                                'categ_id': category_id,
                                'taxes_id': [(6, 0, [x[1] for x in tax_command])] if tax_command else False,
                                'available_in_pos': data_item.get('available_in_pos', True),
                                'image_1920': data_item.get('image_1920'),
                                'barcode': data_item.get('barcode'),
                                'vit_sub_div': data_item.get('vit_sub_div'),
                                'vit_item_kel': data_item.get('vit_item_kel'),
                                'vit_item_type': data_item.get('vit_item_type'),
                                'brand': data_item.get('vit_item_brand'),
                                'gm_sub_category': data_item.get('gm_sub_category'),
                                'gm_class': data_item.get('gm_class'),
                                'gm_manufacturer': data_item.get('gm_manufacturer'),
                                'company_id': company.id,
                            }

                            if existing_product:
                                # Update existing product
                                existing_product.write(product_data)
                                updated.append({
                                    'id': existing_product.id,
                                    'product_code': existing_product.default_code,
                                    'name': existing_product.name,
                                    'company_id': company.id,
                                    'company_name': company.name,
                                    'list_price': existing_product.list_price,
                                    'active': existing_product.active,  # ✅ TAMBAHAN
                                    'action': 'archived' if not existing_product.active else 'updated'  # ✅ TAMBAHAN
                                })
                            else:
                                # Create new product
                                product_data['create_uid'] = uid
                                product = env['product.template'].sudo().create(product_data)
                                created.append({
                                    'id': product.id,
                                    'product_code': product.default_code,
                                    'name': product.name,
                                    'company_id': company.id,
                                    'company_name': company.name,
                                    'list_price': product.list_price,
                                    'active': product.active,  # ✅ TAMBAHAN
                                    'action': 'created'
                                })

                            # Release savepoint if successful
                            env.cr.execute(f'RELEASE SAVEPOINT {savepoint_name}')

                        except Exception as e:
                            # Rollback to savepoint on error
                            try:
                                env.cr.execute(f'ROLLBACK TO SAVEPOINT {savepoint_name}')
                            except:
                                pass

                            failed.append({
                                'data': data_item,
                                'company_id': company.id,
                                'company_name': company.name,
                                'message': f"Error: {str(e)}",
                                'id': None
                            })

                except Exception as e:
                    failed.append({
                        'data': data_item,
                        'company_id': None,
                        'company_name': None,
                        'message': f"Error: {str(e)}",
                        'id': None
                    })

            # Commit transaction
            env.cr.commit()

            # Return response
            return {
                'code': 200 if not failed else 207,
                'status': 'success' if not failed else 'partial_success',
                'total_companies_processed': len(companies),
                'created_items': created,
                'updated_items': updated,
                'failed_items': failed
            }

        except Exception as e:
            try:
                request.env.cr.rollback()
            except:
                pass
            _logger.error(f"Failed to process items: {str(e)}")
            return {
                'status': 'Failed',
                'code': 500,
                'message': f"Failed to process items: {str(e)}"
            }


import logging
from datetime import datetime
from odoo import http, _
from odoo.http import request

_logger = logging.getLogger(__name__)

class POSTMasterPricelist(http.Controller):

    @http.route('/api/master_pricelist', type='json', auth='none', methods=['POST'], csrf=False)
    def post_pricelist(self, **kw):
        """
        Struktur payload (product-centric):
        {
            "items": [
                {
                    "product_code": "0001360",
                    "quantity": 1,
                    "date_start": null,
                    "date_end": null,
                    "prices": [
                        {
                            "pricelist_name": "Price List TEST 1",
                            "currency_id": 12,
                            "conditions": "1_product",
                            "compute_price": "fixed",
                            "fixed_price": 20000,
                            "percent_price": 0
                        },
                        ...
                    ]
                }
            ]
        }
        """
        try:
            # ════════════════════════════════════════════════════
            # AUTH
            # ════════════════════════════════════════════════════
            config = request.env['setting.config'].sudo().search(
                [('vit_config_server', '=', 'mc')], limit=1
            )
            if not config:
                return {'status': 'Failed', 'code': 500, 'message': 'Configuration not found.'}

            uid = request.session.authenticate(
                request.session.db,
                config.vit_config_username,
                config.vit_config_password_api
            )
            if not uid:
                return {'status': 'Failed', 'code': 401, 'message': 'Authentication failed.'}

            # ════════════════════════════════════════════════════
            # ENV — context diset di sini, berlaku untuk semua operasi
            # ════════════════════════════════════════════════════
            env = request.env(
                user=request.env.ref('base.user_admin').id,
                context={
                    'tracking_disable': True,
                    'mail_notrack': True,
                    'mail_activity_automation_skip': True,
                    'recompute': False,
                    'no_recompute': True,
                }
            )

            # ════════════════════════════════════════════════════
            # COMPANIES
            # ════════════════════════════════════════════════════
            companies = env['res.company'].sudo().search([('active', '=', True)])
            if not companies:
                return {'status': 'Failed', 'code': 404, 'message': 'No active companies found.'}
            company_ids = companies.ids

            # ════════════════════════════════════════════════════
            # INPUT
            # ════════════════════════════════════════════════════
            data = request.get_json_data()
            items = data.get('items', [])
            if not isinstance(items, list):
                items = [data]

            created, updated, failed = [], [], []

            # ════════════════════════════════════════════════════
            # STEP 1 — Kumpulkan semua key unik dari seluruh items
            # ════════════════════════════════════════════════════
            all_product_codes = set()
            all_pricelist_names = set()
            all_currency_ids = set()

            for item in items:
                if item.get('product_code'):
                    all_product_codes.add(item['product_code'])
                for price in item.get('prices', []):
                    if price.get('pricelist_name'):
                        all_pricelist_names.add(price['pricelist_name'])
                    if price.get('currency_id'):
                        all_currency_ids.add(price['currency_id'])

            # ════════════════════════════════════════════════════
            # STEP 2 — Bulk query 1x per model
            # ════════════════════════════════════════════════════

            # Product map: (default_code, company_id|False) → product_tmpl_id
            all_products_rs = env['product.product'].sudo().search([
                ('default_code', 'in', list(all_product_codes)),
                '|',
                ('company_id', 'in', company_ids),
                ('company_id', '=', False),
            ])
            product_map = {}
            for p in all_products_rs:
                code = p.default_code
                cid = p.company_id.id or False
                product_map[(code, cid)] = p.product_tmpl_id.id

            def _get_tmpl_id(code, company_id):
                return product_map.get((code, company_id)) or product_map.get((code, False))

            # Currency validation
            valid_currencies = set(
                env['res.currency'].sudo().browse(list(all_currency_ids))
                .filtered('active').ids
            ) if all_currency_ids else set()

            # Existing pricelists (include archived): (name, company_id) → record
            existing_rs = env['product.pricelist'].sudo().with_context(active_test=False).search([
                ('name', 'in', list(all_pricelist_names)),
                ('company_id', 'in', company_ids),
            ])
            # Prefetch item_ids + product_tmpl_id sekaligus → hindari N+1 query
            existing_rs.mapped('item_ids.product_tmpl_id')
            existing_map = {
                (pl.name, pl.company_id.id): pl for pl in existing_rs
            }

            # ════════════════════════════════════════════════════
            # STEP 3 — Validasi & parse, kumpulkan per pricelist
            # ════════════════════════════════════════════════════
            pricelist_ops = {}

            for item in items:
                product_code = item.get('product_code')
                if not product_code:
                    failed.append({
                        'product_code': None,
                        'message': 'Missing product_code',
                    })
                    continue

                prices = item.get('prices', [])
                if not prices:
                    failed.append({
                        'product_code': product_code,
                        'message': 'No prices provided',
                    })
                    continue

                # Parse date di level item
                date_start = item.get('date_start')
                date_end = item.get('date_end')
                try:
                    if date_start:
                        date_start = datetime.strptime(date_start.split('.')[0], '%Y-%m-%d %H:%M:%S')
                    if date_end:
                        date_end = datetime.strptime(date_end.split('.')[0], '%Y-%m-%d %H:%M:%S')
                    if date_start and date_end and date_start > date_end:
                        failed.append({
                            'product_code': product_code,
                            'message': 'Invalid date range (date_start > date_end)',
                        })
                        continue
                except ValueError as e:
                    failed.append({
                        'product_code': product_code,
                        'message': f"Invalid date format: {e}",
                    })
                    continue

                quantity = item.get('quantity', 1)

                for price in prices:
                    pricelist_name = price.get('pricelist_name')
                    currency_id = price.get('currency_id')
                    compute_price = price.get('compute_price', 'fixed')
                    conditions = price.get('conditions', '1_product')

                    if not pricelist_name:
                        failed.append({
                            'product_code': product_code,
                            'message': 'Missing pricelist_name in prices entry',
                        })
                        continue

                    if not currency_id:
                        failed.append({
                            'product_code': product_code,
                            'pricelist_name': pricelist_name,
                            'message': 'Missing currency_id in prices entry',
                        })
                        continue

                    if currency_id not in valid_currencies:
                        failed.append({
                            'product_code': product_code,
                            'pricelist_name': pricelist_name,
                            'message': f"Currency ID {currency_id} not found or inactive",
                        })
                        continue

                    if compute_price == 'percentage' and price.get('percent_price') is None:
                        failed.append({
                            'product_code': product_code,
                            'pricelist_name': pricelist_name,
                            'message': 'percent_price required for compute_price=percentage',
                        })
                        continue

                    if compute_price == 'fixed' and price.get('fixed_price') is None:
                        failed.append({
                            'product_code': product_code,
                            'pricelist_name': pricelist_name,
                            'message': 'fixed_price required for compute_price=fixed',
                        })
                        continue

                    line_vals = {
                        'applied_on': conditions,
                        'compute_price': compute_price,
                        'percent_price': price.get('percent_price', 0),
                        'fixed_price': price.get('fixed_price', 0),
                        'min_quantity': quantity,
                        'date_start': date_start,
                        'date_end': date_end,
                    }

                    for company in companies:
                        cid = company.id
                        op_key = (pricelist_name, cid)

                        if op_key not in pricelist_ops:
                            pricelist_ops[op_key] = {
                                'pricelist_name': pricelist_name,
                                'currency_id': currency_id,
                                'company': company,
                                'lines': [],
                            }

                        pricelist_ops[op_key]['lines'].append((product_code, dict(line_vals)))

            # ════════════════════════════════════════════════════
            # STEP 4 — Resolve tmpl_id & pisahkan create vs update
            # ════════════════════════════════════════════════════
            write_ops = []
            create_batch = []

            for op_key, op in pricelist_ops.items():
                pricelist_name = op['pricelist_name']
                currency_id = op['currency_id']
                company = op['company']
                cid = company.id

                resolved_lines = []
                missing_codes = []
                for (product_code, line_vals) in op['lines']:
                    tmpl_id = _get_tmpl_id(product_code, cid)
                    if not tmpl_id:
                        missing_codes.append(product_code)
                        continue
                    resolved_lines.append((tmpl_id, line_vals))

                if missing_codes:
                    failed.append({
                        'pricelist_name': pricelist_name,
                        'company_id': cid,
                        'company_name': company.name,
                        'message': (
                            f"Products not found in company '{company.name}': "
                            f"{', '.join(missing_codes)}"
                        ),
                    })
                    if not resolved_lines:
                        continue

                pricelist_data = {
                    'name': pricelist_name,
                    'currency_id': currency_id,
                    'company_id': cid,
                }

                existing_pl = existing_map.get((pricelist_name, cid))

                if existing_pl:
                    # Build map of existing lines by product_tmpl_id
                    existing_lines_map = {
                        line.product_tmpl_id.id: line
                        for line in existing_pl.item_ids
                    }

                    upsert_commands = []
                    # Lines to keep: we will process all resolved lines
                    new_tmpl_ids = set()
                    for (tmpl_id, line_vals) in resolved_lines:
                        new_tmpl_ids.add(tmpl_id)
                        full_vals = {**line_vals, 'product_tmpl_id': tmpl_id}
                        existing_line = existing_lines_map.get(tmpl_id)
                        if not existing_line:
                            # New line
                            upsert_commands.append((0, 0, full_vals))
                        else:
                            # Check if any field changed
                            changed = False
                            for field, val in full_vals.items():
                                if field == 'product_tmpl_id':
                                    continue
                                # Compare values (careful with dates, they might be datetime vs string)
                                if existing_line[field] != val:
                                    changed = True
                                    break
                            if changed:
                                upsert_commands.append((1, existing_line.id, full_vals))
                            # else: no change, skip this line

                    # Remove lines that are no longer in the source
                    for tmpl_id, existing_line in existing_lines_map.items():
                        if tmpl_id not in new_tmpl_ids:
                            # This line should be deleted
                            upsert_commands.append((2, existing_line.id, 0))

                    # Only proceed if there are changes
                    if upsert_commands:
                        write_ops.append((existing_pl, company, {
                            **pricelist_data,
                            'item_ids': upsert_commands,
                        }))
                    else:
                        # No changes, log as updated with zero changes? Or skip entirely.
                        updated.append({
                            'id': existing_pl.id,
                            'name': existing_pl.name,
                            'company_id': company.id,
                            'company_name': company.name,
                            'active': existing_pl.active,
                            'action': 'no_change',
                            'lines_updated': 0,
                        })
                else:
                    create_lines = [
                        (0, 0, {**line_vals, 'product_tmpl_id': tmpl_id})
                        for (tmpl_id, line_vals) in resolved_lines
                    ]
                    create_batch.append((company, {
                        **pricelist_data,
                        'item_ids': create_lines,
                        'create_uid': uid,
                    }))

            # ════════════════════════════════════════════════════
            # STEP 5 — Eksekusi DB operations
            # ════════════════════════════════════════════════════

            # UPDATE — pakai savepoint agar 1 error tidak abort semua transaksi
            for rec, company, vals in write_ops:
                try:
                    with env.cr.savepoint():
                        rec.sudo().write(vals)
                    updated.append({
                        'id': rec.id,
                        'name': rec.name,
                        'company_id': company.id,
                        'company_name': company.name,
                        'active': rec.active,
                        'action': 'updated',
                        'lines_updated': len(vals.get('item_ids', [])),
                    })
                except Exception as e:
                    _logger.error(f"Pricelist update error [{rec.name}]: {e}", exc_info=True)
                    failed.append({
                        'pricelist_name': rec.name,
                        'company_id': company.id,
                        'company_name': company.name,
                        'message': f"Update failed: {e}",
                        'id': rec.id,
                    })

            # CREATE — batch sekaligus dengan savepoint
            if create_batch:
                try:
                    with env.cr.savepoint():
                        new_pls = env['product.pricelist'].sudo().create(
                            [pl_data for _, pl_data in create_batch]
                        )
                    for (company, pl_data), pl in zip(create_batch, new_pls):
                        created.append({
                            'id': pl.id,
                            'name': pl.name,
                            'company_id': company.id,
                            'company_name': company.name,
                            'active': pl.active,
                            'action': 'created',
                            'lines_added': len(pl.item_ids),
                        })
                        existing_map[(pl.name, company.id)] = pl
                except Exception as e:
                    _logger.error(f"Pricelist batch create error: {e}", exc_info=True)
                    for company, pl_data in create_batch:
                        failed.append({
                            'pricelist_name': pl_data.get('name'),
                            'company_id': company.id,
                            'company_name': company.name,
                            'message': f"Batch create failed: {e}",
                            'id': None,
                        })

            return {
                'code': 200 if not failed else 207,
                'status': 'success' if not failed else 'partial_success',
                'total_companies_processed': len(companies),
                'total_created': len(created),
                'total_updated': len(updated),
                'total_failed': len(failed),
                'created_pricelists': created,
                'updated_pricelists': updated,
                'failed_pricelists': failed,
            }

        except Exception as e:
            request.env.cr.rollback()
            _logger.error(f"Failed to process Pricelists: {e}", exc_info=True)
            return {'status': 'Failed', 'code': 500, 'message': f"Failed to process Pricelists: {e}"}
        
class POSTMasterUoM(http.Controller):
    @http.route('/api/master_uom', type='json', auth='none', methods=['POST'], csrf=False)
    def post_master_uom(self, **kw):
        try:
            # 🔐 Autentikasi
            config = request.env['setting.config'].sudo().search(
                [('vit_config_server', '=', 'mc')], limit=1
            )
            if not config:
                return {
                    'status': 'Failed',
                    'code': 500,
                    'message': 'Configuration not found.'
                }

            uid = request.session.authenticate(
                request.session.db,
                config.vit_config_username,
                config.vit_config_password_api
            )
            if not uid:
                return {
                    'status': 'Failed',
                    'code': 401,
                    'message': 'Authentication failed.'
                }

            env = request.env(user=request.env.ref('base.user_admin').id)
            
            # Get all active companies
            companies = env['res.company'].sudo().search([('active', '=', True)])
            if not companies:
                return {
                    'status': "Failed", 
                    'code': 404, 
                    'message': "No active companies found."
                }

            json_data = request.get_json_data()
            items = json_data.get('items')

            # ✅ Bisa single dict atau list
            if isinstance(items, dict):
                items = [items]
            elif items is None and isinstance(json_data, dict):
                items = [json_data]
            elif not isinstance(items, list):
                return {
                    'status': 'Failed',
                    'code': 400,
                    'message': "'items' must be a list or object."
                }

            created = []  # To store successfully created UoMs
            updated = []  # To store successfully updated UoMs
            failed = []   # To store failed UoMs

            # Process each item
            for data_item in items:
                try:
                    name = data_item.get('name')
                    uom_type = data_item.get('uom_type')
                    category_id = data_item.get('category_id')

                    if not name or not uom_type or not category_id:
                        failed.append({
                            'data': data_item,
                            'company_id': None,
                            'company_name': None,
                            'message': "Missing required field: name, uom_type, or category_id",
                            'id': None
                        })
                        continue

                    # Loop through all companies
                    for company in companies:
                        try:
                            # Cek apakah UoM sudah ada berdasarkan name & category_id per company
                            existing = env['uom.uom'].sudo().search([
                                ('name', '=', name),
                                ('category_id', '=', category_id),
                                '|',
                                ('company_id', '=', company.id),
                                ('company_id', '=', False)
                            ], limit=1)
                            
                            uom_data = {
                                'name': name,
                                'uom_type': uom_type,
                                'category_id': category_id,
                                'rounding': data_item.get('rounding', 1.0),
                                'ratio': data_item.get('ratio', 1.0),
                                'active': data_item.get('active', True),
                                'factor': data_item.get('factor', 1.0),
                                'factor_inv': data_item.get('factor_inv', 1.0),
                                'company_id': company.id,
                            }

                            if existing:
                                # Update existing UoM
                                existing.write(uom_data)
                                updated.append({
                                    'id': existing.id,
                                    'name': existing.name,
                                    'uom_type': existing.uom_type,
                                    'category_id': existing.category_id.id,
                                    'category': existing.category_id.name,
                                    'company_id': company.id,
                                    'company_name': company.name,
                                    'action': 'updated'
                                })
                            else:
                                # Create new UoM
                                uom = env['uom.uom'].sudo().create(uom_data)
                                created.append({
                                    'id': uom.id,
                                    'name': uom.name,
                                    'uom_type': uom.uom_type,
                                    'category_id': uom.category_id.id,
                                    'category': uom.category_id.name,
                                    'company_id': company.id,
                                    'company_name': company.name,
                                    'action': 'created'
                                })

                        except Exception as e:
                            failed.append({
                                'data': data_item,
                                'company_id': company.id,
                                'company_name': company.name,
                                'message': f"Error: {str(e)}",
                                'id': None
                            })

                except Exception as e:
                    failed.append({
                        'data': data_item,
                        'company_id': None,
                        'company_name': None,
                        'message': f"Error: {str(e)}",
                        'id': None
                    })

            # Return response
            return {
                'code': 200,
                'status': 'success',
                'total_companies_processed': len(companies),
                'created_uoms': created,
                'updated_uoms': updated,
                'failed_uoms': failed
            }

        except Exception as e:
            request.env.cr.rollback()
            _logger.error(f"Failed to process UoMs: {str(e)}")
            return {
                'status': 'Failed',
                'code': 500,
                'message': f"Failed to process UoMs: {str(e)}"
            }
class POSTCustomerGroup(http.Controller):
    @http.route('/api/master_customer_group', type='json', auth='none', methods=['POST'], csrf=False)
    def post_customer_group(self, **kw):
        """
        POST Customer Group
        JSON Body:
        {
            "items": [
                {
                    "group_name": "Group A",
                    "pricelist_id": 1
                }
            ]
        }
        """
        try:
            # Check if customer group pricelist is enabled
            if not is_customer_group_pricelist_enabled():
                return {
                    'status': 'Failed',
                    'code': 403,
                    'message': 'Customer Group Pricelist feature is not enabled. Please enable it in POS Settings.'
                }

            # Authentication
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}
            
            uid = request.session.authenticate(request.session.db, config.vit_config_username, config.vit_config_password_api)
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)
            
            # Get all active companies
            companies = env['res.company'].sudo().search([('active', '=', True)])
            if not companies:
                return {
                    'status': "Failed", 
                    'code': 404, 
                    'message': "No active companies found."
                }

            json_data = request.get_json_data()
            items = json_data.get('items', [])
            if not isinstance(items, list):
                items = [json_data]

            created = []  # To store successfully created groups
            updated = []  # To store successfully updated groups
            failed = []   # To store failed groups

            # Process each item
            for data_item in items:
                try:
                    group_name = data_item.get('group_name')
                    pricelist_id = data_item.get('pricelist_id')

                    if not group_name:
                        failed.append({
                            'data': data_item,
                            'company_id': None,
                            'company_name': None,
                            'message': "Missing group_name",
                            'id': None
                        })
                        continue

                    if not pricelist_id:
                        failed.append({
                            'data': data_item,
                            'company_id': None,
                            'company_name': None,
                            'message': "Missing pricelist_id",
                            'id': None
                        })
                        continue

                    # Validate pricelist exists
                    pricelist = env['product.pricelist'].sudo().browse(pricelist_id)
                    if not pricelist.exists():
                        failed.append({
                            'data': data_item,
                            'company_id': None,
                            'company_name': None,
                            'message': f"Pricelist ID {pricelist_id} not found",
                            'id': None
                        })
                        continue

                    # Loop through all companies
                    for company in companies:
                        try:
                            # Check if customer group exists by name and company
                            existing = env['customer.group'].sudo().search([
                                ('vit_group_name', '=', group_name),
                                '|',
                                ('company_id', '=', company.id),
                                ('company_id', '=', False)
                            ], limit=1)
                            
                            group_data = {
                                'vit_group_name': group_name,
                                'vit_pricelist_id': pricelist_id,
                                'company_id': company.id,
                            }

                            if existing:
                                # Update existing customer group
                                existing.write(group_data)
                                updated.append({
                                    'id': existing.id,
                                    'group_name': existing.vit_group_name,
                                    'pricelist_id': existing.vit_pricelist_id.id,
                                    'pricelist_name': existing.vit_pricelist_id.name,
                                    'company_id': company.id,
                                    'company_name': company.name,
                                    'action': 'updated'
                                })
                            else:
                                # Create new customer group
                                group_data['create_uid'] = uid
                                group = env['customer.group'].sudo().create(group_data)
                                created.append({
                                    'id': group.id,
                                    'group_name': group.vit_group_name,
                                    'pricelist_id': group.vit_pricelist_id.id,
                                    'pricelist_name': group.vit_pricelist_id.name,
                                    'company_id': company.id,
                                    'company_name': company.name,
                                    'action': 'created'
                                })

                        except Exception as e:
                            failed.append({
                                'data': data_item,
                                'company_id': company.id,
                                'company_name': company.name,
                                'message': f"Error: {str(e)}",
                                'id': None
                            })

                except Exception as e:
                    failed.append({
                        'data': data_item,
                        'company_id': None,
                        'company_name': None,
                        'message': f"Error: {str(e)}",
                        'id': None
                    })

            # Return response
            return {
                'code': 200,
                'status': 'success',
                'total_companies_processed': len(companies),
                'created_groups': created,
                'updated_groups': updated,
                'failed_groups': failed
            }

        except Exception as e:
            request.env.cr.rollback()
            _logger.error(f"Failed to process customer groups: {str(e)}")
            return {
                'status': 'Failed',
                'code': 500,
                'message': f"Failed to process customer groups: {str(e)}"
            }


# ==================== MASTER CUSTOMER API (UPDATED) ====================

import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


def is_customer_group_pricelist_enabled():
    """Check if vit_cust_group_pricelist is enabled"""
    try:
        config = request.env['ir.config_parameter'].sudo()
        return config.get_param('pos.vit_cust_group_pricelist') == 'True'
    except Exception as e:
        _logger.error(f"Error checking customer group pricelist config: {str(e)}")
        return False


class POSTMasterCustomer(http.Controller):
    @http.route('/api/master_customer', type='json', auth='none', methods=['POST'], csrf=False)
    def post_master_customer(self, **kw):
        try:
            # Authentication
            config = request.env['setting.config'].sudo().search(
                [('vit_config_server', '=', 'mc')], limit=1
            )
            if not config:
                return {'status': 'Failed', 'code': 500, 'message': 'Configuration not found.'}

            uid = request.session.authenticate(
                request.session.db,
                config.vit_config_username,
                config.vit_config_password_api
            )
            if not uid:
                return {'status': 'Failed', 'code': 401, 'message': 'Authentication failed.'}

            env = request.env(user=request.env.ref('base.user_admin').id)

            # Check if customer group pricelist is enabled
            group_pricelist_enabled = is_customer_group_pricelist_enabled()

            # Get JSON data
            json_data = request.get_json_data()
            items = json_data.get('items', [])

            if isinstance(items, dict):
                items = [items]
            elif not isinstance(items, list):
                return {'status': 'Failed', 'code': 400, 'message': "'items' must be a list or object."}

            created = []
            updated = []
            failed = []

            VALID_BP_TYPES = ['vendor', 'customer']

            for data_item in items:
                try:
                    customer_code = data_item.get('customer_code')
                    if not customer_code:
                        failed.append({
                            'data': data_item,
                            'company_id': None,
                            'company_name': None,
                            'message': 'Missing customer_code',
                            'id': None
                        })
                        continue

                    # Validate company_name (REQUIRED)
                    company_name = data_item.get('company_name')
                    if not company_name:
                        failed.append({
                            'customer_code': customer_code,
                            'company_id': None,
                            'company_name': None,
                            'message': 'Missing required field: company_name',
                            'id': None
                        })
                        continue

                    # Validate company exists
                    company = env['res.company'].sudo().search(
                        [('name', '=', company_name)], limit=1
                    )
                    if not company:
                        failed.append({
                            'customer_code': customer_code,
                            'company_id': None,
                            'company_name': company_name,
                            'message': f"Company '{company_name}' not found",
                            'id': None
                        })
                        continue

                    # Validasi gm_bp_type
                    gm_bp_type = data_item.get('gm_bp_type', 'customer')
                    if gm_bp_type not in VALID_BP_TYPES:
                        failed.append({
                            'customer_code': customer_code,
                            'company_id': company.id,
                            'company_name': company_name,
                            'message': f"Invalid gm_bp_type '{gm_bp_type}'. Must be one of: {VALID_BP_TYPES}",
                            'id': None
                        })
                        continue

                    # Validasi gm_bp_tax (REQUIRED)
                    gm_bp_tax_name = data_item.get('gm_bp_tax')
                    if not gm_bp_tax_name:
                        failed.append({
                            'customer_code': customer_code,
                            'company_id': company.id,
                            'company_name': company_name,
                            'message': 'Missing required field: gm_bp_tax',
                            'id': None
                        })
                        continue

                    bp_tax = env['account.tax'].sudo().search([
                        ('name', '=', gm_bp_tax_name),
                        ('company_id', '=', company.id)
                    ], limit=1)
                    if not bp_tax:
                        failed.append({
                            'customer_code': customer_code,
                            'company_id': company.id,
                            'company_name': company_name,
                            'message': f"Tax '{gm_bp_tax_name}' not found for company '{company_name}'",
                            'id': None
                        })
                        continue

                    # Validate customer group if enabled
                    if group_pricelist_enabled:
                        vit_customer_group = data_item.get('vit_customer_group')
                        if not vit_customer_group:
                            failed.append({
                                'customer_code': customer_code,
                                'company_id': company.id,
                                'company_name': company_name,
                                'message': 'vit_customer_group is required when Customer Group Pricelist is enabled',
                                'id': None
                            })
                            continue

                        customer_group_check = env['customer.group'].sudo().search([
                            ('id', '=', vit_customer_group),
                            ('company_id', '=', company.id)
                        ], limit=1)
                        if not customer_group_check:
                            failed.append({
                                'customer_code': customer_code,
                                'company_id': company.id,
                                'company_name': company_name,
                                'message': f"Customer group ID {vit_customer_group} not found for company '{company_name}'",
                                'id': None
                            })
                            continue

                    # IS_INTEGRATED boolean validation
                    is_integrated = data_item.get('is_integrated', False)
                    if not isinstance(is_integrated, bool):
                        if isinstance(is_integrated, str):
                            is_integrated = is_integrated.lower() in ['true', '1', 'yes']
                        else:
                            is_integrated = bool(is_integrated)

                    active = data_item.get('active', True)
                    if not isinstance(active, bool):
                        if isinstance(active, str):
                            active = active.lower() not in ['false', '0', 'no']
                        else:
                            active = bool(active)

                    # Resolve pricelist for this company
                    pricelist_raw = data_item.get('property_product_pricelist')
                    resolved_pricelist_id = None
                    if pricelist_raw:
                        try:
                            pricelist_id_int = int(pricelist_raw)
                            pricelist_domain = [
                                ('id', '=', pricelist_id_int),
                                ('company_id', '=', company.id)
                            ]
                        except (ValueError, TypeError):
                            pricelist_domain = [
                                ('name', '=', pricelist_raw),
                                ('company_id', '=', company.id)
                            ]

                        pricelist = env['product.pricelist'].sudo().search(
                            pricelist_domain, limit=1
                        )
                        if not pricelist:
                            failed.append({
                                'customer_code': customer_code,
                                'company_id': company.id,
                                'company_name': company_name,
                                'message': f"Pricelist '{pricelist_raw}' not found for company '{company_name}'",
                                'id': None
                            })
                            continue

                        resolved_pricelist_id = pricelist.id

                    # Check existing customer
                    existing = env['res.partner'].sudo().search([
                        ('customer_code', '=', customer_code),
                        ('company_id', '=', company.id),
                        '|',
                        ('active', '=', True),
                        ('active', '=', False),
                    ], limit=1)

                    customer_vals = {
                        'name': data_item.get('name'),
                        'customer_code': customer_code,
                        'street': data_item.get('street'),
                        'street2': data_item.get('street2'),
                        'city': data_item.get('city'),
                        'zip': data_item.get('zip'),
                        'phone': data_item.get('phone'),
                        'email': data_item.get('email'),
                        'mobile': data_item.get('mobile'),
                        'website': data_item.get('website'),
                        'gm_bp_type': gm_bp_type,
                        'gm_bp_tax': bp_tax.id,
                        'is_integrated': is_integrated,
                        'vat': data_item.get('tax_id'),
                        'l10n_id_pkp': data_item.get('l10n_id_pkp', False),
                        'company_id': company.id,
                        'active': active,
                    }

                    if resolved_pricelist_id:
                        customer_vals['property_product_pricelist'] = resolved_pricelist_id

                    if group_pricelist_enabled and 'vit_customer_group' in data_item:
                        customer_vals['vit_customer_group'] = data_item['vit_customer_group']

                    if existing:
                        existing.write(customer_vals)
                        updated.append({
                            'id': existing.id,
                            'customer_code': existing.customer_code,
                            'name': existing.name,
                            'email': existing.email,
                            'company_id': company.id,
                            'company_name': company_name,
                            'gm_bp_type': existing.gm_bp_type,
                            'gm_bp_tax': existing.gm_bp_tax.name if existing.gm_bp_tax else None,
                            'is_integrated': existing.is_integrated,
                            'active': existing.active,
                            'action': 'archived' if not existing.active else 'updated'
                        })
                    else:
                        customer_vals['create_uid'] = uid
                        customer = env['res.partner'].sudo().create(customer_vals)
                        created.append({
                            'id': customer.id,
                            'customer_code': customer.customer_code,
                            'name': customer.name,
                            'email': customer.email,
                            'company_id': company.id,
                            'company_name': company_name,
                            'gm_bp_type': customer.gm_bp_type,
                            'gm_bp_tax': customer.gm_bp_tax.name if customer.gm_bp_tax else None,
                            'is_integrated': customer.is_integrated,
                            'action': 'created'
                        })

                except Exception as e:
                    failed.append({
                        'customer_code': data_item.get('customer_code'),
                        'company_id': None,
                        'company_name': data_item.get('company_name'),
                        'message': f"Error: {str(e)}",
                        'id': None
                    })

            return {
                'code': 200 if not failed else 207,
                'status': 'success' if not failed else 'partial_success',
                'created_customers': created,
                'updated_customers': updated,
                'failed_customers': failed
            }

        except Exception as e:
            request.env.cr.rollback()
            _logger.error(f"Failed to process customers: {str(e)}")
            return {'status': 'Failed', 'code': 500, 'message': f"Failed to process customers: {str(e)}"}

class MasterCustomerPATCH(http.Controller):
    @http.route(['/api/master_customer'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_master_customer(self, **kwargs):
        try:
            # Authentication
            config = request.env['setting.config'].sudo().search(
                [('vit_config_server', '=', 'mc')], limit=1
            )
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}

            uid = request.session.authenticate(
                request.session.db,
                config.vit_config_username,
                config.vit_config_password_api
            )
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            # Check if customer group pricelist is enabled
            group_pricelist_enabled = is_customer_group_pricelist_enabled()

            json_data = request.get_json_data()
            items = json_data.get('items')

            if isinstance(items, dict):
                items = [items]
            elif not isinstance(items, list):
                return {'status': 'Failed', 'code': 400, 'message': "'items' must be a list or object."}

            updated, errors = [], []

            for data in items:
                try:
                    customer_code = data.get('customer_code')
                    if not customer_code:
                        errors.append({'customer_code': None, 'message': "Missing customer_code"})
                        continue

                    # ✅ Validate company_name (REQUIRED)
                    company_name = data.get('company_name')
                    if not company_name:
                        errors.append({
                            'customer_code': customer_code,
                            'message': "Missing required field: company_name"
                        })
                        continue

                    # ✅ Validate company exists
                    company = request.env['res.company'].sudo().search(
                        [('name', '=', company_name)], limit=1
                    )
                    if not company:
                        errors.append({
                            'customer_code': customer_code,
                            'message': f"Company '{company_name}' not found"
                        })
                        continue

                    # ✅ Validate vit_customer_group if group pricelist is enabled
                    if group_pricelist_enabled and 'vit_customer_group' in data:
                        vit_customer_group = data.get('vit_customer_group')
                        if vit_customer_group:
                            # Validate customer group exists
                            customer_group = request.env['customer.group'].sudo().search([
                                ('id', '=', vit_customer_group),
                                ('company_id', '=', company.id)
                            ], limit=1)
                            if not customer_group:
                                errors.append({
                                    'customer_code': customer_code,
                                    'message': f"Customer group ID {vit_customer_group} not found for company '{company_name}'"
                                })
                                continue

                    # Search customer with customer_code and company_id
                    master_customer = request.env['res.partner'].sudo().search([
                        ('customer_code', '=', customer_code),
                        ('company_id', '=', company.id)
                    ], limit=1)
                    
                    if not master_customer:
                        errors.append({
                            'customer_code': customer_code,
                            'message': f"Customer not found for company '{company_name}'"
                        })
                        continue

                    # Prepare update data
                    update_data = {
                        'name': data.get('name'),
                        'street': data.get('street'),
                        'email': data.get('email'),
                        'mobile': data.get('mobile'),
                        'website': data.get('website'),
                        'write_uid': uid,
                    }

                    # Add property_product_pricelist if provided
                    if 'property_product_pricelist' in data:
                        pricelist_id = data['property_product_pricelist']
                        if pricelist_id:
                            # Validate pricelist exists and belongs to the same company
                            pricelist = request.env['product.pricelist'].sudo().search([
                                ('id', '=', pricelist_id),
                                ('company_id', '=', company.id)
                            ], limit=1)
                            if pricelist:
                                update_data['property_product_pricelist'] = pricelist_id
                            else:
                                errors.append({
                                    'customer_code': customer_code,
                                    'message': f"Pricelist ID {pricelist_id} not found for company '{company_name}'"
                                })
                                continue
                        else:
                            update_data['property_product_pricelist'] = False

                    # Add vit_customer_group if provided and enabled
                    if group_pricelist_enabled and 'vit_customer_group' in data:
                        vit_customer_group = data['vit_customer_group']
                        if vit_customer_group:
                            update_data['vit_customer_group'] = vit_customer_group
                        else:
                            update_data['vit_customer_group'] = False

                    # Remove None values
                    update_data = {
                        key: val for key, val in update_data.items() if val is not None
                    }

                    master_customer.sudo().write(update_data)

                    updated.append({
                        'id': master_customer.id,
                        'customer_code': master_customer.customer_code,
                        'name': master_customer.name,
                        'company_id': master_customer.company_id.id if master_customer.company_id else None,
                        'company_name': master_customer.company_id.name if master_customer.company_id else None,
                        'vit_customer_group': master_customer.vit_customer_group.id if master_customer.vit_customer_group else None,
                        'property_product_pricelist': master_customer.property_product_pricelist.id if master_customer.property_product_pricelist else None,
                        'status': 'success'
                    })

                except Exception as e:
                    errors.append({
                        'customer_code': data.get('customer_code'),
                        'message': f"Exception: {str(e)}"
                    })

            return {
                'code': 200 if not errors else 207,
                'status': 'success' if not errors else 'partial_success',
                'updated_customers': updated,
                'errors': errors
            }

        except Exception as e:
            _logger.error(f"Error updating master customer: {str(e)}")
            return {'code': 500, 'status': 'failed', 'message': str(e)}
    
class POSTMasterWarehouse(http.Controller):
    @http.route('/api/master_warehouse', type='json', auth='none', methods=['POST'], csrf=False)
    def post_master_warehouse(self, **kw):
        try:
            config = request.env['setting.config'].sudo().search([
                ('vit_config_server', '=', 'mc')
            ], limit=1)
 
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}
 
            uid = request.session.authenticate(
                request.session.db,
                config.vit_config_username,
                config.vit_config_password_api
            )
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}
 
            env = request.env
 
            data = request.get_json_data()
            items = data.get('items', [])
 
            if not isinstance(items, list):
                items = [items]
 
            if not items:
                return {'status': "Failed", 'code': 400, 'message': "No items provided"}
 
            created = []
            updated = []
            failed = []
 
            for item in items:
                code = item.get('code')
                name = item.get('name')
                company_name = item.get('company_name')
                transit_location_name = item.get('transit_location')
                is_transit = str(item.get('is_transit', '')).lower() in ['yes', 'y', 'true', '1']
 
                # ✅ Active/Archive boolean validation
                active = item.get('active', True)
                if not isinstance(active, bool):
                    if isinstance(active, str):
                        active = active.lower() not in ['false', '0', 'no']
                    else:
                        active = bool(active)
 
                if not code:
                    failed.append({'data': item, 'message': "Field 'code' is required"})
                    continue
                if not name:
                    failed.append({'data': item, 'message': "Field 'name' is required"})
                    continue
                if not company_name:
                    failed.append({'data': item, 'message': "Field 'company_name' is required"})
                    continue
 
                try:
                    company = env['res.company'].sudo().search([
                        ('name', '=', company_name)
                    ], limit=1)
 
                    if not company:
                        failed.append({
                            'data': item,
                            'message': f"Company '{company_name}' not found in database."
                        })
                        continue
 
                    # ✅ Cari juga warehouse yang sudah diarchive
                    existing = env['stock.warehouse'].sudo().with_context(
                        active_test=False
                    ).search([
                        ('code', '=', code),
                        ('company_id', '=', company.id)
                    ], limit=1)
 
                    if not existing:
                        existing = env['stock.warehouse'].sudo().with_context(
                            active_test=False
                        ).search([
                            ('name', '=', name),
                            ('company_id', '=', company.id)
                        ], limit=1)
 
                    transit_loc = None
                    if transit_location_name and transit_location_name.strip():
                        transit_location_name = transit_location_name.strip()
 
                        transit_loc = env['stock.location'].sudo().search([
                            ('complete_name', '=', transit_location_name),
                            ('company_id', '=', company.id)
                        ], limit=1)
 
                        if not transit_loc:
                            transit_loc = env['stock.location'].sudo().search([
                                ('complete_name', '=', transit_location_name)
                            ], limit=1)
 
                        if not transit_loc:
                            transit_loc = env['stock.location'].sudo().search([
                                ('name', '=', transit_location_name),
                                ('company_id', '=', company.id)
                            ], limit=1)
 
                        if not transit_loc:
                            failed.append({
                                'data': item,
                                'company_name': company_name,
                                'message': f"Transit location '{transit_location_name}' not found for company '{company_name}'"
                            })
                            continue
 
                    if existing:
                        was_archived = not existing.active
 
                        # Unarchive dulu jika archived
                        if not existing.active and active:
                            existing.sudo().with_context(
                                active_test=False,
                                tracking_disable=True,
                                mail_notrack=True
                            ).write({'active': True})
 
                        update_values = {
                            'name': name,
                            'code': code,
                            'active': active,  # ✅ TAMBAHAN
                        }
                        if transit_loc:
                            update_values['location_transit'] = transit_loc.id
 
                        existing.sudo().with_context(
                            allowed_company_ids=[company.id],
                            active_test=False,
                            no_recompute=True,
                            tracking_disable=True,
                            mail_notrack=True
                        ).write(update_values)
 
                        if is_transit and existing.location_transit:
                            existing.location_transit.sudo().write({'usage': 'transit'})
 
                        env.cr.commit()
 
                        # ✅ Tentukan action berdasarkan kondisi
                        if was_archived and active:
                            action = 'unarchived & updated'
                        elif not active:
                            action = 'archived'
                        else:
                            action = 'updated'
 
                        updated.append({
                            'id': existing.id,
                            'code': existing.code,
                            'name': existing.name,
                            'company_id': company.id,
                            'company_name': company.name,
                            'active': existing.active,  # ✅ TAMBAHAN
                            'was_archived': was_archived,
                            'transit_location': existing.location_transit.complete_name if existing.location_transit else None,
                            'transit_location_usage': existing.location_transit.usage if existing.location_transit else None,
                            'action': action
                        })
 
                    else:
                        create_values = {
                            'name': name,
                            'code': code,
                            'company_id': company.id,
                            'create_uid': uid,
                            'active': active,  # ✅ TAMBAHAN
                        }
                        if transit_loc:
                            create_values['location_transit'] = transit_loc.id
 
                        wh = env['stock.warehouse'].sudo().with_context(
                            allowed_company_ids=[company.id]
                        ).create(create_values)
 
                        if is_transit and wh.location_transit:
                            wh.location_transit.sudo().write({'usage': 'transit'})
 
                        env.cr.commit()
 
                        created.append({
                            'id': wh.id,
                            'code': wh.code,
                            'name': wh.name,
                            'company_id': company.id,
                            'company_name': company.name,
                            'active': wh.active,  # ✅ TAMBAHAN
                            'transit_location': wh.location_transit.complete_name if wh.location_transit else None,
                            'transit_location_usage': wh.location_transit.usage if wh.location_transit else None,
                            'action': 'created'
                        })
 
                except Exception as e:
                    env.cr.rollback()
                    error_msg = str(e)
 
                    if 'stock_warehouse_warehouse_name_uniq' in error_msg:
                        error_msg = f"Warehouse name '{name}' already exists in company '{company_name}'"
                    elif 'stock_warehouse_code_uniq' in error_msg or 'duplicate key' in error_msg.lower():
                        error_msg = f"Warehouse code '{code}' already exists in company '{company_name}'"
 
                    failed.append({
                        'data': item,
                        'company_name': company_name if company_name else 'Unknown',
                        'message': error_msg
                    })
 
            return {
                'code': 200 if not failed else 207,
                'status': 'success' if not failed else 'partial_success',
                'message': f"Processed {len(items)} items: {len(created)} created, {len(updated)} updated, {len(failed)} failed",
                'summary': {
                    'total': len(items),
                    'created': len(created),
                    'updated': len(updated),
                    'failed': len(failed)
                },
                'created': created,
                'updated': updated,
                'failed': failed,
            }
 
        except Exception as e:
            request.env.cr.rollback()
            return {
                'status': "Failed",
                'code': 500,
                'message': f"Server error: {str(e)}"
            }

class POSTMappingTax(http.Controller):

    @http.route('/api/mapping_tax', type='json', auth='none', methods=['POST'], csrf=False)
    def post_mapping_tax(self, **kw):
        try:
            # Auth
            config = request.env['setting.config'].sudo().search([
                ('vit_config_server', '=', 'mc')
            ], limit=1)

            if not config:
                return {'status': 'Failed', 'code': 500, 'message': 'Configuration not found.'}

            uid = request.session.authenticate(
                request.session.db,
                config.vit_config_username,
                config.vit_config_password_api
            )
            if not uid:
                return {'status': 'Failed', 'code': 401, 'message': 'Authentication failed.'}

            env = request.env
            data = request.get_json_data()
            items = data.get('items', [])

            if not isinstance(items, list):
                items = [items]
            if not items:
                return {'status': 'Failed', 'code': 400, 'message': 'No items provided.'}

            created = []
            updated = []
            failed = []

            for item in items:
                company_name    = item.get('company_name')
                warehouse_code  = item.get('warehouse_code')
                tax_code_name   = item.get('tax_code')
                tax_code_0_name = item.get('tax_code_0')

                # Validasi field wajib
                if not company_name:
                    failed.append({'data': item, 'message': "Field 'company_name' is required"})
                    continue
                if not warehouse_code:
                    failed.append({'data': item, 'message': "Field 'warehouse_code' is required"})
                    continue

                try:
                    # Cari company
                    company = env['res.company'].sudo().search([
                        ('name', '=', company_name)
                    ], limit=1)
                    if not company:
                        failed.append({
                            'data': item,
                            'message': f"Company '{company_name}' not found."
                        })
                        continue

                    # Cari warehouse
                    warehouse = env['stock.warehouse'].sudo().search([
                        ('code', '=', warehouse_code),
                        ('company_id', '=', company.id)
                    ], limit=1)
                    if not warehouse:
                        failed.append({
                            'data': item,
                            'message': f"Warehouse code '{warehouse_code}' not found for company '{company_name}'."
                        })
                        continue

                    # Cari tax code (opsional)
                    tax_code = False
                    if tax_code_name:
                        tax_code = env['account.tax'].sudo().search([
                            ('name', '=', tax_code_name),
                            ('company_id', '=', company.id),
                            ('type_tax_use', '=', 'sale')
                        ], limit=1)
                        if not tax_code:
                            failed.append({
                                'data': item,
                                'message': f"Tax code '{tax_code_name}' not found for company '{company_name}'."
                            })
                            continue

                    # Cari tax code 0 (opsional)
                    tax_code_0 = False
                    if tax_code_0_name:
                        tax_code_0 = env['account.tax'].sudo().search([
                            ('name', '=', tax_code_0_name),
                            ('company_id', '=', company.id),
                            ('type_tax_use', '=', 'sale')
                        ], limit=1)
                        if not tax_code_0:
                            failed.append({
                                'data': item,
                                'message': f"Tax code 0 '{tax_code_0_name}' not found for company '{company_name}'."
                            })
                            continue

                    vals = {
                        'company_id':      company.id,
                        'gm_warehouse_id': warehouse.id,
                        'gm_tax_code':     tax_code.id if tax_code else False,
                        'gm_tax_code_0':   tax_code_0.id if tax_code_0 else False,
                    }

                    # Cek existing berdasarkan warehouse (unique)
                    existing = env['mapping.tax'].sudo().search([
                        ('gm_warehouse_id', '=', warehouse.id)
                    ], limit=1)

                    if existing:
                        existing.sudo().with_context(
                            allowed_company_ids=[company.id]
                        ).write(vals)
                        env.cr.commit()

                        updated.append({
                            'id':             existing.id,
                            'company_name':   company.name,
                            'warehouse_code': warehouse.code,
                            'warehouse_name': warehouse.name,
                            'tax_code':       existing.gm_tax_code.name if existing.gm_tax_code else None,
                            'tax_code_0':     existing.gm_tax_code_0.name if existing.gm_tax_code_0 else None,
                            'action':         'updated'
                        })

                    else:
                        rec = env['mapping.tax'].sudo().with_context(
                            allowed_company_ids=[company.id]
                        ).create(vals)
                        env.cr.commit()

                        created.append({
                            'id':             rec.id,
                            'company_name':   company.name,
                            'warehouse_code': warehouse.code,
                            'warehouse_name': warehouse.name,
                            'tax_code':       rec.gm_tax_code.name if rec.gm_tax_code else None,
                            'tax_code_0':     rec.gm_tax_code_0.name if rec.gm_tax_code_0 else None,
                            'action':         'created'
                        })

                except Exception as e:
                    env.cr.rollback()
                    failed.append({
                        'data': item,
                        'message': str(e)
                    })

            return {
                'code':    200 if not failed else 207,
                'status':  'success' if not failed else 'partial_success',
                'message': f"Processed {len(items)} items: {len(created)} created, {len(updated)} updated, {len(failed)} failed",
                'summary': {
                    'total':   len(items),
                    'created': len(created),
                    'updated': len(updated),
                    'failed':  len(failed)
                },
                'created': created,
                'updated': updated,
                'failed':  failed,
            }

        except Exception as e:
            request.env.cr.rollback()
            return {'status': 'Failed', 'code': 500, 'message': f"Server error: {str(e)}"}
        
class POSTItemCategory(http.Controller):

    # Helper function untuk create kategori ber-level
    def get_or_create_category(self, env, category_path):
        names = [x.strip() for x in category_path.split('/')]
        
        parent_id = False
        last_category = None
        full_path = []

        for name in names:
            category = env['product.category'].sudo().search([
                ('name', '=', name),
                ('parent_id', '=', parent_id or False)
            ], limit=1)

            if not category:   # jika belum ada → create
                category = env['product.category'].sudo().create({
                    'name': name,
                    'parent_id': parent_id or False
                })

            parent_id = category.id
            last_category = category
            full_path.append(name)

        return last_category, " / ".join(full_path)


    @http.route('/api/item_category', type='json', auth='none', methods=['POST'], csrf=False)
    def post_item_group(self, **kw):
        try:
            # Authentication
            config = request.env['setting.config'].sudo().search([
                ('vit_config_server', '=', 'mc')
            ], limit=1)

            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}

            uid = request.session.authenticate(
                request.session.db,
                config.vit_config_username,
                config.vit_config_password_api
            )

            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)

            data = request.get_json_data()
            items = data.get('items', [])
            if not isinstance(items, list):
                items = [data]

            created, updated, failed = [], [], []

            for data_item in items:
                try:
                    # CASE 1: input menggunakan category_path = "All / Elektronik / Komponen"
                    if data_item.get('category_path'):
                        category_obj, full_path = self.get_or_create_category(env, data_item['category_path'])

                        created.append({
                            'id': category_obj.id,
                            'name': category_obj.name,
                            'path': full_path,
                            'action': 'created_or_existing'
                        })
                        continue

                    # CASE 2: fallback manual (pakai category_name seperti kode awal)
                    category_name = data_item.get('category_name')
                    if not category_name:
                        failed.append({'data': data_item, 'message': "Missing category_name or category_path"})
                        continue

                    existing_category = env['product.category'].sudo().search([
                        ('name', '=', category_name)
                    ], limit=1)

                    category_data = {'name': category_name}
                    if data_item.get('parent_category_id'):
                        category_data['parent_id'] = data_item.get('parent_category_id')

                    if existing_category:
                        existing_category.write(category_data)
                        updated.append({
                            'id': existing_category.id,
                            'name': existing_category.name,
                            'action': 'updated'
                        })
                    else:
                        category = env['product.category'].sudo().create(category_data)
                        created.append({
                            'id': category.id,
                            'name': category.name,
                            'action': 'created'
                        })

                except Exception as e:
                    failed.append({'data': data_item, 'message': str(e)})

            return {
                'code': 200,
                'status': 'success',
                'created_or_existing': created,
                'updated': updated,
                'failed': failed
            }

        except Exception as e:
            request.env.cr.rollback()
            _logger.error(f"Failed to process Categories: {str(e)}")
            return {'status': "Failed", 'code': 500, 'message': str(e)}
        
class POSTItemPoSCategory(http.Controller):
    @http.route('/api/pos_category', type='json', auth='none', methods=['POST'], csrf=False)
    def post_pos_category(self, **kw):
        try:
            # Authentication
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}
            
            uid = request.session.authenticate(request.session.db, config.vit_config_username, config.vit_config_password_api)
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}
            
            env = request.env(user=request.env.ref('base.user_admin').id)
            
            data = request.get_json_data()
            items = data.get('items', [])
            if not isinstance(items, list):
                items = [data]
            
            created = []  # To store successfully created POS categories
            updated = []  # To store successfully updated POS categories
            failed = []   # To store failed POS categories
            
            # Process each item
            for data_item in items:
                try:
                    category_name = data_item.get('category_name')
                    if not category_name:
                        failed.append({
                            'data': data_item,
                            'message': "Missing required field: category_name",
                            'id': None
                        })
                        continue
                    
                    # Check if POS category exists by name (pos.category tidak memiliki company_id)
                    existing_category = env['pos.category'].sudo().search([
                        ('name', '=', category_name),
                    ], limit=1)
                    
                    category_data = {
                        'name': category_name,
                    }
                    
                    # Add create_date if provided
                    if data_item.get('create_date'):
                        category_data['create_date'] = data_item.get('create_date')
                    
                    if existing_category:
                        # Update existing POS category
                        existing_category.write(category_data)
                        updated.append({
                            'id': existing_category.id,
                            'name': existing_category.name,
                            'action': 'updated'
                        })
                    else:
                        # Create new POS category
                        category_data['create_uid'] = uid
                        category = env['pos.category'].sudo().create(category_data)
                        created.append({
                            'id': category.id,
                            'name': category.name,
                            'action': 'created'
                        })
                        
                except Exception as e:
                    failed.append({
                        'data': data_item,
                        'message': f"Error: {str(e)}",
                        'id': None
                    })
            
            # Return response
            return {
                'code': 200,
                'status': 'success',
                'created_pos_categories': created,
                'updated_pos_categories': updated,
                'failed_pos_categories': failed
            }
            
        except Exception as e:
            request.env.cr.rollback()
            _logger.error(f"Failed to process PoS Categories: {str(e)}")
            return {
                'status': "Failed",
                'code': 500,
                'message': f"Failed to process PoS Categories: {str(e)}"
            }

def _authenticate(env):
    """Shared authentication helper."""
    config = env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
    if not config:
        return None, {'status': "Failed", 'code': 500, 'message': "Configuration not found."}
    uid = request.session.authenticate(request.session.db, config.vit_config_username, config.vit_config_password_api)
    if not uid:
        return None, {'status': "Failed", 'code': 401, 'message': "Authentication failed."}
    return uid, None


def _validate_company(env, company_name):
    """Validate and return company."""
    company = env['res.company'].sudo().search([('name', '=', company_name)], limit=1)
    if not company:
        return None, {
            'status': "Failed", 'code': 400,
            'message': f"Company '{company_name}' not found."
        }
    return company, None


def _validate_locations(env, location_id, location_dest_id, company_id, company_name):
    """Bulk-validate source and destination locations."""
    locations = env['stock.location'].sudo().browse([location_id, location_dest_id])
    loc_map = {loc.id: loc for loc in locations}

    source = loc_map.get(location_id)
    dest = loc_map.get(location_dest_id)

    if not source or not source.exists():
        return None, None, {'status': "Failed", 'code': 400, 'message': f"Source location ID {location_id} not found."}
    if not dest or not dest.exists():
        return None, None, {'status': "Failed", 'code': 400, 'message': f"Destination location ID {location_dest_id} not found."}
    if source.company_id and source.company_id.id != company_id:
        return None, None, {
            'status': "Failed", 'code': 400,
            'message': f"Source location belongs to '{source.company_id.name}', not '{company_name}'."
        }
    if dest.company_id and dest.company_id.id != company_id:
        return None, None, {
            'status': "Failed", 'code': 400,
            'message': f"Destination location belongs to '{dest.company_id.name}', not '{company_name}'."
        }
    return source, dest, None


def _bulk_validate_products(env, move_lines, company_id, company_name):
    """
    Bulk-fetch all products in ONE query.
    Returns (product_map, errors_list).
    product_map = {product_code: product_record}
    """
    product_codes = list({line.get('product_code') for line in move_lines if line.get('product_code')})

    products = env['product.product'].sudo().search([
        ('default_code', 'in', product_codes),
        '|',
        ('company_id', '=', company_id),
        ('company_id', '=', False)
    ])

    product_map = {}
    for p in products:
        if p.default_code not in product_map or p.company_id.id == company_id:
            product_map[p.default_code] = p

    missing = [code for code in product_codes if code not in product_map]
    if missing:
        return None, [{
            'status': "Failed", 'code': 400,
            'message': f"Products not found or not accessible for company '{company_name}': {', '.join(missing)}"
        }]
    return product_map, []


def _validate_move_line_quantities(move_lines):
    """Validate quantities in move lines, return errors list."""
    errors = []
    for idx, line in enumerate(move_lines):
        qty = line.get('product_uom_qty')
        code = line.get('product_code', f'Line {idx+1}')
        if qty is None:
            errors.append(f"{code}: missing quantity")
            continue
        try:
            if float(qty) <= 0:
                errors.append(f"{code}: quantity must be positive")
        except (ValueError, TypeError):
            errors.append(f"{code}: invalid quantity format")
    return errors


class POSTGoodsReceipt(http.Controller):
    @http.route('/api/goods_receipt', type='json', auth='none', methods=['POST'], csrf=False)
    def post_goods_receipt(self, **kw):
        try:
            env = request.env
            uid, auth_error = _authenticate(env)
            if auth_error:
                return auth_error

            data = request.get_json_data()

            # ── Required field checks ──────────────────────────────────────
            company_name = data.get('company_name')
            if not company_name:
                return {'status': "Failed", 'code': 400, 'message': "Field 'company_name' is required."}

            picking_type_name = data.get('picking_type')
            location_id       = data.get('location_id')
            location_dest_id  = data.get('location_dest_id')
            scheduled_date    = data.get('scheduled_date')
            date_done         = data.get('date_done')
            transaction_id    = data.get('transaction_id')
            move_type         = data.get('move_type')
            move_lines        = data.get('move_lines', [])

            # ── Company ───────────────────────────────────────────────────
            company, err = _validate_company(env, company_name)
            if err:
                return err
            company_id = company.id

            # ── Duplicate check ───────────────────────────────────────────
            existing = env['stock.picking'].sudo().search([
                ('vit_trxid', '=', transaction_id),
                ('picking_type_id.name', '=', 'Goods Receipts'),
                ('company_id', '=', company_id)
            ], limit=1)
            if existing:
                return {
                    'code': 400, 'status': 'failed',
                    'message': 'Goods Receipt already exists',
                    'id': existing.id, 'doc_num': existing.name,
                    'company_name': existing.company_id.name
                }

            # ── Picking type ──────────────────────────────────────────────
            picking_type = env['stock.picking.type'].sudo().search([
                ('name', '=', picking_type_name),
                ('default_location_dest_id', '=', location_dest_id),
                ('company_id', '=', company_id)
            ], limit=1)
            if not picking_type:
                return {'status': "Failed", 'code': 400,
                        'message': f"Picking type '{picking_type_name}' not found for company '{company.name}'."}

            # ── Locations ─────────────────────────────────────────────────
            source_loc, dest_loc, err = _validate_locations(
                env, location_id, location_dest_id, company_id, company.name)
            if err:
                return err

            # ── Products & Quantities ─────────────────────────────────────
            if not move_lines:
                return {'status': "Failed", 'code': 400, 'message': "move_lines cannot be empty."}

            qty_errors = _validate_move_line_quantities(move_lines)
            product_map, prod_errors = _bulk_validate_products(env, move_lines, company_id, company.name)

            all_errors = (prod_errors or []) + (["Invalid quantities: " + ", ".join(qty_errors)] if qty_errors else [])
            if all_errors:
                return {'status': "Failed", 'code': 400, 'message': "; ".join(
                    e['message'] if isinstance(e, dict) else e for e in all_errors)}

            # ── Context untuk disable mail/tracking ───────────────────────
            ctx = {
                'tracking_disable': True,
                'mail_notrack': True,
                'mail_notify_force_send': False,
                'no_recompute': True,
            }

            # ── Create picking ────────────────────────────────────────────
            goods_receipt = env['stock.picking'].sudo().with_context(**ctx).create({
                'picking_type_id': picking_type.id,
                'location_id': source_loc.id,
                'location_dest_id': dest_loc.id,
                'move_type': move_type,
                'scheduled_date': scheduled_date,
                'date_done': date_done,
                'vit_trxid': transaction_id,
                'company_id': company_id,
                'create_uid': uid,
            })

            # ── Bulk create move lines ────────────────────────────────────
            move_vals_list = []
            for line in move_lines:
                product = product_map[line['product_code']]
                qty = float(line['product_uom_qty'])
                move_vals_list.append({
                    'name': product.name,
                    'product_id': product.id,
                    'product_uom': product.uom_id.id,
                    'product_uom_qty': qty,
                    'quantity': qty,
                    'picking_id': goods_receipt.id,
                    'location_id': source_loc.id,
                    'location_dest_id': dest_loc.id,
                    'company_id': company_id,
                    'state': 'draft',
                })
            env['stock.move'].sudo().with_context(**ctx).create(move_vals_list)

            # ── Unlink followers & Validate ───────────────────────────────
            goods_receipt.sudo().message_follower_ids.unlink()
            goods_receipt.sudo().with_context(
                **ctx,
                skip_backorder=True,
                immediate_transfer=True,
                skip_subscribe=True,
            ).button_validate()

            return {
                'code': 200, 'status': 'success',
                'message': 'Goods Receipt created and validated successfully',
                'id': goods_receipt.id,
                'doc_num': goods_receipt.name,
                'company_name': goods_receipt.company_id.name
            }

        except Exception as e:
            request.env.cr.rollback()
            _logger.error("Failed to create Goods Receipt: %s", e, exc_info=True)
            return {'status': "Failed", 'code': 500, 'message': f"Failed to create Goods Receipt: {e}"}


class POSTGoodsIssue(http.Controller):
    @http.route('/api/goods_issue', type='json', auth='none', methods=['POST'], csrf=False)
    def post_goods_issue(self, **kw):
        try:
            env = request.env
            uid, auth_error = _authenticate(env)
            if auth_error:
                return auth_error

            data = request.get_json_data()

            # ── Required fields ───────────────────────────────────────────
            required_fields = ['company_name', 'picking_type', 'location_id', 'location_dest_id',
                               'scheduled_date', 'transaction_id', 'move_type', 'move_lines']
            missing_fields = [f for f in required_fields if not data.get(f)]
            if missing_fields:
                return {'status': "Failed", 'code': 400,
                        'message': f"Missing required fields: {', '.join(missing_fields)}"}

            company_name      = data['company_name']
            picking_type_name = data['picking_type']
            location_id       = data['location_id']
            location_dest_id  = data['location_dest_id']
            scheduled_date    = data['scheduled_date']
            date_done         = data.get('date_done')
            transaction_id    = data['transaction_id']
            move_type         = data['move_type']
            move_lines        = data['move_lines']

            # ── Company ───────────────────────────────────────────────────
            company, err = _validate_company(env, company_name)
            if err:
                return err
            company_id = company.id

            # ── Duplicate check ───────────────────────────────────────────
            existing = env['stock.picking'].sudo().search([
                ('vit_trxid', '=', transaction_id),
                ('picking_type_id.name', '=', 'Goods Issue'),
                ('company_id', '=', company_id)
            ], limit=1)
            if existing:
                return {
                    'code': 409, 'status': 'failed',
                    'message': 'Goods Issue already exists',
                    'data': {'id': existing.id, 'doc_num': existing.name,
                             'company_name': existing.company_id.name}
                }

            # ── Picking type ──────────────────────────────────────────────
            picking_type = env['stock.picking.type'].sudo().search([
                ('name', '=', picking_type_name),
                ('default_location_src_id', '=', location_id),
                ('company_id', '=', company_id)
            ], limit=1)
            if not picking_type:
                return {'status': "Failed", 'code': 400,
                        'message': f"Picking type '{picking_type_name}' not found for company '{company.name}'."}

            # ── Locations ─────────────────────────────────────────────────
            source_loc, dest_loc, err = _validate_locations(
                env, location_id, location_dest_id, company_id, company.name)
            if err:
                return err

            # ── Quantity & Products ───────────────────────────────────────
            qty_errors = _validate_move_line_quantities(move_lines)
            product_map, prod_errors = _bulk_validate_products(env, move_lines, company_id, company.name)

            all_errors = (prod_errors or []) + (["Invalid quantities: " + ", ".join(qty_errors)] if qty_errors else [])
            if all_errors:
                return {'status': "Failed", 'code': 400, 'message': "; ".join(
                    e['message'] if isinstance(e, dict) else e for e in all_errors)}

            # ── Context untuk disable mail/tracking ───────────────────────
            ctx = {
                'tracking_disable': True,
                'mail_notrack': True,
                'mail_notify_force_send': False,
                'no_recompute': True,
            }

            # ── Create picking ────────────────────────────────────────────
            gi_vals = {
                'picking_type_id': picking_type.id,
                'location_id': source_loc.id,
                'location_dest_id': dest_loc.id,
                'move_type': move_type,
                'scheduled_date': scheduled_date,
                'vit_trxid': transaction_id,
                'company_id': company_id,
                'create_uid': uid,
            }
            if date_done:
                gi_vals['date_done'] = date_done

            goods_issue = env['stock.picking'].sudo().with_context(**ctx).create(gi_vals)

            # ── Bulk create move lines ────────────────────────────────────
            move_vals_list = []
            for line in move_lines:
                product = product_map[line['product_code']]
                qty = float(line['product_uom_qty'])
                move_vals_list.append({
                    'name': product.name,
                    'product_id': product.id,
                    'product_uom': product.uom_id.id,
                    'product_uom_qty': qty,
                    'quantity': qty,
                    'picking_id': goods_issue.id,
                    'location_id': source_loc.id,
                    'location_dest_id': dest_loc.id,
                    'company_id': company_id,
                    'state': 'draft',
                })
            env['stock.move'].sudo().with_context(**ctx).create(move_vals_list)

            # ── Unlink followers & Validate ───────────────────────────────
            goods_issue.sudo().message_follower_ids.unlink()
            goods_issue.sudo().with_context(
                **ctx,
                skip_backorder=True,
                immediate_transfer=True,
                skip_subscribe=True,
            ).button_validate()

            return {
                'code': 200, 'status': 'success',
                'message': 'Goods Issue created and validated successfully',
                'data': {
                    'id': goods_issue.id,
                    'doc_num': goods_issue.name,
                    'company_name': goods_issue.company_id.name
                }
            }

        except Exception as e:
            request.env.cr.rollback()
            _logger.error("Failed to create Goods Issue: %s", e, exc_info=True)
            return {'status': "Failed", 'code': 500, 'message': f"Failed to create Goods Issue: {e}"}
        

class POSTPurchaseOrderFromSAP(http.Controller):
    @http.route('/api/purchase_order', type='json', auth='none', methods=['POST'], csrf=False)
    def post_purchase_order(self, **kw):
        try:
            # Authentication
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}

            uid = request.session.authenticate(
                request.session.db,
                config.vit_config_username,
                config.vit_config_password_api
            )
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env
            data = request.get_json_data()
            
            # ✅ Cek apakah ini request untuk close PO
            transaction_id = data.get('transaction_id')
            close_po = data.get('close_po')
            
            # ✅ SCENARIO 1: Update PO (Close PO) - hanya butuh transaction_id dan close_po
            if close_po is not None:
                # Validasi required fields untuk close
                if not transaction_id:
                    return {
                        'status': "Failed",
                        'code': 400,
                        'message': "Missing required field: transaction_id"
                    }
                
                # Validasi close_po harus boolean
                if not isinstance(close_po, bool):
                    return {
                        'status': "Failed",
                        'code': 400,
                        'message': "Invalid data: close_po must be a boolean"
                    }
                
                # Cari PO berdasarkan transaction_id
                purchase_order = env['purchase.order'].sudo().search([
                    ('vit_trxid', '=', transaction_id)
                ], limit=1)
                
                if not purchase_order:
                    return {
                        'code': 404,
                        'status': 'error',
                        'message': 'Purchase Order not found',
                        'transaction_id': transaction_id
                    }
                
                # Jika close_po = true, jalankan button_done
                # Jika close_po = true, jalankan button_done
                if close_po:
                    try:
                        purchase_order.button_done()
                        purchase_order.write({'write_uid': uid})
                        
                        # ✅ TAMBAHAN: Auto cancel receipt yang ready
                        picking_ids = env['stock.picking'].sudo().search([
                            ('purchase_id', '=', purchase_order.id),
                            ('state', 'in', ['assigned', 'confirmed', 'waiting'])  # Status yang belum done
                        ])
                        
                        cancelled_receipts = []
                        if picking_ids:
                            for picking in picking_ids:
                                try:
                                    picking.action_cancel()  # Cancel receipt
                                    cancelled_receipts.append(picking.name)
                                    _logger.info(f"Receipt {picking.name} cancelled successfully")
                                except Exception as pick_error:
                                    _logger.warning(f"Failed to cancel receipt {picking.name}: {str(pick_error)}")
                        
                        return {
                            'code': 200,
                            'status': 'success',
                            'message': 'Purchase Order closed successfully',
                            'data': {
                                'id': purchase_order.id,
                                'doc_num': purchase_order.name,
                                'company_name': purchase_order.company_id.name,
                                'transaction_id': transaction_id,
                                'state': purchase_order.state,
                                'close_po': close_po,
                                'receipts_cancelled': cancelled_receipts
                            }
                        }
                    except Exception as e:
                        _logger.error(f"Failed to close PO {purchase_order.name}: {str(e)}")
                        return {
                            'code': 500,
                            'status': 'error',
                            'message': f'Failed to close Purchase Order: {str(e)}',
                            'transaction_id': transaction_id
                        }
                else:
                    # close_po = false, hanya update write_uid
                    purchase_order.write({'write_uid': uid})
                    
                    return {
                        'code': 200,
                        'status': 'success',
                        'message': 'Purchase Order updated successfully',
                        'data': {
                            'id': purchase_order.id,
                            'doc_num': purchase_order.name,
                            'company_name': purchase_order.company_id.name,
                            'transaction_id': transaction_id,
                            'state': purchase_order.state,
                            'close_po': close_po
                        }
                    }
            
            # ✅ SCENARIO 2: Create PO baru - butuh semua field lengkap
            # Validasi input fields yang required untuk create
            required_fields = ['company_name', 'customer_code', 'currency_id', 
                             'date_order', 'transaction_id', 'expected_arrival', 'picking_type', 
                             'location_id', 'order_line']
            missing_fields = [f for f in required_fields if not data.get(f)]
            
            if missing_fields:
                return {
                    'status': "Failed",
                    'code': 400,
                    'message': f"Missing required fields: {', '.join(missing_fields)}"
                }

            company_name = data['company_name']
            customer_code = data['customer_code']
            vendor_reference = data.get('vendor_reference')
            currency_name = data['currency_id']
            date_order = data['date_order']
            expected_arrival = data['expected_arrival']
            picking_type_name = data['picking_type']
            location_id = data['location_id']
            order_line = data['order_line']

            # Validate company
            company = env['res.company'].sudo().search([('name', '=', company_name)], limit=1)
            if not company:
                return {
                    'status': "Failed",
                    'code': 400,
                    'message': f"Company '{company_name}' not found."
                }
            
            company_id = company.id

            # Check duplicate PO
            existing_po = env['purchase.order'].sudo().search([
                ('vit_trxid', '=', transaction_id),
                ('company_id', '=', company_id)
            ], limit=1)

            if existing_po:
                return {
                    'code': 409,
                    'status': 'failed',
                    'message': 'Purchase Order already exists',
                    'data': {
                        'id': existing_po.id,
                        'doc_num': existing_po.name,
                        'company_name': existing_po.company_id.name,
                        'state': existing_po.state
                    }
                }

            # ✅ Validate customer (vendor) - terima partner milik company ATAU shared
            customer = env['res.partner'].sudo().search([
                ('customer_code', '=', customer_code),
                '|',
                ('company_id', '=', company_id),
                ('company_id', '=', False)
            ], limit=1)
            
            if not customer:
                return {
                    'status': "Failed",
                    'code': 400,
                    'message': f"Customer with code '{customer_code}' not found or not accessible for company '{company.name}'."
                }
            
            customer_id = customer.id

            # Validate currency
            currency = env['res.currency'].sudo().search([('name', '=', currency_name)], limit=1)
            if not currency:
                return {
                    'status': "Failed",
                    'code': 400,
                    'message': f"Currency '{currency_name}' not found."
                }
            currency_id = currency.id

            # ✅ Validate picking type dengan company eksplisit
            picking_types = env['stock.picking.type'].sudo().search([
                ('name', '=', picking_type_name),
                ('default_location_dest_id', '=', location_id),
                ('company_id', '=', company_id)
            ], limit=1)

            if not picking_types:
                return {
                    'status': "Failed",
                    'code': 400,
                    'message': f"Picking type '{picking_type_name}' with location_id '{location_id}' not found for company '{company.name}'."
                }

            # ✅ Validate order_line not empty
            if not order_line:
                return {
                    'status': "Failed",
                    'code': 400,
                    'message': "Order lines cannot be empty."
                }

            # ✅ PERBAIKAN: Validate all products - terima produk milik company ATAU shared
            missing_products = []
            invalid_quantities = []
            missing_taxes = []
            
            for idx, line in enumerate(order_line):
                product_code = line.get('product_code')
                product_uom_qty = line.get('product_uom_qty')
                price_unit = line.get('price_unit')
                taxes_name = line.get('taxes_ids')
                
                # Validate required fields in order line
                if not product_code:
                    missing_products.append(f"Line {idx + 1}: missing product_code")
                    continue
                
                if product_uom_qty is None:
                    invalid_quantities.append(f"{product_code}: missing quantity")
                    continue
                
                if price_unit is None:
                    invalid_quantities.append(f"{product_code}: missing price_unit")
                    continue
                
                try:
                    qty = float(product_uom_qty)
                    if qty <= 0:
                        invalid_quantities.append(f"{product_code}: quantity must be positive")
                    
                    price = float(price_unit)
                    if price < 0:
                        invalid_quantities.append(f"{product_code}: price_unit cannot be negative")
                except (ValueError, TypeError):
                    invalid_quantities.append(f"{product_code}: invalid number format")
                    continue
                
                # ✅ PERBAIKAN: Validate product - terima milik company atau shared
                product_id = env['product.product'].sudo().search([
                    ('default_code', '=', product_code),
                    '|',
                    ('company_id', '=', company_id),
                    ('company_id', '=', False)
                ], limit=1)
                
                if not product_id:
                    missing_products.append(product_code)
                
                # Validate tax jika ada
                if taxes_name:
                    tax = env['account.tax'].sudo().search([
                        ('name', '=', taxes_name),
                        ('company_id', '=', company_id)
                    ], limit=1)
                    if not tax:
                        missing_taxes.append(f"{taxes_name} (for product {product_code})")

            # ✅ Consolidated error messages
            errors = []
            if missing_products:
                errors.append(f"Products not found or not accessible for company '{company.name}': {', '.join(missing_products)}")
            if invalid_quantities:
                errors.append(f"Invalid values: {', '.join(invalid_quantities)}")
            if missing_taxes:
                errors.append(f"Taxes not found: {', '.join(missing_taxes)}")
            
            if errors:
                return {
                    'status': "Failed",
                    'code': 400,
                    'message': "; ".join(errors)
                }

            # ✅ PERBAIKAN: Build purchase order lines dengan filter yang sama
            purchase_order_lines = []
            for line in order_line:
                product_code = line.get('product_code')
                product_uom_qty = float(line.get('product_uom_qty'))
                price_unit = float(line.get('price_unit'))
                taxes_name = line.get('taxes_ids')
                vit_line_number_sap = line.get('line_number_sap')

                # ✅ Cari produk yang milik company ini atau shared
                product_id = env['product.product'].sudo().search([
                    ('default_code', '=', product_code),
                    '|',
                    ('company_id', '=', company_id),
                    ('company_id', '=', False)
                ], limit=1)

                po_line = {
                    'name': product_id.name,
                    'product_id': product_id.id,
                    'product_qty': product_uom_qty,
                    'price_unit': price_unit,
                    'vit_line_number_sap': vit_line_number_sap,
                    'product_uom': product_id.uom_id.id,
                }
                
                # Add tax if provided
                if taxes_name:
                    tax = env['account.tax'].sudo().search([
                        ('name', '=', taxes_name),
                        ('company_id', '=', company_id)
                    ], limit=1)
                    po_line['taxes_id'] = [(6, 0, [tax.id])]
                
                purchase_order_lines.append((0, 0, po_line))

            # Create purchase order
            purchase_order = env['purchase.order'].sudo().create({
                'partner_id': customer_id,
                'partner_ref': vendor_reference,
                'currency_id': currency_id,
                'date_order': date_order,
                'date_planned': expected_arrival,
                'vit_trxid': transaction_id,
                'picking_type_id': picking_types.id,
                'company_id': company_id,
                'create_uid': uid,
                'user_id': uid,
                'order_line': purchase_order_lines,
            })

            # Confirm purchase order
            purchase_order.button_confirm()

            # ✅ Update related pickings dengan company yang benar
            picking_ids = env['stock.picking'].sudo().search([('purchase_id', '=', purchase_order.id)])
            if picking_ids:
                for picking in picking_ids:
                    for move in picking.move_ids_without_package:
                        move.product_uom_qty = move.quantity
                    picking.write({
                        'origin': purchase_order.name,
                        'vit_trxid': transaction_id,
                        'company_id': company_id
                    })

            return {
                'code': 200,
                'status': 'success',
                'message': 'Purchase Order created and validated successfully',
                'data': {
                    'id': purchase_order.id,
                    'doc_num': purchase_order.name,
                    'company_name': purchase_order.company_id.name,
                    'transaction_id': transaction_id,
                    'state': purchase_order.state
                }
            }

        except Exception as e:
            request.env.cr.rollback()
            _logger.error(f"Failed to process Purchase Order: {str(e)}", exc_info=True)
            return {
                'status': "Failed",
                'code': 500,
                'message': f"Failed to process Purchase Order: {str(e)}"
            }