from email.policy import default

from odoo import models, fields, api


class SuppliesRfpProductLine(models.Model):
    _name = 'supplies.rfp.product.line'
    _description = 'Request for Purchase Product Line'
    rfp_id = fields.Many2one('supplies.rfp', string='RFP', required=True, ondelete='cascade', index=True, copy=False)
    product_id = fields.Many2one('product.product', string='Product', required=True,
                                 domain="[('categ_id', 'child_of', parent.product_category_id)]")
    product_name = fields.Char(string='Product Name', related='product_id.name')
    product_image = fields.Binary(string='Product Image', related='product_id.image_1920')
    description = fields.Text(string='Description')
    product_qty = fields.Integer(string='Quantity')
    unit_price = fields.Monetary(string='Price')
    product_uom = fields.Many2one('uom.uom', string='UOM')
    subtotal_price = fields.Monetary(string='Subtotal', compute='_compute_subtotal_price', store=True)
    delivery_charge = fields.Monetary(string='Delivery Charge')
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id)

    @api.depends('product_qty', 'unit_price', 'delivery_charge')
    def _compute_subtotal_price(self):
        for rec in self:
            rec.subtotal_price = (rec.product_qty * rec.unit_price) + rec.delivery_charge

    @api.onchange('product_qty')
    def _onchange_product_qty(self):
        if self.product_qty < 0:
            self.product_qty = 1

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Prevent duplicate product selection across product lines."""
        if self.rfp_id and self.product_id:
            # Get all other selected product IDs
            existing_product_ids = self.rfp_id.product_line_ids.filtered(lambda l: l != self).mapped('product_id.id')
            if self.product_id.id in existing_product_ids:
                self.product_id = False
                return {
                    'warning': {
                        'title': 'Duplicate Product',
                        'message': 'This product is already selected.'
                    }
                }
