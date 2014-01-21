from operator import attrgetter
from network import Enum, Signal, SignalListener
from itertools import islice
from contextlib import contextmanager


class EvaluationState(metaclass=Enum):
    values = "success", "failure", "running", "error", "ready"


class BehaviourTree:

    def __init__(self, signaller, root=None):
        self.signaller = signaller
        self.blackboard = self.new_blackboard()

        if root is None:
            root = SelectorNode()
        self.root = root

        self._last_visited = set()

    @property
    def root(self):
        return self._root

    @root.setter
    def root(self, value):
        self._root = value
        self._root.change_signaller(self.signaller)

    def new_blackboard(self):
        return {"_visited": set()}

    def debug(self):
        self._root.print_tree()

    def update(self, delta_time):
        blackboard = self.blackboard
        blackboard['delta_time'] = delta_time
        self.reset_visited(blackboard)
        self._root.update(blackboard)

    def reset(self):
        self._root.reset(self.blackboard)
        self._last_visited.clear()
        self.blackboard = self.new_blackboard()

    def reset_visited(self, blackboard):
        """Ensure that nodes are cleared
        In case a branch isn't evaluated
        @param blackboard: blackboard instance"""
        visited = blackboard['_visited']
        last_visited = self._last_visited

        for node in visited:
            if node.state != EvaluationState.running:
                node.state = EvaluationState.ready

            if node in last_visited:
                last_visited.remove(node)

        for node in last_visited:
            node.reset(self.blackboard)

        self._last_visited = visited
        blackboard['_visited'] = set()


class LeafNode(SignalListener):

    def __init__(self):
        super().__init__()

        self.register_signals()
        self._signal_parent = self

        self.state = EvaluationState.ready
        self.name = ""

    def change_signaller(self, parent):
        parent.register_child(self, greedy=True)
        if self._signal_parent is not self:
            self._signal_parent.unregister_child(self, greedy=True)
        self._signal_parent = parent

    def evaluate(self, blackboard):
        pass

    def on_enter(self, blackboard):
        pass

    def on_exit(self, blackboard):
        pass

    def update(self, blackboard):
        # Invoke entry if neccessary
        if self.state != EvaluationState.running:
            self.state = EvaluationState.running
            self.on_enter(blackboard)

        self.state = self.evaluate(blackboard)

        # Invoke exit if neccessary
        if not self.state in (EvaluationState.ready, EvaluationState.running):
            self.on_exit(blackboard)

        # Remember visit
        blackboard['_visited'].add(self)

    def reset(self, blackboard):
        self.state = EvaluationState.ready
        self.on_exit(blackboard)

    def print_tree(self, index=0):
        print('   ' * index, '->', index, self)

    def __repr__(self):
        return "[{} {}] : {}".format(self.__class__.__name__,
                                     self.name,
                                     EvaluationState[self.state])


class InnerNode(LeafNode):

    def __init__(self, *children):
        super().__init__()

        self._children = []

        for child in children:
            self.add_child(child)

    @property
    def children(self):
        return self._children

    def add_child(self, child, index=None):
        if index is None:
            self._children.append(child)

        else:
            self._children.insert(index, child)

        child.change_signaller(self._signal_parent)

    def change_signaller(self, identifier):
        super().change_signaller(identifier)

        for child in self.children:
            child.change_signaller(identifier)

    def print_tree(self, index=0):
        super().print_tree(index)

        if self.children:
            print()

        for child in self.children:
            child.print_tree(index + 1)

        if self.children:
            print()

    def remove_child(self, child):
        self._children.remove(child)
        child.change_signaller(child)

    def reset(self, blackboard):
        super().reset(blackboard)

        for child in self._children:
            child.reset(blackboard)


class ResumableNode(InnerNode):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._resume_index = 0
        self.should_restart = False

    @property
    def resume_index(self):
        return self._resume_index

    @resume_index.setter
    def resume_index(self, value):
        self._resume_index = value

    def on_exit(self, blackboard):
        self.resume_index = 0


class SelectorNode(ResumableNode):

    def evaluate(self, blackboard):
        resume_index = 0 if self.should_restart else self.resume_index
        remembered_resume = False

        running_state = EvaluationState.running
        success_state = EvaluationState.success

        for index, child in enumerate(
                                  islice(self.children, resume_index, None)):
            child.update(blackboard)

            if child.state == running_state:
                remembered_resume = True
                break

            if child.state == success_state:
                break

        else:
            return EvaluationState.failure

        # Copy child's state
        if remembered_resume:
            self.resume_index = index + resume_index
            child = self.children[self.resume_index]

        return child.state


class ConcurrentNode(ResumableNode):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._failure_limit = 1

    @property
    def failure_limit(self):
        return self._failure_limit

    def on_exit(self, blackboard):
        self.resume_index = 0

    def evaluate(self, blackboard):
        resume_index = 0 if self.should_restart else self.resume_index
        remembered_resume = False
        failure_limit = self.failure_limit
        failed_total = 0

        running_state = EvaluationState.running
        success_state = EvaluationState.success

        for index, child in enumerate(
                                  islice(self.children, resume_index, None)):
            child.update(blackboard)

            # Increment failure count (anything that isn't a success)
            if child.state != success_state:
                failed_total += 1

            # Remember the first child that needed completion
            if (child.state == running_state
                            and not remembered_resume):
                remembered_resume = True
                self.resume_index = resume_index + index

            # At the limit we then return the last/ last running child's status
            if failed_total == failure_limit:
                if remembered_resume:
                    return self.children[self.resume_index].state

                else:
                    return child.state

        return success_state


class SequenceNode(ConcurrentNode):

    @property
    def failure_limit(self):
        return 1


class LoopNode(SequenceNode):

    def evaluate(self, blackboard):
        state = None
        evaluate = super().evaluate

        while not state in (EvaluationState.failure, EvaluationState.error):
            state = evaluate(blackboard)

        return state


class SignalLeafNode(LeafNode):

    @property
    def signaller(self):
        if self._signal_parent is self:
            return None
        return self._signal_parent


class SignalInnerNode(InnerNode):

    @property
    def signaller(self):
        if self._signal_parent is self:
            return None
        return self._signal_parent
