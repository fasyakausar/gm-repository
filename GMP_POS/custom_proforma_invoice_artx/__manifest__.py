{
    'name': 'Sale Proforma Custom Amount',
    'version': '1.0',
    'summary': 'Generate proforma invoices with down payment in Odoo Sale Orders.',
    'description': """
Custom Sale Proforma
====================

This module enhances the default Odoo Sale module by allowing users to:
- Set a down payment percentage in the "Other Info" tab of the sale order.
- Print a customized Proforma Invoice showing the Down Payment and Remaining Amount in the footer.

Perfect for businesses needing control over their delivery workflow and payment tracking.

Key Features:
-------------
- Adds a field for Down Payment in Sale Order.
- Custom Proforma Invoice template.
- Footer shows Down Payment and Remaining Amount.
- Helps in dispatch planning and cash flow visibility.
    """,
    'author': 'Areterix Technologies',
    'website': 'https://areterix.com',
    'category': 'Sales',
    'depends': ['base', 'sale'],
    'data': [
        'views/sale_order_views.xml',
        'report/report_proforma_invoice_template.xml',
    ],
    'images': ['static/description/banner.png'],  # Add a banner if uploading to Odoo App Store
    # 'price': 21.0,
    # 'currency': 'USD',
    'live_test_url': 'https://youtu.be/6yH6MRQbOk8',
    'license': 'LGPL-3',
    'installable': True,
    'application': True,
}
