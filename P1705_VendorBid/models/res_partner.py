from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'
    company_category_type = fields.Selection(
        [
            ('LLC', 'LLC'),
            ('PLC', 'PLC'),
            ('Limited', 'Limited'),
            ('Partnership', 'Partnership'),
            ('Sole Proprietorship', 'Sole Proprietorship'),
            ('Others', 'Others'),
        ]
    )
    product_category_id = fields.Many2one("product.category", string="Product Category")
    trade_license_number = fields.Char(string='Trade License Number')
    commencement_date = fields.Date(string='Commencement Date')
    expiry_date = fields.Date(string='Expiry Date')
    trade_license_doc = fields.Binary(string='Trade License Document')
    # certification fields
    certification_name = fields.Char(string='Certification')
    certificate_number = fields.Char(string='Certificate Number')
    certifying_body = fields.Char(string='Certifying Body')
    certification_award_date = fields.Date(string='Certification Award Date')
    certification_expiry_date = fields.Date(string='Certification Expiry Date')
    # docs
    certificate_of_incorporation_doc = fields.Binary(string='Certificate of Incorporation Document')
    certificate_of_good_standing_doc = fields.Binary(string='Certificate of Good Standing Document')
    establishment_card_doc = fields.Binary(string='Establishment Card Document')
    vat_tax_certificate_doc = fields.Binary(string='VAT Tax Certificate Document')
    memorandum_of_association_doc = fields.Binary(string='Memorandum of Association Document')
    identification_of_authorised_person_doc = fields.Binary(string='Identification of Authorized Person Document')
    bank_letter_doc = fields.Binary(string='Bank Letter Document')
    past_2_years_financial_statement_doc = fields.Binary(string='Past 2 Years Financial Statement Document')
    other_certification_doc = fields.Binary(string='Other Certification Document')
    company_stamp = fields.Binary(string='Company Stamp')
    # signature fields
    signatory_name = fields.Char(string='Signatory')
    authorized_signatory_name = fields.Char(string='Authorized Signatory')
    date_registration = fields.Datetime(string='Date of Registration')

