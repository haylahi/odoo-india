# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import time
import datetime
from openerp.osv import fields, osv
from openerp import netsvc
import openerp.addons.decimal_precision as dp
from openerp.tools.translate import _
from openerp.osv.orm import browse_record, browse_null

class stock_picking_in(osv.osv):
    _inherit = "stock.picking.in"
    _columns = {
        'lr_no': fields.char("LR No",size=64),
        'lr_date': fields.date("LR Date"),
        'transporter':fields.char("Transporter",size=256),
        'hpressure':fields.integer("HPressure"),
        'dest_from': fields.char("Destination From",size=64),
        'dest_to': fields.char("Destination To",size=64),
        'lab_no':fields.integer("Lab No"),
        'gp_no': fields.integer("Gate Pass No"),
        'gp_year': fields.char("GP Year",size=64),
        'series_id': fields.many2one("product.order.series",'Series'),
        'remark1': fields.char("Remark1",size=256),
        'remark2': fields.char("remark2",size=256),
        'case_code': fields.boolean("Cash Code"),
        'challan_no': fields.char("Challan Number",size=256),
        'despatch_mode': fields.selection([('person','By Person'),
                                           ('scooter','By Scooter'),
                                           ('tanker','By Tanker'),
                                           ('truck','By Truck'),
                                           ('auto_rickshaw','By Auto Rickshaw'),
                                           ('loading_rickshaw','By Loading Rickshaw'),
                                           ('tempo','By Tempo'),
                                           ('metador','By Metador'),
                                           ('rickshaw_tempo','By Rickshaw Tempo'),
                                           ('cart','By Cart'),
                                           ('cycle','By Cycle'),
                                           ('pedal_rickshaw','By Pedal Rickshaw'),
                                           ('car','By Car'),
                                           ('post_parcel','By Post Parcel'),
                                           ('courier','By Courier'),
                                           ('tractor','By Tractor'),
                                           ('hand_cart','By Hand Cart'),
                                           ('camel_cart','By Camel Cart'),
                                           ('others','Others'),],"Despatch Mode"),
        'other_dispatch': fields.char("Other Dispatch",size=256),
            
    }
stock_picking_in()

class purchase_order_line(osv.Model):
    _inherit = 'purchase.order.line'
    
    def _amount_line(self, cr, uid, ids, prop, arg, context=None):
        res = super(purchase_order_line, self)._amount_line(cr, uid, ids, prop, arg, context=context)
        cur_obj=self.pool.get('res.currency')
        tax_obj = self.pool.get('account.tax')
        for line in self.browse(cr, uid, ids, context=context):
            res[line.id] -= (res[line.id] * line.discount) / 100
            taxes = tax_obj.compute_all(cr, uid, line.taxes_id, res[line.id], 1, line.product_id, line.order_id.partner_id)
            cur = line.order_id.pricelist_id.currency_id
            res[line.id] = cur_obj.round(cr, uid, cur, taxes['total'])
        return res

    _columns = {
        'discount': fields.float('Discount'),
        'price_subtotal': fields.function(_amount_line, string='Subtotal', digits_compute= dp.get_precision('Account')),
        'person': fields.integer('Person',help="Number of Person work for this task"),
        'contract': fields.related('order_id', 'contract', type='boolean', relation='purchase.order', string='Contract', store=True, readonly=True),
                }
purchase_order_line()
class purchase_requisition(osv.osv):
    _inherit = "purchase.requisition"
    _order = "name desc"
    _defaults = {
                 'exclusive': 'exclusive',
    }
purchase_requisition()

class purchase_requisition_partner(osv.osv_memory):
    _inherit = "purchase.requisition.partner"
    _columns = {
        'po_series_id': fields.many2one('product.order.series', 'PO Series'),
    }
    def create_order(self, cr, uid, ids, context=None):
        active_ids = context and context.get('active_ids', [])
        data =  self.browse(cr, uid, ids, context=context)[0]
        context.update({'po_order_series':data.po_series_id or False})
        qu_id = self.pool.get('purchase.requisition').make_purchase_order(cr, uid, active_ids, data.partner_id.id, context=context)
        if qu_id:
            self.pool.get('purchase.order').write(cr,uid,qu_id[active_ids[0]],{'po_series_id':data.po_series_id.id or False})
        return {'type': 'ir.actions.act_window_close'}    
