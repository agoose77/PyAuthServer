from network.signals import SignalListener

from ...enums import EvaluationState

from functools import wraps
from random import shuffle

__all__ = "CompositeNode", "DecoratorNode", "SequenceNode", "SelectorNode", "SucceederNode", "RepeaterNodeBase",\
          "RepeatForNode", "RepeatUntilFailNode", "RandomiserNode", "InverterNode", "SignalListenerNode", "Node"


class StateManager(type):
    """Meta class to update node state with return of evaluation"""

    def __new__(metacls, name, bases, attrs):
        try:
            evaluate_function = attrs["evaluate"]
            attrs["evaluate"] = metacls.evaluate_wrapper(evaluate_function)

        finally:
            return super().__new__(metacls, name, bases, attrs)

    @staticmethod
    def evaluate_wrapper(func):
        """Wrap function in setter

        :param func: function to evaluate node state
        """
        @wraps(func)
        def wrapper(self, blackboard):
            if self.state == EvaluationState.ready:
                self.on_enter()

            state = func(self, blackboard)
            self.state = state

            if state != EvaluationState.running:
                self.on_exit()

            return state

        return wrapper


class Node(metaclass=StateManager):
    """Base class for Behaviour tree nodes"""

    def __init__(self):
        self.state = EvaluationState.ready
        self.parent = None

    def evaluate(self, blackboard):
        """Evaluate the node state"""
        pass

    def on_enter(self, blackboard):
        pass

    def on_exit(self, blackboard):
        pass


class CompositeNode(Node):
    """Base class for Behaviour tree nodes with children"""

    def __init__(self, *children):
        super().__init__()

        self.children = list(children)

        for child in children:
            child.parent = self

    def reset(self):
        """Reset this node's (and its children's) state to ready"""
        self.state = EvaluationState.ready

        for child in self.children:
            if hasattr(child, "reset"):
                child.reset()


class DecoratorNode(CompositeNode):
    """Decorates a single child Behaviour tree node"""

    def __init__(self, child):
        super().__init__()

        self.child = child
        child.parent = self

    def evaluate(self, blackboard):
        child = self.child
        return child.evaluate(blackboard)


class SequenceNode(CompositeNode):
    """Evaluates children in sequential order.

    If child fails to succeed, evaluation is considered a failure, otherwise a success
    """

    def evaluate(self, blackboard):
        """Evaluates the node's (and its children's) state.

        :returns: the state of the first node to return a non-success state
        """
        success = EvaluationState.success

        state = success
        for child in self.children:
            state = child.evaluate(blackboard)

            if state != success:
                break

        return state


class SelectorNode(CompositeNode):
    """Evaluates children in sequential order.

    If any child succeeds, evaluation is considered a success, else a failure.
    """

    def evaluate(self, blackboard):
        """Evaluates the node's (and its children's) state.

        Returns success if any node succeeds, else failure.
        """
        success = EvaluationState.success

        for child in self.children:
            state = child.evaluate(blackboard)

            if state == success:
                return success

        return EvaluationState.failure


class SucceederNode(DecoratorNode):
    """Evaluates child node and returns a success"""

    def evaluate(self, blackboard):
        super().evaluate(blackboard)

        return EvaluationState.success


class RepeaterNodeBase(DecoratorNode):
    """Base class for repeating decorator nodes

    Repeatedly evaluates child node according to implementation.
    """

    def iterations(self):
        raise NotImplementedError("RepeaterNode is base class for repeaters")

    def evaluate(self, blackboard):
        state = EvaluationState.success

        evaluate = self.child.evaluate
        for state in self.iterations():
            evaluate(blackboard)

        return state


class RepeatUntilFailNode(RepeaterNodeBase):
    """Repeats evaluation of decorated node until failure.

    Returns success state on completion.
    """

    def iterations(self):
        success = EvaluationState.success
        failure = EvaluationState.failure

        child = self.child
        while child.state != failure:
            yield success


class RepeatForNode(RepeaterNodeBase):
    """Repeats evaluation of decorated node for N iterations

    Returns state of child on completion.
    """

    def __init__(self, count, child):
        super().__init__(child)

        self.count = count

    def iterations(self):
        child = self.child

        for i in range(self.count):
            yield child.state


class RandomiserNode(DecoratorNode):
    """Decorates CompositeNode instance

     Shuffles node's children before evaluation, returns state of node.
     """

    def evaluate(self, blackboard):
        child = self.child
        shuffle(child.children)
        return child.evaluate(blackboard)


class InverterNode(DecoratorNode):
    """Inverts the state of evaluated node.

    Does not invert running (as it has no counterpart).
    """

    def evaluate(self, blackboard):
        state = self.child.evaluate(blackboard)

        if state == EvaluationState.failure:
            return EvaluationState.failure

        if state == EvaluationState.success:
            return EvaluationState.failure

        return EvaluationState.running


class SignalListenerNode(Node, SignalListener):
    """Returns success state if appropriate signal is received."""

    def __init__(self, signal_cls):
        super().__init__()

        self._parent_identifier = None
        self._received_signal = False

        signal_cls.subscribe(self, self._handle_signal)
        self.signal_cls = signal_cls

    @property
    def parent_identifier(self):
        return self._parent_identifier

    @parent_identifier.setter
    def parent_identifier(self, identifier):
        old_id, self._parent_identifier = self._parent_identifier, identifier

        self.change_signal_handler(old_id, identifier)

    def _handle_signal(self):
        self._received_signal = True

    def change_signal_handler(self, old_id, id_):
        """Change parent dispatcher for signaller

        :param old_id: previous parent identifier
        :param id_: new parent identifier
        """
        self.signal_cls.remove_parent(self, old_id)
        self.signal_cls.set_parent(self, id_)

    def evaluate(self, blackboard):
        return EvaluationState.success if self._received_signal else EvaluationState.failure

    def on_exit(self, blackboard):
        self._received_signal = False