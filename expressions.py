import math
import inspect
import operator
import itertools
import functools


def sliding_window(iterable):
    list_iterable = list(iterable)
    previous = [None] + list_iterable[:-1]
    future = iter(list_iterable)
    next(future, None)
    return itertools.zip_longest(previous, list_iterable, future)


def _sum(*a):
    return sum(a)


def ternary(cond, a, b):
    return a if cond else b


def sigma(start, end, body):
    return sum(map(body, range(start, end)))


class MathematicInfo:

    def angle_wrapper(func):
        def wrapper(*args):
            return func(args)
        
        return wrapper
    
    def __init__(self):
        self.functions = {name: value for name, value in inspect.getmembers(math) if callable(value)}
        self.constants = {name: value for name, value in inspect.getmembers(math)
                        if isinstance(value, (float, int))}  
    
        for name, func in self.functions.items():
            doc_string = func.__doc__

            if "in radians" in doc_string:
                input = doc_string.index("of") < doc_string.index("in radians")
                self.functions[name] = self.angle_converter(func, input)
                print("{} is an {} function".format(name, "input" if input else "output"))
        
        self.functions['use_radians'] = functools.partial(setattr, self, "angle_measure", "radians")
        self.functions['use_degrees'] = functools.partial(setattr, self, "angle_measure", "degrees")
        
        self.angle_measure = "radians"
    
    def angle_converter(self, func, input=True):
        def input_wrapper(angle): 
            if self.angle_measure == "degrees":
                return func(math.radians(angle))
            return func(angle)

        def output_wrapper(input):
            if self.angle_measure == "degrees":
                return math.degrees(func(input))

            return func(input)
        return input_wrapper if input else output_wrapper


class Operator:
    
    priority = 0
    arguments = 2
    associativity = "left"
    returns_value = True
    
    def __gt__(self, other):
        return self.priority < other.priority
    
    def __lt__(self, other):
        return self.priority > other.priority
    
    def __eq__(self, other):
        return self.priority == other.priority
    
    def evaluate(self, variables, *args): 
        pass


class MathOperator(Operator):
    
    def __init__(self, operation):
        self.operation = operation
    
    def evaluate(self, variables, *args):
        return Constant(self.operation(*[arg.evaluate(variables) for arg in args]))
    
    def __repr__(self):
        return "<{}: {}>".format(self.__class__.__name__, self.operation)


class AssignmentOperator(Operator):  
    
    priority = 7
    associativity = "right"
    returns_value = False
    
    def evaluate(self, variables, a, b):
        b_value = b.evaluate(variables)
        variables[a.value] = b_value  
        return None


class FunctionOperator(MathOperator):
    
    priority = 4
    arguments = 1
    
    def evaluate(self, variables, *args):
        print(variables, args)
        return Constant(self.operation(*[arg.evaluate(variables) for arg in args]))


class UnaryModifier(Operator):
    
    priority = 1
    arguments = 1
    
    associativity = "right"
    
    def evaluate(self, variables, term):
        return Constant(-term.evaluate(variables))


ass_op = AssignmentOperator()
un_mod = UnaryModifier()

exp_op = MathOperator(operator.pow)
exp_op.priority = 1

not_mod = MathOperator(operator.not_)
not_mod.priority = 2
not_mod.arguments = 1

mul_op = MathOperator(operator.mul)
mul_op.priority = 3

div_op = MathOperator(operator.truediv)
div_op.priority = 3

add_op = MathOperator(operator.add)
add_op.priority = 4

sub_op = MathOperator(operator.sub)
sub_op.priority = 4

gt_cond = MathOperator(operator.gt)
gt_cond.priority = 5

lt_cond = MathOperator(operator.lt)
lt_cond.priority = 5

and_cond = MathOperator(lambda b, a: bool(a) and bool(b))
and_cond.priority = 5

or_cond = MathOperator(lambda b, a: bool(a) or bool(b))
or_cond.priority = 5

eq_cond = MathOperator(operator.eq)
eq_cond.priority = 6


class Parenthesis:
    pass


class Delimiter:
    pass


class LeftParenthesis(Parenthesis):
    pass


class RightParenthesis(Parenthesis):
    pass


class Term:
    
    def __init__(self, value):
        self.value = value
    
    def evaluate(self, variables):
        return self.value
    
    def __repr__(self):
        return "<{}: {}>".format(self.__class__.__name__, self.value)


