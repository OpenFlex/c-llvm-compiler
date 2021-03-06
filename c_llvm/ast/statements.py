from c_llvm.ast.base import AstNode


class CompoundStatementNode(AstNode):
    def generate_code(self, state):
        state.enter_block()
        children = self.process_children(state)
        state.leave_block()
        return "\n".join(children)

    def toString(self):
        return ""

    def toStringTree(self):
        return "{\n%s\n}" % (
            super(CompoundStatementNode, self).toStringTree(),
        )


class IfNode(AstNode):
    child_attributes = {
        'exp': 0,
        'statement': 1
    }

    template = """
%(exp_code)s
%(exp_cast_code)s
br i1 %(exp_cast_value)s, label %%If%(num)d.True, label %%If%(num)d.False
If%(num)d.True:
%(statement_code)s
br label %%If%(num)d.False
If%(num)d.False:
"""

    def generate_code(self, state):
        exp_code = self.exp.generate_code(state)
        exp_result = state.pop_result()
        exp_cast_code = exp_result.type.cast_to_bool(exp_result, state)
        exp_cast_result = state.pop_result()

        return self.template % {
            'exp_code': exp_code,
            'exp_cast_code': exp_cast_code,
            'exp_cast_value': exp_cast_result.value,
            'num': state._get_next_number(),
            'statement_code': self.statement.generate_code(state),
        }


class IfElseNode(AstNode):
    child_attributes = {
        'exp': 0,
        'statement1': 1,
        'statement2': 2,
    }

    template = """
%(exp_code)s
%(exp_cast_code)s
br i1 %(exp_cast_value)s, label %%If%(num)d.True, label %%If%(num)d.False
If%(num)d.True:
%(statement1_code)s
br label %%If%(num)d.End
If%(num)d.False:
%(statement2_code)s
br label %%If%(num)d.End
If%(num)d.End:
"""

    def generate_code(self, state):
        exp_code = self.exp.generate_code(state)
        exp_result = state.pop_result()
        exp_cast_code = exp_result.type.cast_to_bool(exp_result, state)
        exp_cast_result = state.pop_result()

        return self.template % {
            'exp_code': exp_code,
            'exp_cast_code': exp_cast_code,
            'exp_cast_value': exp_cast_result.value,
            'num': state._get_next_number(),
            'statement1_code': self.statement1.generate_code(state),
            'statement2_code': self.statement2.generate_code(state),
        }


class WhileStatement(AstNode):
    child_attributes = {
        'exp': 0,
        'statement': 1
    }

    def generate_code(self, state):
        num = state._get_next_number()
        state.break_labels.append("While%d.End" % num)
        state.continue_labels.append("While%d.Body" % num)
        exp_code = self.exp.generate_code(state)
        exp_result = state.pop_result()
        exp_cast_code = exp_result.type.cast_to_bool(exp_result, state)
        exp_cast_value = state.pop_result().value
        statement_code = self.statement.generate_code(state)
        state.break_labels.pop()
        state.continue_labels.pop()
        return self.template % {
            'exp_code': exp_code,
            'exp_cast_code': exp_cast_code,
            'exp_cast_value': exp_cast_value,
            'num': num,
            'statement_code': statement_code,
        }


class WhileNode(WhileStatement):
    # end previous basic block with br
    template = """
br label %%While%(num)d.Test
While%(num)d.Test:
%(exp_code)s
%(exp_cast_code)s
br i1 %(exp_cast_value)s, label %%While%(num)d.Body, label %%While%(num)d.End
While%(num)d.Body:
%(statement_code)s
br label %%While%(num)d.Test
While%(num)d.End:
"""


class DoWhileNode(WhileStatement):
    # end previous basic block with br
    template = """
br label %%While%(num)d.Body
While%(num)d.Body:
%(statement_code)s
br label %%While%(num)d.Test
While%(num)d.Test:
%(exp_code)s
%(exp_cast_code)s
br i1 %(exp_cast_value)s, label %%While%(num)d.Body, label %%While%(num)d.End
While%(num)d.End:
"""


