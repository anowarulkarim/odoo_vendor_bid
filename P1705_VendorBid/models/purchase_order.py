from logging import exception

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    rfp_id = fields.Many2one('supplies.rfp', string='RFP', index=True, copy=False)
    warrenty_period = fields.Integer(string='Warrenty Period (in months)')
    score = fields.Float(string='Score', default=0)
    system_score = fields.Float(string='System Score', compute='_compute_system_score')
    recommended = fields.Boolean(string='Recommended', default=False)
    last_changed_status_date = fields.Datetime(string='Last Updated Date of RFQ Status',
                                           compute='_compute_last_changed_status_date', store=True)

    @api.depends('state')
    def _compute_last_changed_status_date(self):
        for rfq in self:
            rfq.last_changed_status_date = fields.Date.today()

    def action_accept(self):
        self.rfp_id.write(
            {'state': 'accepted', 'approved_supplier_id': self.partner_id.id, 'date_accept': fields.Date.today()})
        self.button_confirm()
        # updating RFP product line prices
        for line in self.rfp_id.product_line_ids:
            rfq_line = self.order_line.filtered(lambda x: x.product_id == line.product_id)
            line.write({
                'unit_price': rfq_line.price_unit,
                'delivery_charge': rfq_line.delivery_charge,
            })
        # cancelling other RFQs
        other_rfqs = self.env['purchase.order'].search(
            [
                ('rfp_id', '=', self.rfp_id.id),
                ('id', '!=', self.id),
            ]
        )
        other_rfqs.button_cancel()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'supplies.rfp',
            'view_mode': 'form',
            'res_id': self.rfp_id.id,
            'target': 'current',
        }

    @api.constrains('recommended')
    def _check_recommended(self):
        for order in self:
            if order.recommended:
                existing_recommendation = self.env['purchase.order'].search(
                    [
                        ('recommended', '=', True),
                        ('rfp_id', '=', order.rfp_id.id),
                        ('partner_id', '=', order.partner_id.id),
                        ('id', '!=', order.id),
                    ]
                )
                if len(existing_recommendation):
                    raise UserError(
                        f'The supplier {order.partner_id.name} is recommended multiple times for the same RFP.')

    @api.model
    def get_purchase_order_sudo(self, domain, fields):
        return self.sudo().search_read(domain, fields)

    @api.model
    def write(self, vals):
        if 'score' in vals and vals['score'] is not None and vals['score'] < 0:
            raise ValidationError(_("Score of this RFQ can not be negative"))
        return super(PurchaseOrder, self).write(vals)

    @api.depends('order_line.price_unit', 'order_line.delivery_charge', 'warrenty_period')
    def _compute_system_score(self):
        for order in self:
            if not order.order_line:
                order.system_score = 0

            price = [line.price_unit for line in order.order_line]
            deliveries = [line.delivery_charge for line in order.order_line]
            warranty = order.warrenty_period or 0

            sum_price = sum(price)
            sum_delivery = sum(deliveries)

            max_price, max_delivery, max_warranty = 100000000, 1000000, 100

            normalized_price = min(sum_price / max_price, 1.0)
            normalized_delivery = min(sum_delivery / max_delivery, 1.0)
            normalized_warranty = min(warranty / max_warranty, 1.0)

            order.system_score = 100 * round(
                0.4 * (1 - normalized_price) +
                0.3 * (1 - normalized_delivery) +
                0.3 * normalized_warranty, 3)