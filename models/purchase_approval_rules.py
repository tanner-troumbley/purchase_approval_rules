import odoo
from odoo import models, fields, api, _
from odoo.tools.safe_eval import safe_eval, test_python_expr
from odoo.exceptions import ValidationError, AccessError
from datetime import datetime


class FieldConditions_Conditions(models.Model):
    _name = 'purchase_approval_rules.field_conditions.conditions'
    _description = 'Field Conditions for conditions'
    
    name = fields.Char()
    string_condition = fields.Boolean()
    boolean_condition = fields.Boolean()


class FieldConditions(models.Model):
    _name = 'purchase_approval_rules.field_conditions'
    _description = 'Field Conditions'
    _order = 'sequence'

    @api.onchange('field_id')
    def _get_condition_domain(self):
        if self.field_id.ttype in ('date', 'datetime', 'float', 'integer', 'monetary'):
            res = {'domain': {'condition_id': [('boolean_condition', '=', False), '|', ('string_condition', '=', False),
                                               ('name', '=', 'is Equal To')]}}
        if self.field_id.ttype == 'boolean':
            res = {'domain': {'condition_id': [('boolean_condition', '=', True)]}}
        if self.field_id.ttype not in ('date', 'datetime', 'float', 'integer', 'monetary', 'boolean'):
            res = {'domain': {'condition_id': [('string_condition', '=', True)]}}

        return res

    purchase_approval_id = fields.Many2one('purchase_approval_rules', ondelete='cascade')
    field_id = fields.Many2one('ir.model.fields', string='Field', required=True, ondelete='cascade')
    value = fields.Text(required=True, help="Expression containing a value specification. \n"
                                            "When Formula type is selected, this field may be a Python expression "
                                            " that can use the same values as for the code field on the server action.\n"
                                            "If Value type is selected, the value will be used directly without evaluation.")

    condition_id = fields.Many2one('purchase_approval_rules.field_conditions.conditions', required=True)
    sequence = fields.Integer(string='Sequence', default=10)

    @api.constrains('value')
    def _value_constraints(self):
        for record in self:
            if record.field_id.ttype in ('date', 'datetime'):
                try:
                    datetime.strptime(record.value, "%m/%d/%Y")
                except ValueError:
                    raise ValidationError(
                        _('%s is a %s field and can only be in Month/Day/Year foramt. Please change the value to match the Month/Day/Year format.' % (record.field_id.display_name, record.field_id.ttype)))
            if record.field_id.ttype in ('float', 'integer', 'monetary') and not record.value.isdigit():
                raise ValidationError(
                    _('%s is a %s field and can only be compared to numbers. Please input a number' % (record.field_id.display_name, record.field_id.ttype)))
            if record.field_id.ttype == 'boolean':
                try:
                    if not isinstance(eval(record.value.lower().capitalize()), bool):
                        raise ValidationError(
                            _('%s is a %s field and can only True or False. Please pick one for the value.' % (record.field_id.display_name, record.field_id.ttype)))
                except NameError:
                    raise ValidationError(
                        _('%s is a %s field and can only True or False. Please pick one for the value.' % (record.field_id.display_name, record.field_id.ttype)))


