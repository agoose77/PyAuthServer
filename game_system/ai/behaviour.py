from ..enums import EvaluationState
from network.signals import SignalListener

from functools import wraps
from random import shuffle

__all__ = "LeafNode", "CompositeNode", "DecoratorNode", "SequenceNode", "SelectorNode", "SucceederNode", \
          "RepeaterNode", "RepeatForNode", "RepeatUntilFailNode", "RandomiserNode", "InverterNode"


class StateManager(type):
    """Meta class to update node state with return of evaluation"""

    def __new__(metacls, name, bases, attrs):
        attrs["evaluate"] = metacls.evaluate_wrapper(attrs["evaluate"])
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


class LeafNode(Node):
    """Final (leaf) node in behaviour tree"""


class CompositeNode(LeafNode):
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

    def evaluate(self, blackboard):
        """Evaluates the node's (and its children's) state.

        :returns: the state of the first node to succeed or
        """
        success = EvaluationState.success

        state = success
        for child in self.children:
            state = child.evaluate(blackboard)

            if state == success:
                break

        return state


class SucceederNode(DecoratorNode):

    def evaluate(self, blackboard):
        super().evaluate(blackboard)

        return EvaluationState.success


class RepeaterNode(DecoratorNode):

    def iterations(self):
        raise NotImplementedError("RepeaterNode is base class for repeaters")

    def evaluate(self, blackboard):
        state = EvaluationState.success

        evaluate = self.child.evaluate
        for state in self.iterations():
            evaluate(blackboard)

        return state


class RepeatUntilFailNode(RepeaterNode):

    def iterations(self):
        success = EvaluationState.success
        failure = EvaluationState.failure

        child = self.child
        while child.state != failure:
            yield success


class RepeatForNode(RepeaterNode):

    def __init__(self, count, child):
        super().__init__(child)

        self.count = count

    def iterations(self):
        child = self.child

        for i in range(self.count):
            yield child.state


class RandomiserNode(DecoratorNode):

    def evaluate(self, blackboard):
        child = self.child
        shuffle(child.children)
        return child.evaluate(blackboard)


class InverterNode(DecoratorNode):

    def evaluate(self, blackboard):
        state = self.child.evaluate(blackboard)

        if state == EvaluationState.failure:
            return EvaluationState.failure

        if state == EvaluationState.success:
            return EvaluationState.failure

        return EvaluationState.running


class SignalLeafNode(LeafNode, SignalListener):

    def __init__(self):
        super().__init__()

        self.register_signals()


class OnSignalNode(SignalLeafNode):

    SIGNAL_CLS = None

    def __init__(self):
        self._parent_identifier = None
        self._state = False

        self.SIGNAL_CLS.subscribe(self, self.activate)

    def change_signal_handler(self, old_id, id_):
        """Change parent dispatcher for signaller

        :param old_id: previous parent identifier
        :param id_: new parent identifier
        """
        self.SIGNAL_CLS.remove_parent(self, old_id)
        self.SIGNAL_CLS.set_parent(self, id_)

    def reset(self):
        self._state = False

        super().reset()

    def activate(self):
        self._state = True

    @property
    def parent_identifier(self):
        return self._parent_identifier

    @parent_identifier.setter
    def parent_identifier(self, id_):
        old_id, self._parent_identifier = self._parent_identifier, id_

        self.change_signal_handler(old_id, id_)