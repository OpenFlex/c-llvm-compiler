from collections import Counter

from c_llvm.ast.base import AstNode
from c_llvm.types import PointerType
from c_llvm.variables import Variable


class DeclarationNode(AstNode):
    child_attributes = {
        'var_type': 0,
        'declarator': 1,
    }

    def generate_code(self, state):
        # TODO: check redeclarations
        is_global = state.is_global()
        state.declaration_stack.append(state.types.get_type(str(self.var_type)))
        type = self.declarator.get_type(state)
        identifier = self.declarator.get_identifier()
        state.declaration_stack.pop()

        if is_global:
            register = '@%s' % (identifier,)
        else:
            register = state.get_var_register(identifier)
        var = Variable(type=type, name=identifier, register=register,
                       is_global=is_global)

        if type.is_function:
            if not is_global:
                self.log_error(state, "can't declare a non-global function")
            declaration = "declare %(ret_type)s %(register)s%(arg_types)s" % {
                'ret_type': type.return_type.llvm_type,
                'register': register,
                'arg_types': type.arg_types_str,
            }
        elif is_global:
            declaration = "%(register)s = global %(type)s %(value)s" % {
                'register': var.register,
                'type': var.type.llvm_type,
                'value': var.type.default_value,
            }
        else:
            declaration = "%(register)s = alloca %(type)s" % {
                'register': var.register,
                'type': var.type.llvm_type,
            }

        state.symbols[identifier] = var
        return declaration

    def toString(self):
        return "declaration"

    def toStringTree(self):
        return "%s\n" % (super(DeclarationNode, self).toStringTree(),)


class FunctionDefinitionNode(AstNode):
    child_attributes = {
        'return_type': 0,
        'declarator': 1,
        'body': 2,
    }
    template = """
define %(type)s @%(name)s(%(args)s)
{
%(init)s
%(contents)s
%(return)s
}
"""
    ret_template = """
%(register1)s = alloca %(type)s
%(register2)s = load %(type)s* %(register1)s
ret %(type)s %(register2)s
"""
    init_template = """
%(register)s = alloca %(type)s
store %(type)s %%%(name)s, %(type)s* %(register)s
"""

    def generate_code(self, state):
        specifier_type = state.types.get_type(str(self.return_type))
        state.declaration_stack.append(specifier_type)
        function_type = self.declarator.get_type(state)
        state.declaration_stack.pop()
        name = self.declarator.get_identifier()
        register = '@%s' % (name,)

        if not function_type.is_function:
            self.log_error(state, "invalid function definition -- "
                           "symbol of a non-function type declared")
            return ""

        if name in state.symbols:
            declared = state.symbols[name]
            if declared.type is not function_type:
                self.log_error(state, "%s already declared as %s" %
                               declared.type.name)
                return ""
            if declared.is_defined:
                self.log_error(state, "function already defined")
                return ""
            declared.is_defined = True
        else:
            state.symbols[name] = Variable(name, function_type, register,
                                           True, True)

        arguments = zip(self.declarator.get_argument_names(state),
                        function_type.arg_types)
        arg_init, arg_header = [], []
        pending_scope = {}
        for arg_name, arg_type in arguments:
            arg_header.append("%s %%%s" % (arg_type.llvm_type, arg_name))
            arg_register = state.get_var_register(arg_name)
            arg_init.append(self.init_template % {
                'type': arg_type.llvm_type,
                'register': arg_register,
                'name': arg_name,
            })
            pending_scope[arg_name] = Variable(arg_name, arg_type,
                                               arg_register, False)

        state.set_pending_scope(pending_scope)

        return_type = function_type.return_type
        state.return_type = return_type
        if return_type.is_void:
            ret_statement = "ret void"
        else:
            ret_statement = self.ret_template % {
                'type': function_type.return_type.llvm_type,
                'register1': state.get_tmp_register(),
                'register2': state.get_tmp_register(),
            }
        result = self.template % {
            'type': function_type.return_type.llvm_type,
            'name': name,
            'args': ', '.join(arg_header),
            'init': '\n'.join(arg_init),
            'contents': self.body.generate_code(state),
            'return': ret_statement,
        }
        state.return_type = None
        return result

    def toString(self):
        return "function definition"

    def toStringTree(self):
        return "%s\n" % (super(FunctionDefinitionNode, self).toStringTree(),)


