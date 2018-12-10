# -*- coding: utf-8 -*-
#  Copyright (c) 2018 - Indexa SRL. (https://www.indexa.do) <info@indexa.do>
#  See LICENSE file for full licensing details.

from odoo import http

# class TemplateModule(http.Controller):
#     @http.route('/template_module/template_module/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/template_module/template_module/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('template_module.listing', {
#             'root': '/template_module/template_module',
#             'objects': http.request.env['template_module.template_module'].search([]),
#         })

#     @http.route('/template_module/template_module/objects/<model("template_module.template_module"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('template_module.object', {
#             'object': obj
#         })