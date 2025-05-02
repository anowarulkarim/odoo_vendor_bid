from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo import http, fields
from odoo import _
from odoo.tools import groupby as groupbyelem
from operator import itemgetter
from odoo.http import request, route
from ..utils import controller_utils as utils
from ..utils import schemas
from ..utils import mail_utils
from ..utils.common import get_descendant_category_ids
from pydantic import ValidationError
from ..utils.mail_utils import get_smtp_server_email, get_reviewers, get_reviewer_emails
from odoo.exceptions import AccessDenied
import base64


class SuppliesPortal(CustomerPortal):
    @http.route(['/my/supplies', '/my/supplies/page/<int:page>'], auth='user', website=True)
    def supplies_portal(self, page=1, sortby=None, search=None, search_in=None, groupby=None, **kw):
        limit = 5
        searchbar_sortings = {
            'date': {'label': 'Newest', 'order': 'date_approve desc'},
            'name': {'label': 'Name', 'order': 'rfp_number'},
        }
        groupby_list = {
            'required_date': {'input': 'required_date', 'label': _('Required Date')},
            'state': {'input': 'state', 'label': _('Status')},
        }
        search_in = search_in or 'name'
        order = searchbar_sortings[sortby]['order'] if sortby else 'date_approve desc'
        groupby = groupby or 'state'
        search_list = {
            'all': {'label': _('All'), 'input': 'all', 'domain': []},
            'name': {'label': _('Name'), 'input': 'rfp_number', 'domain': [('rfp_number', 'ilike', search)]},
        }
        sortby = sortby or 'date'
        search_domain = utils.get_rfp_general_search_domain(request.env)
        search_domain += search_list[search_in]['domain']
        rfp_count = request.env['supplies.rfp'].sudo().search_count(search_domain)
        pager = portal_pager(
            url="/my/supplies",
            url_args={'sortby': sortby, 'search_in': search_in, 'search': search, 'groupby': groupby},
            total=rfp_count,
            page=page,
            step=limit
        )
        rfps = request.env['supplies.rfp'].sudo().search(search_domain, order=order, limit=limit,
                                                         offset=pager['offset'])
        group_by_rfp = groupby_list.get(groupby, {})
        if groupby_list[groupby]['input']:
            rfp_group_list = [{group_by_rfp['input']: i, 'rfps': list(j)} for i, j in
                              groupbyelem(rfps, itemgetter(group_by_rfp['input']))]
        else:
            rfp_group_list = [{'rfps': rfps}]

        return request.render(
            'P1705_VendorBid.portal_supplies_rfp_tree_view',
            {
                'rfps': rfps,
                'page_name': 'rfp_list',
                'pager': pager,
                'searchbar_sortings': searchbar_sortings,
                'searchbar_inputs': search_list,
                'sortby': sortby,
                'search_in': search_in,
                'search': search,
                'groupby': groupby,
                'searchbar_groupby': groupby_list,
                'default_url': '/my/supplies',
                'group_rfps': rfp_group_list
            }
        )

    @http.route('/my/supplies/<string:rfp_number>', auth='user', website=True)
    def supplies_portal_rfp(self, rfp_number, **kw):
        search_domain = utils.get_rfp_general_search_domain(request.env)
        all_rfps = request.env['supplies.rfp'].sudo().search(search_domain)
        search_domain.append(('rfp_number', '=', rfp_number))
        rfp = request.env['supplies.rfp'].sudo().search(search_domain, limit=1)
        rfp_index = all_rfps.ids.index(rfp.id)
        prev_record = all_rfps[rfp_index - 1].rfp_number if rfp_index > 0 else False
        next_record = all_rfps[rfp_index + 1].rfp_number if rfp_index < len(all_rfps) - 1 else False
        success_list = []
        error_list = []
        page_contexts = {}

        if request.httprequest.method == 'POST':
            try:
                partner_id = request.env.user.partner_id
                if partner_id.supplier_rank < 1:
                    raise AttributeError('You are not a supplier.')
                rfq_schema = schemas.PurchaseOrderSchema(
                    **dict(
                        request.httprequest.form.items(),
                        rfp_id=rfp.id,
                        partner_id=partner_id.id,
                        user_id=rfp.review_by.id
                    )
                )
            except ValidationError as e:
                errors = e.errors()
                for error in errors:
                    error_list.append(error['msg'])
            except AttributeError as e:
                error_list.append(str(e))
            else:
                data = rfq_schema.model_dump(exclude_none=True)
                order_line = data.pop('order_line')
                rfq = request.env['purchase.order'].sudo().create(data)
                for line in order_line:
                    line['order_id'] = rfq.id
                    # link taxes_id
                    tax_amount = line.pop('tax')
                    tax_id = False
                    if tax_amount:
                        if ac_tax := request.env['account.tax'].sudo().search([('amount', '=', tax_amount)], limit=1):
                            tax_id = ac_tax.id
                        else:
                            tax_data = {
                                "name": f"{tax_amount}%",
                                "amount": tax_amount,
                                "type_tax_use": "purchase",
                            }
                            ac_tax = request.env['account.tax'].sudo().create(tax_data)
                            tax_id = ac_tax.id
                    if tax_id:
                        line['taxes_id'] = [(4, tax_id)]
                    # create the PO line
                    request.env['purchase.order.line'].sudo().create(line)
                success_list.append('RFQ submitted successfully.')
                # send email to reviewer
                template = request.env.ref('P1705_VendorBid.email_template_model_purchase_order_rfq_submission').sudo()
                email_values = {
                    'email_from': mail_utils.get_smtp_server_email(request.env),
                    'email_to': rfp.create_uid.login,
                    'subject': f'New RFQ Submission for {rfp.rfp_number}',
                }
                contexts = {'rfp_number': rfp.rfp_number, 'company_name': rfq.company_id.name}
                template.with_context(**contexts).send_mail(rfq.id, email_values=email_values)
                page_contexts['submitted_rfq'] = rfq

        if request.env.user.has_group('P1705_VendorBid.group_supplies_requester'):
            template_name = "portal_supplies_rfp_form_view_requester"
        else:
            template_name = "portal_supplies_rfp_form_view"
        return request.render(
            f'P1705_VendorBid.{template_name}',
            {
                'rfp': rfp,
                'page_name': 'rfp_view',
                'success_list': success_list,
                'error_list': error_list,
                'prev_record': "/my/supplies/" + prev_record if prev_record else False,
                'next_record': "/my/supplies/" + next_record if next_record else False,
                **page_contexts
            }
        )

    @http.route(['/my/supplies/rfq', '/my/supplies/rfq/page/<int:page>'], auth='user', website=True)
    def supplies_portal_rfq(self, page=1, sortby=None, search=None, search_in=None, groupby=None, **kw):
        limit = 5
        searchbar_sortings = {
            'date': {'label': 'Newest', 'order': 'create_date desc'},
            'name': {'label': 'Name', 'order': 'name'},
            'state': {'label': 'Status', 'order': 'state desc'},
        }
        search_in = search_in or 'name'
        order = searchbar_sortings[sortby]['order'] if sortby else 'create_date desc'
        groupby = groupby or 'state'
        search_list = {
            'all': {'label': _('All'), 'input': 'all', 'domain': []},
            'name': {'label': _('Name'), 'input': 'name', 'domain': [('name', 'ilike', search)]},
        }
        sortby = sortby or 'date'
        search_domain = [('partner_id', '=', request.env.user.partner_id.id)]
        search_domain += search_list[search_in]['domain']
        rfq_count = request.env['purchase.order'].sudo().search_count(search_domain)
        pager = portal_pager(
            url="/my/supplies/rfq",
            url_args={'sortby': sortby, 'search_in': search_in, 'search': search, 'groupby': groupby},
            total=rfq_count,
            page=page,
            step=limit
        )
        rfqs = request.env['purchase.order'].sudo().search(search_domain, order=order, limit=limit,
                                                           offset=pager['offset'])

        return request.render(
            'P1705_VendorBid.portal_supplies_rfq_tree_view',
            {
                'rfqs': rfqs,
                'page_name': 'rfq_list',
                'pager': pager,
                'searchbar_sortings': searchbar_sortings,
                'searchbar_inputs': search_list,
                'sortby': sortby,
                'search_in': search_in,
                'search': search,
                'default_url': '/my/supplies/rfq',
            }
        )

    @http.route('/my/supplies/rfq/<string:rfq_ref>', auth='user', website=True)
    def supplies_portal_rfq_view(self, rfq_ref, **kw):
        rfq = request.env['purchase.order'].sudo().search(
            [
                ('name', '=', rfq_ref),
                ('partner_id', '=', request.env.user.partner_id.id)
            ]
        )
        return request.render(
            'P1705_VendorBid.portal_supplies_rfq_form_view',
            {
                'rfq': rfq,
                'page_name': 'rfq_detail'
            }
        )

    @http.route(['/my/profile'], auth='user', website=True)
    def portal_partner_profile(self, **kwargs):
        user = request.env.user
        is_partner = user.partner_id.supplier_rank > 0

        if not is_partner:
            # If the user is not part of the supplier group, raise an access denied error
            raise AccessDenied("You do not have the necessary permissions to access this page.")

        partner = request.env.user.partner_id
        return request.render('P1705_VendorBid.portal_partner_profile_view', {
            'partner': partner,
            'page_name': 'vendor_profile'
        })

    @http.route(['/my/supplies/request/rfp', '/my/supplies/request/rfp/<int:category_id>'], auth='user', website=True)
    def supplier_portal_request_for_bid(self, category_id=None, **kw):
        """
        Renders the supplier portal's Request for Proposal (RFP) form
        """

        categories = request.env['product.category'].sudo().search([])
        submitted = kw.get('submitted')

        return request.render('P1705_VendorBid.portal_request_rfp_form', {
            'product_category_ids': categories,
            'selected_category_id': category_id,
            'page_name': 'request_rfp',
            'success': True if submitted else False,
        })

    @http.route(['/my/supplies/category-products-html/'], type='json', auth='none', methods=['POST'])
    def category_prods_html(self, **kwargs):
        """
        Returns the HTML for the products in a selected category.
        """
        param_category_id = kwargs.get('category_id')
        if not param_category_id:
            return utils.format_response('error', 'Invalid category ID')
        category_id = request.env['product.category'].sudo().search([('id', '=', param_category_id)], limit=1)
        descendant_cat_ids = get_descendant_category_ids(category_id)
        product_ids = request.env['product.template'].sudo().search([
            ('categ_id', 'in', descendant_cat_ids),
        ])
        html = utils.render_qweb_template(
            request.env,
            "P1705_VendorBid.portal_product_select_options",
            {"product_ids": product_ids},
        )
        return utils.format_response('success', '', data=html)

    @http.route('/my/supplies/request/rfq/submit', type='http', auth="user", website=True, csrf=True)
    def submit_rfp_form(self, **post):
        """
            Processes the supplier portal RFP form submission.

            - Validates required fields and submitted product lines.
            - Creates a new RFP record in the `supplies.rfp` model if validation passes.
            - Redirects to the RFP page on success or reloads form with errors on failure.

            Parameters:
                **post: Form data, including required date, selected category, and product lines.

            Returns:
                Redirects to success URL if submitted, otherwise re-renders the form with success/error messages.
        """
        error_list = []

        try:
            required_date = post.get('required_date')
            category_id = post.get('product_category_id')
            if not required_date:
                error_list.append("Required Date is mandatory.")
                raise ValueError("Missing required_date")

            # Get product line values
            product_ids = request.httprequest.form.getlist('product')
            descriptions = request.httprequest.form.getlist('description[]')
            quantities = request.httprequest.form.getlist('quantity[]')

            if not product_ids or not descriptions or not quantities:
                error_list.append("At least one product line must be added.")
                raise ValueError("Missing product lines")

            product_lines = []
            for i in range(len(product_ids)):
                if not product_ids[i]:
                    continue
                product_lines.append((0, 0, {
                    'product_id': int(product_ids[i]),
                    'description': descriptions[i],
                    'product_qty': float(quantities[i])
                }))

            if not product_lines:
                error_list.append("No valid product lines were submitted.")
                raise ValueError("No valid product lines")

            # Create RFP
            rfp = request.env['supplies.rfp'].sudo().create({
                'required_date': required_date,
                'product_category_id': category_id,
                'product_line_ids': product_lines,
                'state': 'draft'
            })
            # send email to reviewers
            reviewers = get_reviewers(request.env)
            email_values = {
                'email_from': get_smtp_server_email(request.env),
                'subject': 'New RFP Submitted'
            }
            contexts = {
                'company_name': request.env.company.name,
                'requester_name': request.env.user.name,
                'requester_id': request.env.user.id,
                'rfp_number': rfp.rfp_number,
            }
            for reviewer in reviewers:
                template = request.env.ref('P1705_VendorBid.email_template_requester_submit_rfp').sudo()
                template.with_context(**contexts).send_mail(reviewer.id, email_values=email_values)

            # ✅ Redirect to success page (with URL param)
            return request.redirect('/my/supplies/request/rfq/thank-you')

        except Exception as e:
            error_list.append("Something went wrong while submitting the request. " + str(e))

        return request.render('P1705_VendorBid.portal_request_rfp_form', {
            'error_list': error_list,
            'product_category_ids': request.env['product.category'].sudo().search([]),
            'product_ids': [],
            'page_name': 'request_rfp',
            'selected_category_id': None
        })

    @http.route('/my/requester/registration', type='http', auth="public", website=True, csrf=True)
    def register_requester(self, **post):
        """
        Handles the supplies requester registration form.
        - GET: Displays the registration form.
        - POST: Creates a requester if the email is not already used.
        Redirects after submission to a thank-you page.
        """
        if request.httprequest.method == 'POST':
            name = post.get('name')
            email = post.get('email')
            phone = post.get('phone')
            reason = post.get('reason')
            image_file = post.get('image')

            # Check if requester with this email already exists
            existing = request.env['supplies.requester'].sudo().search([('email', '=', email)], limit=1)
            if existing:
                return request.redirect('/my/requester/registration?error=exists')

            # Process image if uploaded
            profile_picture = None
            if image_file and hasattr(image_file, 'read'):
                profile_picture = base64.b64encode(image_file.read())

            # Create the requester
            requester = request.env['supplies.requester'].sudo().create({
                'name': name,
                'email': email,
                'phone': phone,
                'reason': reason,
                'profile_picture': profile_picture,
                'state': 'requested'
            })

            # send email to reviewers
            reviewers = get_reviewers(request.env)
            email_values = {
                'email_from': get_smtp_server_email(request.env),
                'subject': 'New Requester Registered'
            }
            contexts = {
                'company_name': request.env.company.name,
                'requester_name': requester.name,
                'requester_id': requester.id,
            }
            for reviewer in reviewers:
                template = request.env.ref('P1705_VendorBid.email_template_requester_registration').sudo()
                template.with_context(**contexts).send_mail(reviewer.id, email_values=email_values)

            # ✅ Redirect to a proper thank-you page
            return request.redirect('/my/requester/registration/thank-you')

        # GET Request (form display)
        error_list = []
        if request.params.get('error') == 'exists':
            error_list.append("Requester with this email already exists.")

        return request.render('P1705_VendorBid.portal_supplies_requester_registration_form_view', {
            'page_name': 'requester_registration',
            'error_list': error_list,
        })

    @http.route(['/my/account/edit'], type='http', auth='user', website=True, methods=['GET', 'POST'])
    def portal_partner_profile_edit(self, **kwargs):
        user = request.env.user
        is_partner = user.partner_id.supplier_rank > 0

        if not is_partner:
            raise AccessDenied("You do not have the necessary permissions to access this page.")

        partner = http.request.env.user.partner_id
        categories = request.env['product.category'].sudo().search([])
        partner_data = partner.read()[0]

        # Add the product category ID to partner data for comparison
        partner_data['product_category_id'] = partner.product_category_id.id if partner.product_category_id else ''

        if http.request.httprequest.method == 'GET':
            return http.request.render('P1705_VendorBid.portal_partner_profile_edit', {
                'partner': partner,
                'error': {},
                'values': partner_data,
                'categories': categories,
                'page_name': 'edit_details'
            })
        else:
            form_data = http.request.httprequest.form.to_dict()
            files = http.request.httprequest.files.to_dict()
            exclude_fields = ['csrf_token','submit']

            for ex_fld in exclude_fields:
                if ex_fld in form_data:
                    form_data.pop(ex_fld)

            # Track changes: Create a dictionary of only changed fields
            changed_data = {}
            for field, value in form_data.items():
                # Compare string representations (or specific conversions if needed)
                if str(partner_data.get(field, '')) != value:
                    changed_data[field] = value
            for field, file in files.items():
                if file:
                    changed_data[field] = file

            # Proceed only if there are changes
            if not changed_data:
                return http.request.redirect('/my/profile?message=no_data_change')

            try:
                # Validate only the changed fields
                edit_schema = schemas.EditProfileSchema(**changed_data)
            except ValidationError as e:
                errors = {error['loc'][0]: error['msg'] for error in e.errors()}
                error_html = utils.render_registration_error_html(request.env, e.errors())
                return http.request.render('P1705_VendorBid.portal_partner_profile_edit', {
                    'partner': partner,
                    'error': errors,
                    'values': form_data,
                    'categories': categories,
                    'page_name': 'edit_details',
                    'error_html': error_html,
                })

            # Process data if validation passes
            data = edit_schema.model_dump(exclude_unset=True)
            requested = request.env['partner.edit.request'].sudo().search([
                ('partner_id', '=', partner.id),
                ('state', '=', 'pending')
            ], limit=1)

            if requested:
                return http.request.redirect('/my/profile?message=requested')

            reviewers = get_reviewers(request.env)
            email_values = {
                'email_from': get_smtp_server_email(request.env),
            }
            contexts = {
                'company_name': partner.name,
                'submission_date': fields.Date.today().strftime('%Y-%m-%d'),
            }
            data['partner_id'] = partner.id

            http.request.env['partner.edit.request'].sudo().create(data)
            for reviewer in reviewers:
                template = request.env.ref('P1705_VendorBid.email_template_partner_edit_request').sudo()
                template.with_context(**contexts).send_mail(reviewer.id, email_values=email_values)

            return http.request.redirect('/my/profile?message=success')

    @http.route('/my/supplies/request/rfq/thank-you', type='http', auth="user", website=True)
    def rfp_thank_you_page(self):
        return request.render('P1705_VendorBid.portal_rfp_thank_you', {
            'page_name': 'success',
        })

    @http.route('/my/requester/registration/thank-you', type='http', auth="public", website=True)
    def requester_thank_you_page(self):
        return request.render('P1705_VendorBid.portal_requester_thank_you', {
            'page_name': 'success',
        })
