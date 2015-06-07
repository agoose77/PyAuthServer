from game_system.enums import EvaluationState
from game_system.pathfinding.algorithm import AStarAlgorithm, PathNotFoundException

from network.structures import factory_dict

from collections import defaultdict
from operator import attrgetter

__all__ = "Goal", "Action", "Planner", "GOAPAIManager", "ActionAStarNode", "GOAPAStarNode", "Goal"


class Goal:
    state = {}
    priority = 0


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

    def check_procedural_precondition(self, blackboard):
        return True

    def get_procedural_cost(self, blackboard):
        return self.cost

    def evaluate(self, blackboard):
        return EvaluationState.success


class GOAPAStarNode:

    def __init__(self, current_state, goal_state):
        self.current_state = current_state
        self.goal_state = goal_state

    @property
    def is_solution(self):
        return not self.unsatisfied_state

    @property
    def unsatisfied_state(self):
        current_state = self.current_state
        return [k for k, v in self.goal_state.items() if not current_state[k] == v]


class GOAPGoalNode(GOAPAStarNode):

    def __repr__(self):
        return "<GOAPGoalNode: {}>".format(self.goal_state)


@total_ordering
class ActionAStarNode(GOAPAStarNode):

    def __init__(self, action):
        effects = action.effects.copy()
        preconditions = action.preconditions.copy()

        super().__init__(current_state=effects, goal_state=preconditions)

        self.action = action

    def __lt__(self, other):
        return self.action.precedence < other.action.precedence

    def __repr__(self):
        return "<ActionNode {}>".format(self.action.__class__.__name__)

    def get_procedural_cost(self, blackboard):
        return self.action.get_procedural_cost(blackboard)

    def update_state(self, blackboard, parent):
        # Get state of preconditions
        action_preconditions = self.action.preconditions

        # Update state from parent, current preconditions, effects
        self.current_state = parent.current_state.copy()
        self.current_state.update({k: blackboard.get(k) for k in action_preconditions if k not in self.current_state})
        self.current_state.update(self.action.effects)

        # Update goal state from action preconditions
        self.goal_state = parent.goal_state.copy()
        self.goal_state.update(action_preconditions)


class Planner:

    def __init__(self, actions, blackboard):
        self.actions = actions
        self.blackboard = blackboard

        self.effects_to_actions = self.get_actions_by_effects(actions)
        self.actions_to_astar = factory_dict(lambda a: ActionAStarNode(a))
        self.finder = AStarAlgorithm(self.get_neighbours, self.get_heuristic_cost, self.get_g_cost, self.check_complete)

    def check_complete(self, node, path):
        ordered_path = self.finder.reconstruct_path(node, path)
        print("{}:\n\t{}\n\t{}\n".format(node, node.goal_state, node.current_state, node.current_state))
        if not node.is_solution:
            return False
        
        ordered_path = self.finder.reconstruct_path(node, path)
        current_state = self.blackboard.copy()

        for node_ in ordered_path:
            current_state.update(node_.current_state)

        for key, goal_value in node.goal_state.items():
            current_value = current_state[key]
            if not current_value == goal_value:
                return False

        return True

    @staticmethod
    def get_actions_by_effects(actions):
        """Associate effects with appropriate actions

        :param actions: valid actions
        """
        mapping = defaultdict(list)

        for action in actions:
            for effect in action.effects:
                mapping[effect].append(action)

        return mapping

    def get_g_cost(self, node_a, node_b):
        node_b.update_state(self.blackboard, node_a)
        return node_b.get_procedural_cost(self.blackboard)

    @staticmethod
    def get_heuristic_cost(node):
        """Rough estimate of cost of node, based upon satisfaction of goal state

        :param node: node to evaluate heuristic
        """
        return len(node.unsatisfied_state)

    def get_neighbours(self, node):
        """Find neighbours of node, which fulfil unsatisfied state

        :param node: node to evaluate
        """
        unsatisfied_effects = node.unsatisfied_state
        effects_to_actions = self.effects_to_actions
        blackboard = self.blackboard

        neighbours = []
        node_map = self.actions_to_astar
        for effect in unsatisfied_effects:
            try:
                actions = effects_to_actions[effect]

            except KeyError:
                continue

            effect_neighbours = [node_map[a] for a in actions if a.check_procedural_precondition(blackboard)]
            neighbours.extend(effect_neighbours)

        neighbours.sort(key=attrgetter("action.precedence"))
        return neighbours

    def build(self, goal_state):
        blackboard = self.blackboard
        current_state = {k: blackboard.get(k) for k in goal_state}

        goal_node = GOAPGoalNode(current_state, goal_state)
        node_path = self.finder.find_path(goal_node)

        path = [node.action for node in list(node_path)[1:]]
        path.reverse()
        print(path)
        return path


class GOAPPlannerFailedException(Exception):
    pass


class GOAPAIPlan:

    def __init__(self, actions):
        self._actions = iter(actions)
        self.current_action = next(self._actions)

    def update(self, blackboard):
        state = self.current_action.evaluate(blackboard)

        if state == EvaluationState.success:
            try:
                self.current_action = next(self._actions)

            # Unless we're finished
            except StopIteration:
                return EvaluationState.success

            return self.update(blackboard)

        return state


class GOAPAIManager:

    def __init__(self, blackboard, goals, actions):
        self.actions = actions
        self.goals = sorted(goals, key=attrgetter("priority"), reverse=True)
        self.blackboard = blackboard
        self.planner = Planner(self.actions, self.blackboard)

        self._plan = None

    def find_best_plan(self):
        build_plan = self.planner.build
        for goal in self.goals:
            try:
                path = build_plan(goal.state)

            except PathNotFoundException:
                continue

            return GOAPAIPlan(path)

        raise GOAPPlannerFailedException("Couldn't find suitable plan")

    def update(self):
        blackboard = self.blackboard

        # Rebuild plan
        if self._plan is None:
            try:
                self._plan = self.find_best_plan()

            except GOAPPlannerFailedException as err:
                print(err)

        else:
            plan_state = self._plan.update(blackboard)

            if plan_state == EvaluationState.failure:
                print("Plan failed: {}".format(self._plan.current_action))
                self._plan = None
                self.update()

            elif plan_state == EvaluationState.success:
                self._plan = None
                self.update()



