# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime
from dateutil.relativedelta import relativedelta
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT

from openerp.exceptions import UserError

from openerp import models, fields, api, _
import openerp.addons.decimal_precision as dp


class StockLocation(models.Model):
    _inherit = 'stock.location'

    @api.model
    def _default_warehouse_id(self):
        company = self.env.user.company_id.id
        warehouse_id = self.env['stock.warehouse'].search([('company_id', '=', company)], limit=1)
        return warehouse_id

    @api.multi
    def create_operation_type(self):
        picking_type = self.env['stock.picking.type']
        sequence = self.env['ir.sequence']

        warehouse = self._default_warehouse_id()
        if not warehouse:
            raise UserError(_('You should have at least one warehouse to define production location.'))

        for location in self:
            sequence_vals = {
                'name': warehouse.name + ' ' + location.name, 
                'prefix': location.name + '/INT/', 
                'padding': 5
            }
            seq = sequence.create(sequence_vals)

            res = {
                'name': location.name,
                'code': 'internal',
                'default_location_src_id':warehouse.lot_stock_id.id,
                'default_location_dest_id':location.id,
                'warehouse_id':warehouse.id,
                'active': True,
                'use_existing_lots': True,
                'use_create_lots': True,
                'sequence_id': seq.id
            }
            picking_type.create(res)

    @api.model
    def create(self, vals):
        location = super(StockLocation, self).create(vals)
        if location.usage == 'production':
            location.create_operation_type()
        return location


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    usage = fields.Selection(related='default_location_dest_id.usage', store=True)

    @api.multi
    def get_indents(self):
        #TODO: review this method and improve if required
        data = self.env['ir.model.data']
        action = self.env['ir.actions.act_window']
        action_id = data.xmlid_to_res_id('indent.action_window', raise_if_not_found=True)
        action_open = action.browse(action_id)
        action_open = action_open.read()[0]
        return action_open


class Equipment(models.Model):
    _name = 'indent.equipment'
    _description = 'Equipment'

    name = fields.Char('Name')
    code = fields.Char('Code')

    _sql_constraints = [
        ('equipment_code', 'unique(code)', 'Equipment code must be unique !')
    ]


class EquipmentSection(models.Model):
    _name = 'indent.equipment.section'
    _description = 'Equipment Section'

    equipment_id = fields.Many2one('indent.equipment', string='Equipment', required=True)
    name = fields.Char('Name', size=256)
    code = fields.Char('Code', size=16)

    _sql_constraints = [
        ('equipment_section_code', 'unique(equipment_id, code)', 'Section code must be unique per Equipment !')
    ]


class AnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    indent_close = fields.Boolean('Close Indents', default=False)
    purchase_close = fields.Boolean('Close Purchase', default=False)


class Indent(models.Model):
    _name = 'stock.indent'
    _description = 'Indent'
    _inherit = ['mail.thread', 'ir.needaction_mixin']
    _order = 'date_indent desc'


    @api.model
    def _default_warehouse_id(self):
        company = self.env.user.company_id.id
        warehouse_ids = self.env['stock.warehouse'].search([('company_id', '=', company)], limit=1)
        return warehouse_ids


    name = fields.Char('Indent', default='Draft Indent / ')

    date_indent = fields.Datetime('Indent Date', default=fields.Datetime.now)
    date_approve = fields.Datetime('Approve Date', copy=False)
    date_required = fields.Datetime('Required Date')

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.user.company_id)

    picking_type_id = fields.Many2one('stock.picking.type', string='Department')
    picking_id = fields.Many2one('stock.picking','Picking')

    location_id = fields.Many2one('stock.location', string='Location', default='_get_default_location')
    user_id = fields.Many2one('res.users', string='Indentor', default=lambda self: self.env.user)
    #manager_id = fields.Many2one('res.users', string='Manager', related="department_id.manager_id", store=True)
    approve_user_id = fields.Many2one('res.users', string='Approved By')

    analytic_account_id = fields.Many2one('account.analytic.account', string='Project')

    indent_type = fields.Selection([('new', 'Purchase Indent'), ('existing', 'Repairing Indent')], string='Type', default='new')
    state = fields.Selection([('draft', 'Draft'), ('confirm', 'Confirm'), ('waiting_approval', 'Waiting for Approval'), ('inprogress', 'In Progress'), ('received', 'Received'), ('reject', 'Rejected')], string='State', default='draft')

    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', default=_default_warehouse_id)
    move_type = fields.Selection([('direct', 'Partial'), ('one', 'All at once')], string='Receive Method', default='direct')

    equipment_id = fields.Many2one('indent.equipment', string='Equipment')
    equipment_section_id = fields.Many2one('indent.equipment.section', string='Section')

    line_ids = fields.One2many('stock.indent.line', 'indent_id', string='Lines')
    description = fields.Text('Additional Note')

    amount_total = fields.Float('Estimated value', readonly=True)
    items = fields.Integer('Total items', readonly=True)


    @api.onchange('picking_type_id')
    def _get_default_location(self):
        self.location_id = self.picking_type_id.default_location_dest_id

    @api.onchange('date_indent')
    def _compute_date_required(self):
        self.date_required = datetime.strptime(self.date_indent, DEFAULT_SERVER_DATETIME_FORMAT) + relativedelta(days=7)

    @api.multi
    def action_confirm(self):
        for indent in self:
            indent.name = self.env['ir.sequence'].next_by_code('stock.indent')
            indent.state = 'waiting_approval'

            if not indent.line_ids:
                raise UserError(_('You cannot confirm an indent which has no line.'))

    @api.multi
    def action_approve(self):
        Move = self.env['stock.move']
        Picking = self.env['stock.picking']

        for indent in self:
            warehouse = indent._default_warehouse_id()
            res = {
                'location_id':warehouse.lot_stock_id.id,
                'location_dest_id':indent.location_id.id,
                'company_id':indent.company_id.id,
                'move_type': indent.move_type,
                'priority': '1',
                'picking_type_id': indent.picking_type_id.id,
                'indent_id': indent.id
            }
            picking_id = Picking.create(res)
            
            for line in indent.line_ids:
                vals = {
                    'name': line.name,
                    'product_id': line.product_id.id,
                    'picking_id': picking_id.id,
                    'location_id': warehouse.lot_stock_id.id,
                    'location_dest_id':indent.location_id.id,
                    'product_uom_qty':line.product_qty,
                    'date': indent.date_indent,
                    'date_expected': indent.date_indent,
                    'product_uom': line.product_uom.id,
                }
                line.move_id = Move.create(vals)
            picking_id.action_confirm()
            indent.picking_id = picking_id
            indent.state = 'inprogress'
            indent.date_approve = datetime.now()
            indent.approve_user_id = self.env.user.id


    @api.multi
    def action_receive_products(self):
        self.ensure_one()
        Picking = self.env['stock.picking']

        name = _('Receive Item')
        view_mode = 'form,tree'

        action = {
            'view_type': 'form',
            'res_model': 'stock.picking',
            'type': 'ir.actions.act_window',
            'nodestroy': True,
            'target': 'current'
        }
        if self.picking_id.id:
            backorders = Picking.search([('indent_id','=',self.id)])
            active_id = self.picking_id.id
            active_ids = [self.picking_id.id]

            if backorders:
                active_ids += backorders.ids
                name = _('Receive Items')
                view_mode = 'tree,form'
            else:
                action.update({
                    'res_id': active_id
                })

            action.update({
                'name': name,
                'view_mode': view_mode,
                'domain': [('id', 'in', active_ids)],
                'context': {'active_id': active_id, 'active_ids': active_ids}
            })

        return action


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    indent_id = fields.Many2one('stock.indent')