purchase_requisition_partner()

class purchase_order(osv.Model):
    _inherit = 'purchase.order'

#    def create_series_sequence(self, cr, uid, vals, context=None):
#        series_obj = self.pool.get('product.order.series')
#        type_name= series_obj.browse(cr,uid,vals['po_series_id']).code
#        type = self.pool.get('ir.sequence.type').create(cr,uid,{'name':'maize'+type_name,'code':type_name})
#        code = self.pool.get('ir.sequence.type').browse(cr,uid,type).code
#        seq = {
#            'name': series_obj.browse(cr,uid,vals['po_series_id']).code,
#            'implementation':'standard',
#            'prefix': series_obj.browse(cr,uid,vals['po_series_id']).code+"/",
#            'padding': 4,
#            'number_increment': 1,
#            'code':code
#        }
#        if 'company_id' in vals:
#            seq['company_id'] = vals['company_id']
#        return self.pool.get('ir.sequence').create(cr, uid, seq)

    def _amount_all(self, cr, uid, ids, field_name, arg, context=None):
        res = {}
        amount_untaxed = 0
        cur_obj=self.pool.get('res.currency')
        for order in self.browse(cr, uid, ids, context=context):
            res[order.id] = {
                'amount_untaxed': 0.0,
                'amount_tax': 0.0,
                'amount_total': 0.0,
                'other_charges': 0.0,
            }
            val = val1 = 0.0
            cur = order.pricelist_id.currency_id
            for line in order.order_line:
                val1 += line.price_subtotal
                amount_untaxed = val1
                for c in self.pool.get('account.tax').compute_all(cr, uid, line.taxes_id, line.price_subtotal, 1, line.product_id, order.partner_id)['taxes']:
                    val += c.get('amount', 0.0)
            other_charge = order.package_and_forwording  - (order.commission + order.other_discount)
            res[order.id]['amount_tax']=cur_obj.round(cr, uid, cur, val)
            res[order.id]['amount_untaxed']=cur_obj.round(cr, uid, cur, val1)
            res[order.id]['other_charges'] = cur_obj.round(cr, uid, cur, other_charge)
            if order.insurance_type == order.freight_type:
                if order.insurance_type == 'fix':
                    amount_untaxed += order.insurance
                    amount_untaxed += order.freight
                else:
                    if order.insurance != 0:
                        amount_untaxed += (amount_untaxed * order.insurance) / 100
                    if order.freight != 0:
                        amount_untaxed += (amount_untaxed * order.freight) / 100
            else:
                if order.insurance_type == 'fix' and order.freight_type == 'percentage':
                    amount_untaxed += order.insurance
                    if order.freight != 0:
                        amount_untaxed += (amount_untaxed * order.freight) / 100
                elif order.insurance_type == 'include':
                    if order.freight_type == 'percentage':
                        amount_untaxed += (amount_untaxed * order.freight) / 100
                    else:
                        amount_untaxed += order.freight
                elif order.freight_type == 'include':
                    if order.insurance_type == 'percentage':
                        amount_untaxed += (amount_untaxed * order.insurance) / 100
                    else:
                        amount_untaxed += order.insurance
                else:
                    if order.insurance != 0:
                        amount_untaxed += (amount_untaxed * order.insurance) / 100
                    amount_untaxed += order.freight
            res[order.id]['amount_total']= amount_untaxed + res[order.id]['amount_tax'] + res[order.id]['other_charges']
        return res

    def _get_order(self, cr, uid, ids, context=None):
        result = {}
        for line in self.pool.get('purchase.order.line').browse(cr, uid, ids, context=context):
            result[line.order_id.id] = True
        return result.keys()
    
    _columns = {
        'package_and_forwording': fields.float('Packing & Forwarding', states={'confirmed':[('readonly',True)], 'approved':[('readonly',True)],'done':[('readonly',True)]}),
        'insurance': fields.float('Insurance',  states={'confirmed':[('readonly',True)], 'approved':[('readonly',True)],'done':[('readonly',True)]}),
        'commission': fields.float('Commission', states={'confirmed':[('readonly',True)], 'approved':[('readonly',True)],'done':[('readonly',True)]}),
        'other_discount': fields.float('Other Discount', states={'confirmed':[('readonly',True)], 'approved':[('readonly',True)],'done':[('readonly',True)]}),
        'delivey': fields.char('Ex. GoDown / Mill Delivey',size=50, states={'confirmed':[('readonly',True)], 'approved':[('readonly',True)],'done':[('readonly',True)]}),
        'po_series_id': fields.many2one('product.order.series', 'PO Series', states={'confirmed':[('readonly',True)], 'approved':[('readonly',True)],'done':[('readonly',True)]}),
        'amount_untaxed': fields.function(_amount_all, digits_compute= dp.get_precision('Account'), string='Untaxed Amount',
            store={
                'purchase.order': (lambda self, cr, uid, ids, c={}: ids, ['excies_ids', 'vat_ids', 'insurance', 'insurance_type', 'freight_type','freight','package_and_forwording','commission','other_discount'], 10),
                'purchase.order.line': (_get_order, None, 10),
            }, multi="sums", help="The amount without tax", track_visibility='always'),
        'amount_tax': fields.function(_amount_all, digits_compute= dp.get_precision('Account'), string='Taxes',
            store={
                'purchase.order': (lambda self, cr, uid, ids, c={}: ids, ['excies_ids', 'vat_ids', 'insurance', 'insurance_type', 'freight_type','freight','package_and_forwording','commission','other_discount'], 10),
                'purchase.order.line': (_get_order, None, 10),
            }, multi="sums", help="The tax amount"),
        'amount_total': fields.function(_amount_all, digits_compute= dp.get_precision('Account'), string='Total',
            store={
                'purchase.order': (lambda self, cr, uid, ids, c={}: ids, ['excies_ids', 'vat_ids', 'insurance', 'insurance_type', 'freight_type','freight','package_and_forwording','commission','other_discount'], 10),
                'purchase.order.line': (_get_order, None, 10),
            }, multi="sums",help="The total amount"),
        'other_charges': fields.function(_amount_all, digits_compute= dp.get_precision('Account'), string='Other Charges',
            store={
                'purchase.order': (lambda self, cr, uid, ids, c={}: ids, ['excies_ids', 'vat_ids', 'insurance', 'insurance_type', 'freight_type','freight','package_and_forwording','commission','other_discount'], 10),
                'purchase.order.line': (_get_order, None, 10),
            }, multi="sums",help="The other charge"),
        'excies_ids': fields.many2many('account.tax', 'purchase_order_exices', 'exices_id', 'tax_id', 'Excise', states={'confirmed':[('readonly',True)], 'approved':[('readonly',True)],'done':[('readonly',True)]}),
        'vat_ids': fields.many2many('account.tax', 'purchase_order_vat', 'vat_id', 'tax_id', 'VAT', states={'confirmed':[('readonly',True)], 'approved':[('readonly',True)],'done':[('readonly',True)]}),
        'freight': fields.float('Freight', states={'confirmed':[('readonly',True)], 'approved':[('readonly',True)],'done':[('readonly',True)]}),
        'insurance_type': fields.selection([('fix', 'Fix Amount'), ('percentage', 'Percentage (%)'), ('include', 'Include in price')], 'Type', states={'confirmed':[('readonly',True)], 'approved':[('readonly',True)],'done':[('readonly',True)]}),
        'freight_type': fields.selection([('fix', 'Fix Amount'), ('percentage', 'Percentage (%)'), ('include', 'Include in price')], 'Type', required=True, states={'confirmed':[('readonly',True)], 'approved':[('readonly',True)],'done':[('readonly',True)]}),
        'payment_term_id': fields.many2one('account.payment.term', 'Payment Term', states={'confirmed':[('readonly',True)], 'approved':[('readonly',True)],'done':[('readonly',True)]}),
        'service_ids': fields.many2many('account.tax', 'purchase_order_service', 'service_id', 'tax_id', 'Service Tax', states={'confirmed':[('readonly',True)], 'approved':[('readonly',True)],'done':[('readonly',True)]}),
        'voucher_id': fields.many2one('account.voucher', 'Payment', states={'confirmed':[('readonly',True)], 'approved':[('readonly',True)],'done':[('readonly',True)]}),
    }

    _defaults = {
        'insurance_type': 'fix',
        'freight_type': 'fix'
     }
    
    def search(self, cr, user, args, offset=0, limit=None, order=None, context=None, count=False):
        if order is None:
            self._order = 'amount_total'
        else:
            self._order = 'name DESC'
        return super(purchase_order, self).search(cr, user, args, offset, limit, order, context, count)
    
