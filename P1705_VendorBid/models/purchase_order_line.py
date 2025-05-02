from odoo import models, fields, api

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    delivery_charge = fields.Monetary(string='Delivery Charge')
    product_name = fields.Char(string='Product Name', related='product_id.name')
    product_image = fields.Binary(string='Product Image', related='product_id.image_1920')
    rfp_id = fields.Many2one('supplies.rfp', related="order_id.rfp_id")