class DeclaratorNode(AstNode):
    child_attributes = {
        'inner_declarator': 0,
    }

    def get_type(self, state):
        """
        Returns the Type instance of this declarator.
        """
        raise NotImplementedError

    def get_identifier(self):
        """
        Drills down through all levels of pointer and array specifiers to
        the identifier.
        """
        return self.inner_declarator.get_identifier()


class IdentifierDeclaratorNode(DeclaratorNode):
    child_attributes = {
        'identifier': 0,
    }

    def get_type(self, state):
        return state.declaration_stack[-1]

    def get_identifier(self):
        return str(self.identifier)


class PointerDeclaratorNode(DeclaratorNode):
    def get_type(self, state):
        child_type = self.inner_declarator.get_type(state)
        return state.types.get_pointer_type(child_type)


class FunctionDeclaratorNode(DeclaratorNode):
    child_attributes = {
        'inner_declarator': 0,
        'arg_list': 1,
    }

    def get_type(self, state):
        return_type = self.inner_declarator.get_type(state)
        if return_type.is_function:
            self.log_error(state, 'a function cannot return a function')
        if return_type.is_array:
            self.log_error(state, 'a function cannot return an array')
        arg_list = self.arg_list.children
        variable_arguments = len(arg_list) > 0 and str(arg_list[-1]) == '...'
        if variable_arguments:
            arg_list.pop()
        arg_types = [arg.get_type(state) for arg in arg_list]

        for i, type in enumerate(arg_types):
            if type.is_void:
                arg_list[i].log_error(state, "function arguments can't be void")
            elif type.is_function:
                arg_types[i] = state.get_pointer_type(type)

        return state.types.get_function_type(return_type, arg_types,
                                             variable_arguments)

    def get_argument_names(self, state):
        """
        This should only be called from function definitions as it will
        log errors only relevant for those.
        """
        names = [arg.get_identifier() for arg in self.arg_list.children]
        if any(name is None for name in names):
            self.log_error(state, "argument name not provided")
            return []
        counter = Counter(names)
        if counter and counter.most_common(1)[0][1] > 1:
            self.log_error(state, "duplicate argument name")
        return names


class ParameterListNode(AstNode):
    pass


class ParameterDeclarationNode(AstNode):
    child_attributes = {
        'type_specifier': 0,
        'declarator': 1,
    }

    def get_type(self, state):
        state.declaration_stack.append(state.types.get_type(str(self.type_specifier)))
        type = self.declarator.get_type(state)
        state.declaration_stack.pop()
        return type

    def get_identifier(self):
        return self.declarator.get_identifier()


class ArrayDeclaratorNode(DeclaratorNode):
    child_attributes = {
        'inner_declarator': 0,
        'length': 1,
    }

    def get_type(self, state):
        if self.getChildCount() != 2:
            self.log_error(state, "incomplete array types are not "
                           "supported (you have to provide a length)")
            length = 0
        elif str(self.length) == '*':
            self.log_error(state, "variable-length arrays are not "
                           "supported")
            length = 0
        else:
            self.length.generate_code(state)
            length_result = state.pop_result()
            if (length_result is not None and length_result.is_constant
                    and length_result.type.is_integer):
                length = length_result.value
            else:
                self.log_error(state, "invalid array dimension (constant "
                               "integer expression required)")
                length = 0

        target_type = self.inner_declarator.get_type(state)

        if target_type.is_function:
            self.log_error(state, "can't declare an array of functions")

        return state.types.get_array_type(target_type, length)
