# api_utils.py
import json
from odoo import http, _
import werkzeug.exceptions

def check_authorization():
    """Memeriksa header Authorization dengan password di setting.config (server='mc')."""
    request_auth_header = http.request.httprequest.headers.get('Authorization')
    if not request_auth_header:
        raise werkzeug.exceptions.Unauthorized(_('Authorization header not found.'))

    config_record = http.request.env['setting.config'].sudo().search([
        ('vit_config_server', '=', 'mc')
    ], limit=1)

    if not config_record or not config_record.vit_config_password:
        raise werkzeug.exceptions.Unauthorized(_('No configuration found.'))

    if request_auth_header != config_record.vit_config_password:
        raise werkzeug.exceptions.Unauthorized(_('Invalid authorization header.'))


def get_authenticated_env(server_key='mc'):
    """
    Cari user berdasarkan vit_config_username di setting.config (server_key),
    lalu kembalikan environment dengan user tersebut.
    Raise werkzeug.exceptions.Unauthorized jika gagal.
    """
    config = http.request.env['setting.config'].sudo().search([
        ('vit_config_server', '=', server_key)
    ], limit=1)

    if not config:
        raise werkzeug.exceptions.Unauthorized(_('Configuration not found.'))

    user = http.request.env['res.users'].sudo().search([
        ('login', '=', config.vit_config_username),
        ('active', '=', True),
    ], limit=1)

    if not user:
        raise werkzeug.exceptions.Unauthorized(_('Authentication failed. User not found.'))

    return http.request.env(user=user.id)


def paginate_records(model, domain, pageSize, page):
    pageSize = int(pageSize)
    page = max(1, int(page))
    offset = pageSize * (page - 1)
    total_records = http.request.env[model].sudo().search_count(domain)
    records = http.request.env[model].sudo().search(domain, limit=pageSize, offset=offset)
    return records, total_records


def serialize_response(data, total_records, total_pages):
    response_data = {
        'status': 200,
        'message': 'success',
        'data': data,
        'total_records': total_records,
        'total_pages': total_pages,
    }
    return werkzeug.wrappers.Response(
        status=200,
        content_type='application/json; charset=utf-8',
        response=json.dumps(response_data)
    )


def serialize_error_response(error_description):
    return werkzeug.wrappers.Response(
        status=400,
        content_type='application/json; charset=utf-8',
        response=json.dumps({
            'error': 'Error',
            'error_descrip': error_description,
        })
    )