class GroupAmounts(models.Model):
    _name = 'purchase_approval_rules.group_amounts'
    _description = 'Group Amounts'
    _order = 'sequence'

    purchase_approval_id = fields.Many2one('purchase_approval_rules', ondelete='cascade')
    group_id = fields.Many2one('res.groups', string='Group', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    amount = fields.Monetary(help='The amount this group can buy without approval from someone else. Will always be positive. 0 means there is no limit.')
    company_id = fields.Many2one('res.company', 'Company', index=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')

    @api.model_create_multi
    def create(self, vals):
        for val in vals:
            if val.get('amount'):
                if val['amount'] < 0:
                    val['amount'] = -val['amount']

        return super(GroupAmounts, self).create(vals)

    def write(self, vals):
        if vals.get('amount'):
            if vals['amount'] < 0:
                vals['amount'] = -vals['amount']

        return super(GroupAmounts, self).write(vals)

    @api.constrains('group_id')
    def _group_id_constraints(self):
        """Ensure that each group is not used more than once."""
        records = self.search([]) - self
        all_groups = records.group_id.ids
        for group in self.group_id:
            if group.id in all_groups:
                parent_record = self.search([('group_id', '=', group.id)])[0]
                raise ValidationError(_('%s already has an amount assigned to it in %s.' % (group.name, parent_record.purchase_approval_id.name)))


class PurchaseApprovalRules(models.Model):
    """ Based of the Server actions model. Ment to be an easy way to add rules
    to the purchase approval process.

    The available actions are :

    - 'Execute Python Code': a block of python code that will be executed
    - 'Group Amounts': Give a group an amount it can purchase without approval. 0 means there is no limit.
    """
    _name = 'purchase_approval_rules'
    _description = 'Purchase Approval Rules'
    _order = 'sequence'

    DEFAULT_PYTHON_CODE = """# Available variables:
#  - env: Purchase Order Environment
#  - model: Purchase Order Model
#  - record: record on which the action is triggered; 
#  - time, datetime, dateutil, timezone: useful Python libraries
#  - log: log(message, level='info'): logging function to record debug information in ir.logging table
#  - UserError: Warning Exception to use with raise
#  - ValidationError: Warning Exception to use with raise
#  - AccessError: Warning Exception to use with raise
      
# To return an action, assign: action = {...}\n\n\n\n"""

    active = fields.Boolean('Active', default=True)

    name = fields.Char(string='Rule Name', translate=True, required=True)
    state = fields.Selection([('code', 'Execute Python Code'), ('group_amounts', 'Group Amounts'), ('field_conditions', 'Conditions')], string='Action To Do', default='code', required=True, copy=True,
                             help="Type of approval rule action. The following values are available:\n- 'Execute Python Code': a block of python code that will be executed\n"
                                  "- 'Groups Amounts': Give Groups Different Purchase amounts before it needs to be approved by someone else\n")
    code = fields.Text(string='Python Code', groups='base.group_system', default=DEFAULT_PYTHON_CODE, help="Write Python code that the action will execute. Some variables are available for use; help about python expression is given in the help tab.")
    group_amount_ids = fields.One2many('purchase_approval_rules.group_amounts', 'purchase_approval_id', help='The Amount the specified group and buy without approval. Will always be positive.')
    field_condition_ids = fields.One2many('purchase_approval_rules.field_conditions', 'purchase_approval_id', help='Conditions on selected fields. If the record fails the conditions it will not be approved.')
    sequence = fields.Integer(string='Sequence', default=10)

    @api.model_create_multi
    def create(self, vals):
        groups = []
        for val in vals:
            if val.get('group_amount_ids'):
                group_ids = []

                for amount in val['group_amount_ids']:
                    if group_ids:
                        if amount[2]['group_id'] in group_ids:
                            group = self.env['res.groups'].search([('id', '=', amount[2]['group_id'])])
                            groups.append(group.name)
                    if amount[0] == 0 and amount[2]['group_id'] not in group_ids:
                        group_ids.append(amount[2]['group_id'])
        if groups:
            compiled_list = [*set(groups)]
            group_list = '\n'.join(map(str, compiled_list))
            msg = 'The following groups have been used more then once .\nGroups:\n' + group_list
            raise ValidationError(_(msg))
        return super(PurchaseApprovalRules, self).create(vals)

    def write(self, vals):
        groups = []
        msg = ''
        if vals.get('group_amount_ids'):
            group_ids = []
            for amount in vals['group_amount_ids']:
                if group_ids and amount[0] == 0:
                    if amount[2]['group_id'] in group_ids:
                        group = self.env['res.groups'].search([('id', '=', amount[2]['group_id'])])
                        groups.append(group.name)
                if amount[0] == 0 and amount[2]['group_id'] not in group_ids:
                    group_ids.append(amount[2]['group_id'])

        if groups:
            compiled_list = [*set(groups)]
            group_list = '\n'.join(map(str, compiled_list))
            msg = 'The following groups have been used more then once .\nGroups:\n' + group_list
            raise ValidationError(_(msg))

        return super(PurchaseApprovalRules, self).write(vals)

    @api.constrains('code')
    def _check_python_code(self):
        for action in self.sudo().filtered('code'):
            msg = test_python_expr(expr=action.code.strip(), mode="exec")
            if msg:
                raise ValidationError(msg)

    def _get_eval_context(self, action=None, purchase_record=None):
        """ Prepare the context used when evaluating python code, like the
        python formulas or code approval rules.

        :param action: the current approval rule
        :type action: browse record
        :returns: dict"""

        def log(message, level="info"):
            with self.pool.cursor() as cr:
                cr.execute("""INSERT INTO ir_logging(create_date, create_uid, type, dbname, name, level, message, path, line, func) VALUES (NOW() at time zone 'UTC', %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                           (self.env.uid, 'approval rules', self._cr.dbname, __name__, level, message, "action", action.id, action.name))

        eval_context = self.env['ir.actions.actions']._get_eval_context(action=action)
        model = self.env['purchase.order']
        record = purchase_record
        eval_context.update({
            # orm
            'env': self.env,
            'model': model,
            # Exceptions
            'UserError': odoo.exceptions.UserError,
            'ValidationError': odoo.exceptions.ValidationError,
            'AccessError': odoo.exceptions.AccessError,
            # record
            'record': record,
            # helpers
            'log': log,
        })
        return eval_context

    def _run_action_code_multi(self, eval_context):
        safe_eval(self.code.strip(), eval_context, mode="exec", nocopy=True)  # nocopy allows to return 'action'
        return eval_context.get('action')

    def _get_runner(self):
        multi = True
        t = type(self)
        fn = getattr(t, f'_run_action_{self.state}_multi', None) \
             or getattr(t, f'run_action_{self.state}_multi', None)
        if not fn:
            multi = False
            fn = getattr(t, f'_run_action_{self.state}', None) \
                 or getattr(t, f'run_action_{self.state}', None)
        if fn and fn.__name__.startswith('run_action_'):
            fn = functools.partial(fn, self)
        return fn, multi

    def run(self, purchase_record):
        """ Runs the approval rule. For each approval rule, the
        :samp:`_run_action_{TYPE}[_multi]` method is called. This allows easy
        overriding of the approval rule.

        The `_multi` suffix means the runner can operate on multiple records,
        otherwise if there are multiple records the runner will be called once
        for each

        :param dict context: context should contain following keys

                             - active_id: id of the current object (single mode)
                             - active_model: current model that should equal the action's model

                             The following keys are optional:

                             - active_ids: ids of the current records (mass mode). If active_ids
                               and active_id are present, active_ids is given precedence.

        :return: an action_id to be executed, or False is finished correctly without
                 return action
        """
        res = False
        for action in self.sudo():
            eval_context = self._get_eval_context(action, purchase_record)
            records = eval_context.get('record') or eval_context['model']
            records |= eval_context.get('records') or eval_context['model']
            runner, multi = action._get_runner()
            if runner and multi:
                # call the multi method
                run_self = action.with_context(eval_context['env'].context)
                res = runner(run_self, eval_context=eval_context)
            elif runner:
                active_id = self._context.get('active_id')
                if not active_id and self._context.get('onchange_self'):
                    active_id = self._context['onchange_self']._origin.id
                    if not active_id:  # onchange on new record
                        res = runner(action, eval_context=eval_context)
                active_ids = self._context.get('active_ids', [active_id] if active_id else [])
                for active_id in active_ids:
                    # run context dedicated to a particular active_id
                    run_self = action.with_context(active_ids=[active_id], active_id=active_id)
                    eval_context["env"].context = run_self._context
                    res = runner(run_self, eval_context=eval_context)
            else:
                _logger.warning(
                    "Found no way to execute server action %r of type %r, ignoring it. "
                    "Verify that the type is correct or add a method called "
                    "`_run_action_<type>` or `_run_action_<type>_multi`.",
                    action.name, action.state
                )
        return res or False