class ForNode(AstNode):
    child_attributes = {
        'exp1': 0,
        'exp2': 1,
        'exp3': 2,
        'statement': 3
    }

    template = """
%(e1_code)s
br label %%For%(num)d.Test
For%(num)d.Test:
%(e2_code)s
%(e2_cast_code)s
br i1 %(e2_cast_value)s, label %%For%(num)d.Body, label %%For%(num)d.End
For%(num)d.Body:
%(statement_code)s
br label %%For%(num)d.Inc
For%(num)d.Inc:
%(e3_code)s
br label %%For%(num)d.Test
For%(num)d.End:
"""

    def generate_code(self, state):
        state.enter_block()
        num = state._get_next_number()
        state.break_labels.append("For%d.End" % num)
        state.continue_labels.append("For%d.Inc" % num)
        e1_code = self.exp1.generate_code(state)

        # Pop the result explicitly to ensure we won't process a discarded
        # result from a previous expression if e2 was omitted.
        state.pop_result()

        e2_code = self.exp2.generate_code(state)
        e2_result = state.pop_result()
        if not e2_result:
            e2_cast_code = ""
            e2_cast_value = 1
        else:
            e2_cast_code = e2_result.type.cast_to_bool(e2_result, state)
            e2_cast_value = state.pop_result().value

        e3_code = self.exp3.generate_code(state)
        statement_code = self.statement.generate_code(state)
        state.break_labels.pop()
        state.continue_labels.pop()
        state.leave_block()
        return self.template % {
            'e1_code': e1_code,
            'e2_code': e2_code,
            'e3_code': e3_code,
            'e2_cast_code': e2_cast_code,
            'e2_cast_value': e2_cast_value,
            'num': num,
            'statement_code': statement_code,
        }


class BreakStatementNode(AstNode):
    def generate_code(self, state):
        if not state.break_labels:
            self.log_error(state, "'break' used outside of loop and switch")
            return ""
        return "br label %%%s" % (state.break_labels[-1])


class ContinueStatementNode(AstNode):
    def generate_code(self, state):
        if not state.continue_labels:
            self.log_error(state, "'continue' used outside of loop")
            return ""
        return "br label %%%s" % (state.continue_labels[-1])


class ReturnStatementNode(AstNode):
    child_attributes = {
        'expression': 0,
    }
    template = """
%(expression_code)s
%(cast_code)s
ret %(type)s %(value)s
"""

    def generate_code(self, state):
        return_type = state.return_type
        if return_type.is_void:
            if self.getChildCount():
                self.log_error(state, "a void function can't return a "
                               "value")
            return "ret void"
        expression_code = self.expression.generate_code(state)
        expression_result = state.pop_result()
        cast_code = state.types.cast_value(expression_result,
                                           state, return_type)
        expression_result = state.pop_result()
        state.return_found = True
        return self.template % {
            'expression_code': expression_code,
            'cast_code': cast_code,
            'type': return_type.llvm_type,
            'value': expression_result.value,
        }


class SwitchStatementNode(AstNode):
    child_attributes = {
        'exp': 0,
        'statement': 1
    }

    template = """
%(exp_code)s
switch i64 %(exp_value)s, label %%%(default_label)s [ %(labels_list)s ]
%(statement_code)s
br label %%Switch%(num)d.End
Switch%(num)d.End:
"""

    def generate_code(self, state):
        num = state._get_next_number()
        state.break_labels.append("Switch%d.End" % num)
        state.enter_switch(num)
        exp_code = self.exp.generate_code(state)
        exp_value = state.pop_result().value
        default_label = "Switch%d.Default" % num
        labels_list = ""
        statement_code = self.statement.generate_code(state)
        # if default-label was not found, use end-label, llvm needs something
        if not state.switches[-1][1]:
            default_label = "Switch%d.End" % num
        for label in state.switches[-1][2]:
            labels_list += label
        state.leave_switch()
        state.break_labels.pop()
        return self.template % {
            'exp_code': exp_code,
            'exp_value': exp_value,
            'default_label': default_label,
            'labels_list': labels_list,
            'num': num,
            'statement_code': statement_code,
        }


class CaseStatementNode(AstNode):
    child_attributes = {
        'exp': 0,
        'statement': 1
    }

    template = """
br label %%%(case_label)s
%(case_label)s:
%(statement_code)s
"""

    def generate_code(self, state):
        if not state.switches:
            self.log_error(state, "'case' used outside of 'switch' statement")
            return ""
        current_switch = state.switches[-1]
        exp_code = self.exp.generate_code(state)
        exp_result = state.pop_result()
        if not exp_result.is_constant:
            self.log_error(state, "'case' expression must be constant")
            return ""
        case_num = exp_result.value
        num = current_switch[0]
        case_label = "Switch%d.Case%d" % (num, case_num)
        current_switch[2].append("i64 %d, label %%%s\n" % (case_num, case_label))
        statement_code = self.statement.generate_code(state)
        return self.template % {
            'case_label': case_label,
            'statement_code': statement_code,
        }


class DefaultStatementNode(AstNode):
    child_attributes = {
        'statement': 0
    }

    template = """
br label %%%(default_label)s
%(default_label)s:
%(statement_code)s
"""

    def generate_code(self, state):
        if not state.switches:
            self.log_error(state, "'default' used outside of 'switch' statement")
            return ""
        current_switch = state.switches[-1]
        current_switch[1] = True
        default_label = "Switch%d.Default" % current_switch[0]
        statement_code = self.statement.generate_code(state)
        return self.template % {
            'default_label': default_label,
            'statement_code': statement_code,
        }