#    def create(self, cr, uid, vals, context=None):
#        series_obj = self.pool.get('product.order.series')
#        if vals.get('name','/')=='/':
#            if vals.get('po_series_id'):
#                series_code =  series_obj.browse(cr,uid,vals['po_series_id']).code
#                if not self.pool.get('ir.sequence').search(cr,uid,[('name','=',series_code)]):
#                    seqq = self.create_series_sequence(cr,uid,vals,context)
#                vals['name'] = self.pool.get('ir.sequence').get(cr, uid, series_code) or '/'
#        order =  super(purchase_order, self).create(cr, uid, vals, context=context)
#        return order
    
    def write(self, cr, uid, ids, vals, context=None):
#        series_obj = self.pool.get('product.order.series')
#        if vals.get('po_series_id'):
#            series_code =  series_obj.browse(cr,uid,vals['po_series_id']).code
#            if not self.pool.get('ir.sequence').search(cr,uid,[('name','=',series_code)]):
#                seqq = self.create_series_sequence(cr,uid,vals,context)
#            vals['name'] = self.pool.get('ir.sequence').get(cr, uid, series_code) or '/'
        
        line_obj = self.pool.get('purchase.order.line')
        if isinstance(ids, (int, long)):
            ids = [ids]
        for order in self.browse(cr, uid, ids, context=context):
            excies_ids = [excies_id.id for excies_id in order.excies_ids]
            vat_ids = [vat_id.id for vat_id in order.vat_ids]
            service_ids = [service_id.id for service_id in order.service_ids]
            if ('excies_ids' in vals) and ('vat_ids' in vals):
                excies_ids = vals.get('excies_ids') and vals.get('excies_ids')[0][2] or []
                vat_ids = vals.get('vat_ids') and vals.get('vat_ids')[0][2] or []
            if 'excies_ids' in vals and 'vat_ids' not in vals:
                excies_ids = vals.get('excies_ids') and vals.get('excies_ids')[0][2] or []
                vat_ids = [vat_id.id for vat_id in order.vat_ids]
            if 'vat_ids' in vals and 'excies_ids' not in vals:
                excies_ids = [excies_id.id for excies_id in order.excies_ids]
                vat_ids = vals.get('vat_ids') and vals.get('vat_ids')[0][2] or []
            if 'service_ids' in vals:
                vat_ids = vals.get('service_ids') and vals.get('service_ids')[0][2] or []
            for line in order.order_line:
                line_obj.write(cr, uid, [line.id], {'taxes_id': [(6, 0, excies_ids + vat_ids+ service_ids)]}, context=context)
        return super(purchase_order, self).write(cr, uid, ids, vals, context=context)

    def onchange_reset(self, cr, uid, ids, insurance_type, freight_type):
        dict = {}
        if insurance_type == 'include':
            dict.update({'insurance': 0.0})
        if freight_type == 'include':
            dict.update({'freight': 0.0})
        return {'value': dict}

    def action_invoice_create(self, cr, uid, ids, context=None):
        invoice_obj = self.pool.get('account.invoice')
        invoice_id = super(purchase_order, self).action_invoice_create(cr, uid, ids, context=context)
        order = self.browse(cr, uid, ids[0], context=context)
        invoice_obj.write(cr, uid, [invoice_id], {'freight':order.freight, 'insurance':order.insurance, 'other_charges':order.other_charges}, context=context)
        invoice_obj.button_compute(cr, uid, [invoice_id], context=context, set_total=True)
        return invoice_id

    def wkf_confirm_order(self, cr, uid, ids, context=None):
        res = super(purchase_order, self).wkf_confirm_order(cr, uid, ids, context=context)
        proc_obj = self.pool.get('procurement.order')
        payment_term_obj = self.pool.get('account.payment.term')
        voucher_obj = self.pool.get('account.voucher')
        for po in self.browse(cr, uid, ids, context=context):
            if not po.po_series_id:
                raise osv.except_osv(_("Warning !"),_('You cannot confirm a purchase order without any purchase order series.'))
            if po.requisition_id and (po.requisition_id.exclusive=='exclusive'):
                for order in po.requisition_id.purchase_ids:
                    if order.id != po.id:
                        proc_ids = proc_obj.search(cr, uid, [('purchase_id', '=', order.id)])
                        if proc_ids and po.state=='confirmed':
                            proc_obj.write(cr, uid, proc_ids, {'purchase_id': po.id})
                        wf_service = netsvc.LocalService("workflow")
                        wf_service.trg_validate(uid, 'purchase.order', order.id, 'purchase_cancel', cr)
                    
                    for line in order.order_line:
                        today = order.date_order
                        year = datetime.datetime.today().year
                        month = datetime.datetime.today().month
                        if month<4:
                            po_year=str(datetime.datetime.today().year-1)+'-'+str(datetime.datetime.today().year)
                        else:
                            po_year=str(datetime.datetime.today().year)+'-'+str(datetime.datetime.today().year+1)
                        self.pool.get('product.product').write(cr,uid,line.product_id.id,{
                                                                                              'last_supplier_rate': line.price_unit,
                                                                                              'last_po_no':order.id,
                                                                                              'last_po_series':order.po_series_id.id,
                                                                                              'last_supplier_code':order.partner_id.id,
                                                                                              'last_po_date':order.date_order,
                                                                                              'last_po_year':po_year
                                                                                          },context=context)
                po.requisition_id.tender_done(context=context)
            totlines = []
            total_amt = 0.0
            flag = False
            if po.payment_term_id:
                totlines = payment_term_obj.compute(cr, uid, po.payment_term_id.id, po.amount_total, po.date_order or False, context=context)
            journal_id = self.pool.get('account.journal').search(cr, uid, [('code', '=', 'BNK2')], context=context)[0]
            journal = self.pool.get('account.journal').browse(cr, uid, journal_id, context=context)
            account_id = journal.default_credit_account_id or journal.default_debit_account_id
            for line in totlines:
                today = fields.date.context_today(self, cr, uid, context=context)
                if line[0] == today:
                    total_amt += line[1]
                    flag = True
            if flag:
                note = '''An advance payment of rupees: %s\n\nREFERENCES:\nPurchase order: %s\nIndent: %s''' %(total_amt, po.name or '', po.indent_id.name or '',)
                voucher_id = voucher_obj.create(cr, uid, {'partner_id': po.partner_id.id, 'date': today, 'amount': total_amt, 'reference': po.name, 'type': 'payment', 'journal_id': journal_id, 'account_id': account_id.id, 'narration': note}, context=context)
                self.write(cr, uid, [po.id], {'voucher_id': voucher_id}, context=context)
        return res

    def open_advance_payment(self, cr, uid, ids, context=None):
        '''
        This function returns an action that display advance payment of given purchase order ids.
        '''
        assert len(ids) == 1, 'This option should only be used for a single id at a time'
        voucher_id = self.browse(cr, uid, ids[0], context=context).voucher_id.id
        res = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'account_voucher', 'view_vendor_payment_form')
        result = {
            'name': _('Advance Payment'),
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': res and res[1] or False,
            'res_model': 'account.voucher',
            'type': 'ir.actions.act_window',
            'nodestroy': True,
            'target': 'current',
            'res_id': voucher_id,
        }
        return result

    def do_merge(self, cr, uid, ids, context=None):
        """ Copy the original do_merge method for set po_series_id field for new Purchase Order
        """
        #TOFIX: merged order line should be unlink
        wf_service = netsvc.LocalService("workflow")
        def make_key(br, fields):
            list_key = []
            for field in fields:
                field_val = getattr(br, field)
                if field in ('product_id', 'move_dest_id', 'account_analytic_id'):
                    if not field_val:
                        field_val = False
                if isinstance(field_val, browse_record):
                    field_val = field_val.id
                elif isinstance(field_val, browse_null):
                    field_val = False
                elif isinstance(field_val, list):
                    field_val = ((6, 0, tuple([v.id for v in field_val])),)
                list_key.append((field, field_val))
            list_key.sort()
            return tuple(list_key)

        # Compute what the new orders should contain

        new_orders = {}

        for porder in [order for order in self.browse(cr, uid, ids, context=context) if order.state == 'draft']:
            order_key = make_key(porder, ('partner_id', 'location_id', 'pricelist_id'))
            new_order = new_orders.setdefault(order_key, ({}, []))
            new_order[1].append(porder.id)
            order_infos = new_order[0]
            if not order_infos:
                order_infos.update({
                    'origin': porder.origin,
                    'po_series_id': porder.po_series_id.id,
                    'date_order': porder.date_order,
                    'partner_id': porder.partner_id.id,
                    'dest_address_id': porder.dest_address_id.id,
                    'warehouse_id': porder.warehouse_id.id,
                    'location_id': porder.location_id.id,
                    'pricelist_id': porder.pricelist_id.id,
                    'state': 'draft',
                    'order_line': {},
                    'notes': '%s' % (porder.notes or '',),
                    'fiscal_position': porder.fiscal_position and porder.fiscal_position.id or False,
                })
            else:
                if porder.date_order < order_infos['date_order']:
                    order_infos['date_order'] = porder.date_order
                if porder.notes:
                    order_infos['notes'] = (order_infos['notes'] or '') + ('\n%s' % (porder.notes,))
                if porder.origin:
                    order_infos['origin'] = (order_infos['origin'] or '') + ' ' + porder.origin

            for order_line in porder.order_line:
                line_key = make_key(order_line, ('name', 'date_planned', 'taxes_id', 'price_unit', 'product_id', 'move_dest_id', 'account_analytic_id'))
                o_line = order_infos['order_line'].setdefault(line_key, {})
                if o_line:
                    # merge the line with an existing line
                    o_line['product_qty'] += order_line.product_qty * order_line.product_uom.factor / o_line['uom_factor']
                else:
                    # append a new "standalone" line
                    for field in ('product_qty', 'product_uom'):
                        field_val = getattr(order_line, field)
                        if isinstance(field_val, browse_record):
                            field_val = field_val.id
                        o_line[field] = field_val
                    o_line['uom_factor'] = order_line.product_uom and order_line.product_uom.factor or 1.0



        allorders = []
        orders_info = {}
        for order_key, (order_data, old_ids) in new_orders.iteritems():
            # skip merges with only one order
            if len(old_ids) < 2:
                allorders += (old_ids or [])
                continue

            # cleanup order line data
            for key, value in order_data['order_line'].iteritems():
                del value['uom_factor']
                value.update(dict(key))
            order_data['order_line'] = [(0, 0, value) for value in order_data['order_line'].itervalues()]

            # create the new order
            neworder_id = self.create(cr, uid, order_data)
            orders_info.update({neworder_id: old_ids})
            allorders.append(neworder_id)

            # make triggers pointing to the old orders point to the new order
            for old_id in old_ids:
                wf_service.trg_redirect(uid, 'purchase.order', old_id, neworder_id, cr)
                wf_service.trg_validate(uid, 'purchase.order', old_id, 'purchase_cancel', cr)
        return orders_info
    
