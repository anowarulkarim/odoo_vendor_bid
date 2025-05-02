from odoo import models, fields, api,_
from odoo.exceptions import ValidationError
from ..utils.mail_utils import get_smtp_server_email

class SuppliesRequester(models.Model):
    _name = 'supplies.requester'
    _inherit = ['mail.thread']
    _description = 'Requester'

    name = fields.Char(string='Name')
    email = fields.Char(string='Email')
    phone= fields.Char(string='Phone')
    profile_picture = fields.Image()
    reason = fields.Text(string='Reason')
    state = fields.Selection([
        ('requested', 'Requested'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Status', readonly=True, copy=False, index=True, tracking=True, default='requested')

    def action_approve(self):
        portal_group = self.env.ref('base.group_portal')
        requester_group = self.env.ref('P1705_VendorBid.group_supplies_requester')

        for rec in self:
            if not rec.email or not rec.phone:
                raise ValidationError(_("Email and phone are required to create a user."))

            # Check if a user already exists with this email
            existing_user = self.env['res.users'].search([('login', '=', rec.email)], limit=1)
            if existing_user:
                raise ValidationError(_("A user with this email already exists."))

            # Create user
            user = self.env['res.users'].sudo().create({
                'name': rec.name,
                'login': rec.email,
                'email': rec.email,
                'password': rec.email,
                'active': True,
            })
            user.write({'groups_id': [(5, 0, 0), (4, portal_group.id), (4, requester_group.id)]})

            # Update state to approved
            rec.state = 'approved'
            email_values = {
                'email_from': get_smtp_server_email(self.env),
                'email_to': self.email,
                'subject': f'Requester Registration Approved',
            }
            contexts = {
                "email": self.email,
                "password": self.email,
            }

            template = self.env.ref('P1705_VendorBid.email_template_model_supplies_requester_approved').sudo()
            template.with_context(**contexts).sudo().send_mail(self.id, email_values=email_values)


    def action_reject(self):
        self.state = 'rejected'
        email_values = {
            'email_from': get_smtp_server_email(self.env),
            'email_to': self.email,
            'subject': f'Requester Registration Rejected',
        }
        contexts = {}
        template = self.env.ref('P1705_VendorBid.email_template_model_supplies_requester_rejected').sudo()
        template.with_context(**contexts).sudo().send_mail(self.id, email_values=email_values)

    def _cron_delete_rejected_requesters(self):
        rejected_records = self.search([('state', '=', 'rejected')])
        rejected_records.unlink()