class IndentLine(models.Model):
    _name = 'stock.indent.line'
    _description = 'Indent Line'

    indent_id =  fields.Many2one('stock.indent', 'Indent', required=True, ondelete='cascade')
    name =  fields.Text('Purpose', required=True)
    product_id =  fields.Many2one('product.product', 'Product', required=True)
    original_product_id =  fields.Many2one('product.product', 'Product to be Repaired')
    produre_type =  fields.Selection([('make_to_stock', 'Stock'), ('make_to_order', 'Purchase')], string='Procure', required=True)
    
    product_qty =  fields.Float('Quantity', digits_compute=dp.get_precision('Product UoS'), required=True, default=1)
    product_uom =  fields.Many2one('product.uom', 'Unit of Measure', required=True)

    product_available_qty =  fields.Float('Available', readonly=True)
    product_issued_qty =  fields.Float(compute='_compute_product_issued_qty', string='Issued', readonly=True)

    product_uos_qty =  fields.Float('Quantity (UoS)' ,digits_compute=dp.get_precision('Product UoS'))
    product_uos =  fields.Many2one('product.uom', 'Product UoS')

    price_unit =  fields.Float('Price', required=True, digits_compute=dp.get_precision('Product Price'))
    price_subtotal =  fields.Float(compute='_compute_price_subtotal')
    qty_available =  fields.Float('In Stock')
    virtual_available =  fields.Float('Forecasted Qty')
    delay =  fields.Float('Lead Time', required=True, default=7)
    specification =  fields.Text('Specification')
    sequence = fields.Integer('Sequence')
    indent_type =  fields.Selection([('new', 'Purchase Indent'), ('existing', 'Repairing Indent')], 'Type')
    
    move_id = fields.Many2one('stock.move', 'Move')


    def _compute_product_issued_qty(self):
        Move = self.env['stock.move']
        Picking = self.env['stock.picking']

        for line in self:
            line.product_issued_qty = 0
            picking_ids = Picking.search([('indent_id','=',line.indent_id.id), ('state','=','done')])
            moves = Move.read_group([('picking_id','in', picking_ids.ids), ('product_id', '=', line.product_id.id)], ['product_id', 'product_qty'], ['product_id'])
            if moves:
                line.product_issued_qty = moves[0].get('product_qty', 0)

    @api.onchange('product_id')
    def _compute_line_based_on_product_id(self):
        self.product_uom = self.product_id.uom_id
        self.name = self.product_id.description_purchase or self.product_id.name
        self.produre_type = 'make_to_stock'
        self.product_available_qty = self.product_id.qty_available
        self.price_unit = self.product_id.standard_price

        if self.product_available_qty > 0:
            self['produre_type'] = 'make_to_stock'
        else:
            self['produre_type'] = 'make_to_order'

    @api.multi
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.price_unit * line.product_qty

