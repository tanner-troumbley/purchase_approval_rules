from odoo import models, fields, api, _
from datetime import datetime
from odoo.exceptions import AccessDenied, AccessError


class PurchaseOrderApprovalChange(models.Model):
    _inherit = 'purchase.order'

    purchase_order_type = fields.Selection([('direct', 'Direct'), ('indirect', 'Indirect')], string="Type", default='direct', store=True, readonly=False, required=True)

    def button_approve(self, force=False):
        if not force:
            self = self.filtered(lambda order: order._approval_allowed())
        self.write({'state': 'purchase', 'date_approve': fields.Datetime.now()})
        self.filtered(lambda p: p.company_id.po_lock == 'lock').write({'state': 'done'})
        self._create_picking()
        return {}

    def button_confirm(self):
        for order in self:
            if order.state not in ['draft', 'sent']:
                continue
            order._add_supplier_to_product()
            # Deal with double validation process
            res = order._approval_allowed()
            if res is not True:
                return res
            if res:
                order.button_approve(force=True)
            else:
                order.write({'state': 'to approve'})
            if order.partner_id not in order.message_partner_ids:
                order.message_subscribe([order.partner_id.id])
        return True
    def _approval_allowed(self):
        self.ensure_one()
        if self.company_id.po_double_validation == 'one_step':
            return True

        rules = self.env['purchase_approval_rules'].search([('active', '=', True)])
        if not rules:
            Approved = True
        msg = ''
        res = True
        for rule in rules:
            Approved = False
            if rule.state == 'code':
                res = rule.run(self)
                Approved = True
            
            if rule.state == 'group_amounts':
                group_names = []
                group_error_msg = ''
                for group in rule.group_amount_ids:
                    if self.env.user.id in group.group_id.users.ids:
                        if group.amount == 0:
                            Approved = True
                            group_error_msg = ''
                            break
                        if self.amount_total <= self.env.company.currency_id._convert(group.amount, self.currency_id, self.company_id, self.date_order or fields.Date.today()):
                            Approved = True
                            group_error_msg = ''
                            break
                        else:
                            group_names.append(group.group_id.display_name)
                            group_error_msg = '%s users are only allowed to approve a purchase up to %s%.2f\n' % (group.group_id.name, group.currency_id.symbol, group.amount)
                if not Approved and group_names and not group_error_msg:
                    group_names = '\n'.join(map(str, group_names))
                    msg += 'User is not in a group to approve purchases.\n\nApproved Groups:\n' + group_names + '\n\n'
                if not Approved and group_error_msg:
                    msg += group_error_msg


                    
            if rule.state == 'field_conditions':
                for condition in rule.field_condition_ids:
                    if condition.field_id.model_id.model == 'purchase.order':
                        if condition.field_id.ttype in ('float', 'integer', 'monetary'):
                            if condition.condition_id.name == 'is Equal To':
                                if self[condition.field_id.name] == float(condition.value):
                                    Approved = True
                                else:
                                    msg += '%s is not equal to %s\n' % (
                                    condition.field_id.field_description, condition.value)
                            if condition.condition_id.name == 'is Less Then':
                                if self[condition.field_id.name] < float(condition.value):
                                    Approved = True
                                else:
                                    msg += '%s is not less then to %s\n' % (
                                    condition.field_id.field_description, condition.value)
                            if condition.condition_id.name == 'is Greater Then':
                                if self[condition.field_id.name] > float(condition.value):
                                    Approved = True
                                else:
                                    msg += '%s is not greater then to %s\n' % (
                                    condition.field_id.field_description, condition.value)

                        if condition.field_id.ttype in ('date', 'datetime'):
                            date_value = datetime.strptime(condition.value, "%m/%d/%Y")
                            # msg += '%s vs. %s' % (self[condition.field_id.name], date_value)
                            if condition.condition_id.name == 'is Equal To':
                                if self[condition.field_id.name] == date_value:
                                    Approved = True
                                else:
                                    msg += '%s is not equal to %s\n' % (
                                    condition.field_id.field_description, condition.value)
                            if condition.condition_id.name == 'is Less Then':
                                if self[condition.field_id.name] < date_value:
                                    Approved = True
                                else:
                                    msg += '%s is not less then to %s\n' % (
                                    condition.field_id.field_description, condition.value)
                            if condition.condition_id.name == 'is Greater Then':
                                if self[condition.field_id.name] > date_value:
                                    Approved = True
                                else:
                                    msg += '%s is not greater then to %s\n' % (
                                    condition.field_id.field_description, condition.value)

                        if condition.field_id.ttype == 'boolean':
                            boolean_value = eval(condition.value.lower().capitalize())
                            msg += '%s vs %s' % (self[condition.field_id.name], boolean_value)
                            if self[condition.field_id.name] == boolean_value:
                                Approved = True
                            else:
                                msg += '%s is not %s\n' % (condition.field_id.field_description, condition.value)

                        if condition.field_id.ttype not in (
                        'float', 'integer', 'monetary', 'boolean', 'date', 'datetime'):
                            if condition.condition_id.name == 'is Equal To':
                                if condition.field_id.ttype in (
                                'many2many', 'many2one', 'many2one_reference', 'one2many'):
                                    name = line[condition.field_id.name].name
                                else:
                                    name = line[condition.field_id.name]
                                if str(condition.value) == name:
                                    Approved = True
                                else:
                                    msg += '%s does not equal %s\n' % (name, condition.value)
                            if condition.condition_id.name == 'Contains':
                                if condition.field_id.ttype in (
                                'many2many', 'many2one', 'many2one_reference', 'one2many'):
                                    name = line[condition.field_id.name].name
                                else:
                                    name = line[condition.field_id.name]
                                if str(condition.value) in name:
                                    Approved = True
                                else:
                                    msg += '%s does not contain %s\n' % (name, condition.value)

                    if condition.field_id.model_id.model == 'purchase.order.line':
                        for line in self.order_line:
                            if condition.field_id.ttype in ('float', 'integer', 'monetary'):
                                if condition.condition_id.name == 'is Equal To':
                                    if line[condition.field_id.name] == float(condition.value):
                                        Approved = True
                                    else:
                                        msg += '%s is not equal to %s\n' % (
                                        condition.field_id.field_description, condition.value)
                                if condition.condition_id.name == 'is Less Then':
                                    if line[condition.field_id.name] < float(condition.value):
                                        Approved = True
                                    else:
                                        msg += '%s is not less then to %s\n' % (
                                        condition.field_id.field_description, condition.value)
                                if condition.condition_id.name == 'is Greater Then':
                                    if line[condition.field_id.name] > float(condition.value):
                                        Approved = True
                                    else:
                                        msg += '%s is not greater then to %s\n' % (
                                        condition.field_id.field_description, condition.value)

                            if condition.field_id.ttype in ('date', 'datetime'):
                                date_value = datetime.strptime(condition.value, "%m/%d/%Y")
                                if condition.condition_id.name == 'is Equal To':
                                    if line[condition.field_id.name] == date_value:
                                        Approved = True
                                    else:
                                        msg += '%s is not equal to %s\n' % (
                                        condition.field_id.field_description, condition.value)
                                if condition.condition_id.name == 'is Less Then':
                                    if line[condition.field_id.name] < date_value:
                                        Approved = True
                                    else:
                                        msg += '%s is not less then to %s\n' % (
                                        condition.field_id.field_description, condition.value)
                                if condition.condition_id.name == 'is Greater Then':
                                    if line[condition.field_id.name] > date_value:
                                        Approved = True
                                    else:
                                        msg += '%s is not greater then to %s\n' % (
                                        condition.field_id.field_description, condition.value)

                            if condition.field_id.ttype == 'boolean':
                                boolean_value = eval(condition.value.lower().capitalize())
                                if line[condition.field_id.name] == boolean_value:
                                    Approved = True
                                else:
                                    msg += '%s is not %s\n' % (condition.field_id.field_description, condition.value)

                            if condition.field_id.ttype not in (
                            'float', 'integer', 'monetary', 'boolean', 'date', 'datetime'):
                                if condition.condition_id.name == 'is Equal To':
                                    if condition.field_id.ttype in (
                                    'many2many', 'many2one', 'many2one_reference', 'one2many'):
                                        name = line[condition.field_id.name].name
                                    else:
                                        name = line[condition.field_id.name]
                                    if str(condition.value) == name:
                                        Approved = True
                                    else:
                                        msg += '%s does not equal %s\n' % (name, condition.value)
                                if condition.condition_id.name == 'Contains':
                                    if condition.field_id.ttype in (
                                    'many2many', 'many2one', 'many2one_reference', 'one2many'):
                                        name = line[condition.field_id.name].name
                                    else:
                                        name = line[condition.field_id.name]
                                    if str(condition.value) in name:
                                        Approved = True
                                    else:
                                        msg += '%s does not contain %s\n' % (name, condition.value)

            if msg:
                raise AccessDenied(_(msg))
        if res is not True:
            return res
        return Approved