class Variable(Term):
    
    is_reference = False
    
    def evaluate(self, variables):
        try:
            return variables[self.value]
        except KeyError as err:
            raise ValueError("Variable '{}' was not declared".format(self.value)) from err


class Constant(Term):
    pass


class FunctionReference(Term):
    pass


class ExpressionParser:
    operators = {'+': add_op, '-': sub_op, '*': mul_op, '/': div_op, '^': exp_op, ':': ass_op,
                '>': gt_cond, '<': lt_cond, '=': eq_cond, '!': not_mod, '&': and_cond, '|': or_cond,
                'UNARY': un_mod}

    def __init__(self, expression):
        self.expression = expression.replace(" ", "")
        self.index = 0
        self.length = 0

    @property
    def end_index(self):
        return self.index + self.length

    @property
    def term(self):
        return self.expression[self.index: self.end_index]

    def consume_term(self):
        self.index += self.length
        self.length = 0

    def scan_while(self, condition):
        expression_length = len(self.expression)
        while condition(self.term) and self.end_index <= expression_length:
            self.length += 1
        self.length -= 1

    def is_variable(self, str_):
        return (str_.replace('_', '') or "defaultvar").isalpha()

    def is_reference(self, str_):
        return str_.startswith("$") and self.is_variable(str_[1:])

    def is_constant(self, str_):
        return (str_.replace('.', '') or "0").isnumeric()

    def __iter__(self):
        expression_length = len(self.expression)
                                
        while True:
            self.length += 1
            
            if self.end_index > expression_length:
                break

            if self.term in self.operators:
                yield self.operators[self.term]

            elif self.term == "(":
                yield LeftParenthesis()

            elif self.term == ")":
                yield RightParenthesis()
            
            elif self.term == ",":
                yield Delimiter()
            
            elif self.is_constant(self.term):
                self.scan_while(self.is_constant)
                yield Constant(eval(self.term))
            
            elif self.is_variable(self.term):
                self.scan_while(self.is_variable)
                yield Variable(self.term)

            elif self.is_reference(self.term):
                self.scan_while(self.is_reference)
                
                variable = Variable(self.term[1:])
                variable.is_reference = True
                yield variable
            
            self.consume_term()
            

class RPNTokenizer:
    
    def __init__(self, expression, symbol_table=None):
        self.expression = ExpressionParser(expression)
        self.tokens = []
        
        self.output = []
        self.operator_stack = []
        self.argument_stack = []
        
        if symbol_table is None:
            symbol_table = {}

        self.symbol_table = symbol_table
    
    def handle_operator(self, token):
        # Place precedent operators on output queue
        while self.operator_stack:
            other_opp = self.operator_stack[-1]
            if not isinstance(other_opp, Operator):
                break

            # Comparisons indicate precendence, not priority
            if not ((token.associativity == "left" and token == other_opp) or (token < other_opp)):
                break
            
            self.output.append(self.operator_stack.pop())
        
        self.operator_stack.append(token)
    
    def handle_delimiter(self, token):
        while self.operator_stack:
            if isinstance(self.operator_stack[-1], LeftParenthesis):
                break
            self.output.append(self.operator_stack.pop())
    
    def handle_term(self, token):
        # If it is a variable
        if isinstance(token, Variable):
            # If it is a function
            if token.value in self.symbol_table:
                function = self.symbol_table[token.value]
                operator = FunctionOperator(function)
                
                # Treat as an argument (part of the body)
                if token.is_reference:
                    token = FunctionReference(function)
    
                # Operators are not content
                else:
                    self.operator_stack.append(operator)
                    self.argument_stack.append(len(self.output))
                    return operator
            
            # We use references only for functions
            elif token.is_reference:
                raise ValueError("References reserved for functions only")

        # Variable values (and constants) can be resolved later
        self.output.append(token)
    
    def count_arguments_until(self, end_index):
        """Determine the number of arguments provided to a function
        Enables true support for variadic functions
        Simply incremementing a stack counter won't identify no argument cases"""
        argument_count = 0

        for token in self.output[end_index:]:
            if isinstance(token, Operator):
                # Account for operator arguments
                for i in range(token.arguments):
                    argument_count -= 1

                # Account for returned values
                if token.returns_value:
                    argument_count += 1
            
            elif isinstance(token, Term):
                argument_count += 1

        # Anything left on stack was an argument
        return argument_count
    
    def handle_right_parenthesis(self, token):
        operator_stack = self.operator_stack

        while operator_stack and not isinstance(operator_stack[-1], LeftParenthesis):
            operator = operator_stack.pop()
            self.output.append(operator)     
                    
        try:
            left_parenthesis = operator_stack.pop()

        except IndexError as err:
            raise ValueError("Unbalanced Parenthesis") from err

        if operator_stack and isinstance(operator_stack[-1], FunctionOperator):
            function = operator_stack.pop()
            function.arguments = self.count_arguments_until(self.argument_stack.pop())

            self.output.append(function)
    
    def handle_left_parenthesis(self, token):
        self.operator_stack.append(token)
    
    def is_unary(self, previous_token, token):
        return token is sub_op and not isinstance(previous_token, (Term, RightParenthesis))
    
    def is_implicit_multiplication(self, previous_token):
        return isinstance(previous_token, (Constant, RightParenthesis))
    
    def __call__(self):        
        self.output.clear()
        self.operator_stack.clear()
        self.argument_stack.clear()
    
        waiting_closure = False
        
        for previous_token, token, next_token in sliding_window(self.expression):

            if isinstance(token, Operator):
                # Support in place negative signs 
                if self.is_unary(previous_token, token):
                    self.handle_operator(self.expression.operators["UNARY"])

                else:
                    self.handle_operator(token)

            elif isinstance(token, Delimiter):                
                self.handle_delimiter(token)
            
            elif isinstance(token, RightParenthesis):
                self.handle_right_parenthesis(token)
                
            else:
                # Implicit multiplication sign
                if self.is_implicit_multiplication(previous_token):
                    self.handle_operator(mul_op)

                if isinstance(token, Term):
                    self.handle_term(token)
                
                elif isinstance(token, LeftParenthesis):
                    self.handle_left_parenthesis(token)
                            
        while self.operator_stack:
            operator = self.operator_stack.pop()
            if isinstance(operator, LeftParenthesis):
                raise ValueError("Unbalanced Parenthesis")
            
            self.output.append(operator)
        
        return self.output


