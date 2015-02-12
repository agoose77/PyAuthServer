from ..enums import EvaluationState
from ..pathfinding.algorithm import AStarAlgorithm, PathNotFoundException

from collections import defaultdict, namedtuple
from operator import attrgetter

__all__ = "Goal", "Action", "Planner", "GOAPAIManager", "ActionAStarNode", "GOAPAStarNode", "Goal"


Goal = namedtuple("Goal", "state priority")


def total_ordering(cls):
    'Class decorator that fills-in missing ordering methods'
    convert = {
        '__lt__': [('__gt__', lambda self, other: other < self),
                   ('__le__', lambda self, other: not other < self),
                   ('__ge__', lambda self, other: not self < other)],
        '__le__': [('__ge__', lambda self, other: other <= self),
                   ('__lt__', lambda self, other: not other <= self),
                   ('__gt__', lambda self, other: not self <= other)],
        '__gt__': [('__lt__', lambda self, other: other > self),
                   ('__ge__', lambda self, other: not  other > self),
                   ('__le__', lambda self, other: not self > other)],
        '__ge__': [('__le__', lambda self, other: other >= self),
                   ('__gt__', lambda self, other: not other >= self),
                   ('__lt__', lambda self, other: not self >= other)]
    }
    if hasattr(object, '__lt__'):
        roots = [op for op in convert if getattr(cls, op) is not getattr(object, op)]
    else:
        roots = set(dir(cls)) & set(convert)

    assert roots, 'must define at least one ordering operation: < > <= >='
    root = max(roots)       # prefer __lt __ to __le__ to __gt__ to __ge__
    for opname, opfunc in convert[root]:
        if opname not in roots:
            opfunc.__name__ = opname
            opfunc.__doc__ = getattr(int, opname).__doc__
            setattr(cls, opname, opfunc)

    return cls


class Action:

    cost = 0
    precedence = 0

    effects = {}
    preconditions = {}

    def procedural_precondition(self, blackboard):
        return True

    def evaluate(self, blackboard):
        return EvaluationState.success


class GOAPAStarNode:

    def __init__(self, current_state, goal_state):
        self.current_state = current_state
        self.goal_state = goal_state

    @property
    def finished(self):
        return not self.unsatisfied_state

    @property
    def unsatisfied_state(self):
        current_state = self.current_state
        return [k for k, v in self.goal_state.items() if not current_state[k] == v]


@total_ordering
class ActionAStarNode(GOAPAStarNode):

    def __init__(self, action):
        super().__init__(action.effects.copy(), action.preconditions.copy())

        self.action = action
        self.cost = action.cost

    def __lt__(self, other):
        return self.action.precedence < other.action.precedence

    def __repr__(self):
        return "<ActionNode {}>".format(self.action.__class__.__name__)

    def update_state(self, blackboard, parent):
        action_preconditions = self.action.preconditions
        current_precondition_state = {k: blackboard.get(k) for k in action_preconditions}

        self.current_state = parent.current_state.copy()
        self.current_state.update(self.action.effects)
        self.current_state.update(current_precondition_state)

        self.goal_state = parent.goal_state.copy()
        self.goal_state.update(action_preconditions)
 

class Planner:

    def __init__(self, actions, blackboard):
        self.actions = actions
        self.blackboard = blackboard

        self.effects_to_actions = self.get_actions_by_effects(actions)

        self.finder = AStarAlgorithm(self.get_neighbours, self.get_heuristic_cost, self.get_g_cost, self.check_complete)

    def check_complete(self, node, path):
        if not node.finished:
            return False
        
        ordered_path = self.finder.reconstruct_path(node, path)
        current_state = self.blackboard.copy()

        for node in ordered_path:
            current_state.update(node.current_state)
        
        for key, goal_value in node.goal_state.items():
            current_value = current_state[key]
            if not current_value == goal_value:
                return False
             
        return True

    @staticmethod
    def get_actions_by_effects(actions):
        mapping = defaultdict(list)

        for action in actions:
            for effect in action.effects:
                mapping[effect].append(action)

        return mapping

    def get_g_cost(self, node_a, node_b):
        node_b.update_state(self.blackboard, node_a)
        
        return node_b.cost

    @staticmethod
    def get_heuristic_cost(node):
        return len(node.unsatisfied_state)

    def get_neighbours(self, node):
        unsatisfied_effects = node.unsatisfied_state
        effects_to_actions = self.effects_to_actions
        blackboard = self.blackboard
        
        for effect in unsatisfied_effects:
            try:
                actions = effects_to_actions[effect]

            except KeyError:
                continue
            
            yield from [ActionAStarNode(a) for a in actions if a.procedural_precondition(blackboard)]
        
    def build(self, goal_state):
        blackboard = self.blackboard
        current_state = {k: blackboard.get(k) for k in goal_state}

        goal_node = GOAPAStarNode(current_state, goal_state)
        node_path = self.finder.find_path(goal_node)

        path = [node.action for node in list(node_path)[1:]]
        path.reverse()

        return path


class GOAPAIManager:

    def __init__(self, blackboard, goals, actions):
        self.actions = actions
        self.goals = sorted(goals, key=attrgetter("priority"), reverse=True)
        self.blackboard = blackboard
        self.planner = Planner(self.actions, self.blackboard)

        self._plan = None

    def update(self):
        build_plan = self.planner.build
        blackboard = self.blackboard
        plan = self._plan

        if not plan:
            for goal in self.goals:
                try:
                    path = build_plan(goal.state)

                except PathNotFoundException:
                    continue

                plan = path
                break

            else:
                return

            self.plan = plan

        action = plan[0]
        state = action.__call__(blackboard)

        if state == EvaluationState.success:
            plan[:] = plan[1:]