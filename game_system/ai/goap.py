from ..pathfinding.algorithm import AStarAlgorithm

from collections import defaultdict

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
                   ('__ge__', lambda self, other: not other > self),
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

    def evaluate(self, blackboard):
        pass

    def procedural_precondition(self, blackboard):
        pass


class GoalAStarNode:

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
class ActionAStarNode:

    def __init__(self, action):
        self.action = action
        self.cost = action.cost
        self.current_state = action.effects.copy()
        self.goal_state = action.preconditions.copy()

    def __lt__(self, other):
        return self.action.precedence < other.action.precedence

    @property
    def unsatisfied_state(self):
        current_state = self.current_state
        return [k for k, v in self.goal_state.items() if not current_state[k] == v]

    @property
    def finished(self):
        return self.current_state == self.goal_state

    def update_state(self, agent_state, parent):
        action_preconditions = self.action.preconditions
        current_precondition_state = {k: agent_state.get(k) for k in action_preconditions}

        self.current_state = parent.current_state.copy()
        self.current_state.update(self.action.effects)
        self.current_state.update(current_precondition_state)

        self.goal_state = parent.goal_state.copy()
        self.goal_state.update(action_preconditions)

    def __repr__(self):
        return "<ActionNode {}>".format(self.action.__class__.__name__)


class Planner:

    def __init__(self, actions):
        self.actions = actions
        self.agent_state = {}

        self.effects_to_actions = self.get_actions_by_effects(actions)
        self.actions_to_nodes = {action: ActionAStarNode(action) for action in actions}

        self.finder = AStarAlgorithm(self.get_neighbours, self.get_heuristic_cost, self.get_g_cost, self.check_complete)

    def check_complete(self, node, path):
        if not node.finished:
            return False

        ordered_path = self.finder.reconstruct_path(node, path)
        current_state = self.agent_state.copy()

        for node in ordered_path:
            node_current_state = dict(node.current_state)
            current_state.update(node_current_state)

        # If we have no unsatisfied state (pretty sure we don't need this)
        return not set(node.goal_state) - set(current_state)

    @staticmethod
    def get_actions_by_effects(actions):
        mapping = defaultdict(list)

        for action in actions:
            for effect in action.effects:
                mapping[effect].append(action)

        return mapping

    def get_g_cost(self, node_a, node_b):
        node_b.update_state(self.agent_state, node_a)

        return node_b.cost

    @staticmethod
    def get_heuristic_cost(node):
        return len(node.unsatisfied_state)

    def get_neighbours(self, node):
        unsatisfied_effects = node.unsatisfied_state
        effects_to_actions = self.effects_to_actions
        actions_to_nodes = self.actions_to_nodes

        for effect in unsatisfied_effects:
            try:
                actions = effects_to_actions[effect]

            except KeyError:
                continue

            yield from [actions_to_nodes[a] for a in actions if a.procedural_precondition(self.agent_state)]

    def build(self, goal_state):
        agent_state = self.agent_state
        current_state = {k: agent_state.get(k) for k in goal_state}

        goal_node = GoalAStarNode(current_state, goal_state)

        node_path = self.finder.find_path(goal_node)

        path = [node.action for node in list(node_path)[1:]]
        path.reverse()

        return path


def main():
    actions = []
    planner = Planner(actions)
    planner.agent_state = {"has_parents": True, "has_axe": True}
    path = planner.build({"has_firewood": True})
    print(path)


if __name__ == "__main__":
    main()