class RPNSolver:

    def __init__(self, tokens, *arguments, name=""):
        self.tokens = tokens
        self.name = name
        self.arguments = arguments
    
    def __repr__(self):
        return "<RPNSolver {}: [{}]>".format(self.name, ', '.join(self.arguments))
    
    def __call__(self, *arguments, variables=None):
        if variables is None:
            variables = {}
        variables.update(zip(self.arguments, arguments))

        stack = []
        for token in self.tokens:
            if isinstance(token, Operator):
                arguments = list(reversed([stack.pop() for i in range(token.arguments)]))
                result = token.evaluate(variables, *arguments)
                # Support variadic operations
                if token.returns_value:
                    stack.append(result)
            
            elif isinstance(token, Term):
                stack.append(token)

        result = stack.pop().evaluate(variables)
        assert not stack, "Invalid Stack operation occured"
        return result

            
math_info = MathematicInfo()
functions = math_info.functions.copy()
constants = math_info.constants.copy()


def create_function(expression, *args, name=None):
    rpn = RPNTokenizer(expression, symbol_table=functions)
    tokens = rpn()
    solver = RPNSolver(tokens, *args, name=name)
    return functools.partial(solver, variables=constants)


functions['E'] = sigma  
functions['switch'] = ternary
functions['sum'] = _sum
functions['unpack'] = lambda x, y: x(*y)
functions['trapezium'] = create_function("h/2 * (s + e + 2*i)", 'h', 's', 'e', 'i', name="Trapezium Rule")
functions['quadratic'] = create_function("(-b + d * sqrt((b^2 - 4a*c)))/ (2a)", 'a', 'b', 'c', 'd', name="Quadratic")
functions['dbg'] = print
constants['g'] = 9.8


def interactive(variables=None):
    if variables is None:
        variables = constants

    try:
        exp=input(">>> ")
        func = create_function(exp)
        result = func(variables=variables)
        print(">>>", result)
        interactive(variables)
    
    except EOFError:
        print(">>> QUIT INTERPRETER")
        return

    except Exception as err:
        print(">>> {}".format(err))
        interactive()


def expression():
    exp = input("Enter expression:\n")
    args = input("Enter arguments:\n").split(' ')
    name = input("Enter name:\n")
    func = create_function(exp, *args, name=name)
    functions[name] = func
    return func