purchase_order()

class stock_picking(osv.osv):
    _inherit = "stock.picking"
    _columns = {
            'type': fields.selection([('out', 'Sending Goods'), ('receipt', 'Receipt'),('in', 'Getting Goods'), ('internal', 'Internal')], 'Shipping Type', required=True, select=True, help="Shipping type specify, goods coming in or going out."),
                }
stock_picking()

class stock_picking_receipt(osv.osv):
    _name = "stock.picking.receipt"
    _inherit = "stock.picking"
    _table = "stock_picking"
    _description = "Receipt"

    def check_access_rights(self, cr, uid, operation, raise_exception=True):
        #override in order to redirect the check of acces rights on the stock.picking object
        return self.pool.get('stock.picking').check_access_rights(cr, uid, operation, raise_exception=raise_exception)

    def check_access_rule(self, cr, uid, ids, operation, context=None):
        #override in order to redirect the check of acces rules on the stock.picking object
        return self.pool.get('stock.picking').check_access_rule(cr, uid, ids, operation, context=context)

    def _workflow_trigger(self, cr, uid, ids, trigger, context=None):
        #override in order to trigger the workflow of stock.picking at the end of create, write and unlink operation
        #instead of it's own workflow (which is not existing)
        return self.pool.get('stock.picking')._workflow_trigger(cr, uid, ids, trigger, context=context)

    def _workflow_signal(self, cr, uid, ids, signal, context=None):
        #override in order to fire the workflow signal on given stock.picking workflow instance
        #instead of it's own workflow (which is not existing)
        return self.pool.get('stock.picking')._workflow_signal(cr, uid, ids, signal, context=context)
    
    _columns = {
        'purchase_id': fields.many2one('purchase.order', 'Purchase Order',ondelete='set null', select=True),
        'inward_id': fields.many2one('stock.picking.in', 'Inward',ondelete='set null'),
        'inward_date': fields.date('Inward Date'),
        'challan_no': fields.integer('Challan Number'),
        'tr_code': fields.integer('TR Code'),
        'excisable_item': fields.boolean('Excisable Item'),
        'gp_received': fields.boolean('GP Received'),
        'gp_date': fields.date('GP Received Date'),
        'state': fields.selection(
            [('draft', 'Draft'),
            ('approved', 'Approved'), 
            ('auto', 'Waiting Another Operation'),
            ('confirmed', 'Waiting Availability'),
            ('assigned', 'Ready to Receive'),
            ('done', 'Received'),
            ('cancel', 'Cancelled'),],
            'Status', readonly=True, select=True,
            help="""* Draft: not confirmed yet and will not be scheduled until confirmed\n
                 * Approved: waiting for manager approval to proceed further\n
                 * Waiting Another Operation: waiting for another move to proceed before it becomes automatically available (e.g. in Make-To-Order flows)\n
                 * Waiting Availability: still waiting for the availability of products\n
                 * Ready to Receive: products reserved, simply waiting for confirmation.\n
                 * Received: has been processed, can't be modified or cancelled anymore\n
                 * Cancelled: has been cancelled, can't be confirmed anymore"""),
    }
    _defaults = {
        'type': 'receipt',
    }    
stock_picking_receipt()
#----------------------------------------------------------
# Stock Location
#----------------------------------------------------------
class stock_location(osv.osv):
    _inherit = "stock.location"
    _columns = {
            'chained_picking_type': fields.selection([('out', 'Sending Goods'), ('in', 'Getting Goods'), ('internal', 'Internal'),('receipt', 'Receipt')], 'Shipping Type', help="Shipping Type of the Picking List that will contain the chained move (leave empty to automatically detect the type based on the source and destination locations)."),
                }
stock_location()

class stock_move(osv.osv):
    _inherit = "stock.move"
    _columns = {
            'type': fields.related('picking_id', 'type', type='selection', selection=[('out', 'Sending Goods'), ('in', 'Getting Goods'), ('internal', 'Internal'),('receipt', 'receipt')], string='Shipping Type'),
                }
stock_location()
