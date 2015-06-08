from game_system.enums import EvaluationState
from game_system.pathfinding.algorithm import AStarAlgorithm, PathNotFoundException, AStarNode, AStarGoalNode

from network.structures import factory_dict

from .priority_queue import PriorityQueue

from collections import defaultdict, deque
from operator import attrgetter
from sys import float_info

__all__ = "Goal", "Action", "Planner", "GOAPAIManager", "ActionAStarNode", "GOAPAStarNode", "Goal"


MAX_FLOAT = float_info.max


def total_ordering(cls):
    """Class decorator that fills-in missing ordering methods"""
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


class Variable:
    """Variable value for effects and preconditions

    Must be resolved during plan-time
    """

    def __init__(self, key):
        self._key = key

    def resolve(self, blackboard):
        """Determine true value of variable

        :param blackboard: AI blackboard dictionary
        """
        return blackboard[self._key]


class Goal:

    state = {}
    priority = 0

    @property
    def relevance(self):
        return self.priority


class Action:

    cost = 1
    precedence = 0

    effects = {}
    preconditions = {}

    def check_procedural_precondition(self, blackboard):
        return True

    def get_procedural_cost(self, blackboard):
        return self.cost

    def evaluate(self, blackboard):
        return EvaluationState.success

    def __repr__(self):
        return self.__class__.__name__


class IGOAPAStarNode:

    f_score = MAX_FLOAT

    def __init__(self, planner):
        self.current_state = {}
        self.goal_state = {}

        self.planner = planner

    @property
    def is_solution(self):
        """If this node is the start node for a solution"""
        return not self.unsatisfied_state

    @property
    def unsatisfied_state(self):
        """Return the keys of the unsatisfied state symbols between the goal and current state"""
        current_state = self.current_state
        return [k for k, v in self.goal_state.items() if not current_state[k] == v]

    @property
    def neighbours(self):
        """Find neighbours of node, which fulfil unsatisfied state

        :param node: node to evaluate
        """
        return self.planner.get_neighbour_nodes_for_effects(self.unsatisfied_state)


class GOAPAStarNode(IGOAPAStarNode, AStarNode):
    pass


class GOAPGoalNode(IGOAPAStarNode, AStarGoalNode):

    def __repr__(self):
        return "<GOAPGoalNode: {}>".format(self.goal_state)

    def get_h_score_from(self, node):
        """Rough estimate of cost of node, based upon satisfaction of goal state

        :param node: node to evaluate heuristic
        """
        node.update_internal_states()
        return len(node.unsatisfied_state)


@total_ordering
class ActionAStarNode(GOAPAStarNode):
    """A* Node with associated GOAP action"""

    def __init__(self, planner, action):
        super().__init__(planner)

        self.action = action

    def __lt__(self, other):
        return self.action.precedence < other.action.precedence

    def __repr__(self):
        if hasattr(self.action, "repr"):
            c = self.action.repr(self)
        else:
            c = self.action.__class__.__name__

        if hasattr(self.parent, "action"):
            if hasattr(self.parent.action, "repr"):
                h = self.parent.action.repr(self.parent)
            else:
                h = self.parent.action.__class__.__name__
        else:
            h = ""
        return "<ActionNode {} ({})>".format(c, h)

    def get_g_score_from(self, node):
        """Determine procedural (or static) cost of this action

        :param node: node to move from (unused)
        """
        # Update world states
        self.current_state.update(node.current_state)
        self.goal_state.update(node.goal_state)

        return self.action.get_procedural_cost(self.planner.blackboard)

    def update_state_with(self, state, source,sc=None):
        """Update one state dictionary with another

        Resolves state from goal state (for Variable instances)

        :param state: state to update
        :param source: source from which to update state
        """
        if sc is None:sc=source
        for key, value in source.items():
            if isinstance(value, Variable):
                value = value.resolve(sc)

            state[key] = value

    def update_internal_states(self):
        """Update internal current and goal states, according to action effects and preconditions

        Required for heuristic estimate
        """
        # Get state of preconditions
        action_preconditions = self.action.preconditions
        blackboard = self.planner.blackboard

        # Update current state with current precondition values
        self.current_state.update({k: blackboard.get(k) for k in action_preconditions if k not in self.current_state})

        # Update current state with applied effects
        self.update_state_with(self.current_state, self.action.effects, sc=self.goal_state)

        # Update goal state from action preconditions
        self.update_state_with(self.goal_state, action_preconditions)
      #  print(self, self.goal_state, self.current_state)
        # 1
        # Solve unsatisfied props
        # Get value from goal, resolve from goal if var
        # Set current from value

        # 2
        # Add precond from action to goal
        # If variable get from goal state then set

        # 3
        # Iterate over goal properties
        # If prop already in curr ignore
        # Add missing props to current
        # Get values from AI current state


def f(d):
    return "[{}]".format(", ".join("{}={}".format(k, v) for k, v in d.items()))


class Planner(AStarAlgorithm):

    def __init__(self, action_classes, blackboard):
        self.action_classes = action_classes
        self.blackboard = blackboard

        self.effects_to_action_classes = self.get_action_classes_by_effects(action_classes)

    def find_plan_for_goal(self, goal_state):
        """Find shortest plan to produce goal state

        :param goal_state: state of goal
        """
        blackboard = self.blackboard

        goal_node = GOAPGoalNode(self)

        goal_node.current_state = {k: blackboard.get(k) for k in goal_state}
        goal_node.goal_state = goal_state

        node_path = self.find_path(goal_node)

        path = [node.action for node in list(node_path)[1:]]
        path.reverse()

        return path

    def find_path(self, goal, start=None):
        """Find shortest path from goal to start"""
        if start is None:
            start = goal

        start.f_score = 0
        open_set = PriorityQueue(start, key=attrgetter("f_score"))

        is_complete = self.is_finished

        while open_set:
            current = open_set.pop()

            if is_complete(current, goal):
                return self.reconstruct_path(current, goal)

            current_parent = current.parent

            for neighbour in current.neighbours:
                if current_parent is neighbour:
                    continue

                tentative_g_score = current.g_score + neighbour.get_g_score_from(current)
                h_score = goal.get_h_score_from(neighbour)
                f_score = tentative_g_score + h_score

                if f_score >= neighbour.f_score:
                    continue

                neighbour.g_score = tentative_g_score
                neighbour.f_score = f_score
                neighbour.h_score = h_score

                open_set.add(neighbour)
                neighbour.parent = current
                print(neighbour)

        raise PathNotFoundException("Couldn't find path for given nodes")

    def get_neighbour_nodes_for_effects(self, effects):
        """Return new nodes for actions which produce the given effects

        :param effects: effects to request
        """
        effects_to_action_classes = self.effects_to_action_classes
        blackboard = self.blackboard

        neighbours = []
        for effect in effects:
            try:
                action_classes = effects_to_action_classes[effect]

            except KeyError:
                continue

            # Create new action instances for every node
            new_actions = [c() for c in action_classes]
            effect_neighbours = [ActionAStarNode(self, a) for a in new_actions
                                 if a.check_procedural_precondition(blackboard)]
            neighbours.extend(effect_neighbours)

        neighbours.sort(key=attrgetter("action.precedence"))
        return neighbours

    @staticmethod
    def get_action_classes_by_effects(action_classes):
        """Associate effects with appropriate actions

        :param action_classes: valid actions
        """
        mapping = {}

        for cls in action_classes:
            for effect in cls.effects:
                try:
                    effect_classes = mapping[effect]

                except KeyError:
                    effect_classes = mapping[effect] = []

                effect_classes.append(cls)

        return mapping

    def is_finished(self, node, goal):
        if not node.is_solution:
            return False

        ordered_path = self.reconstruct_path(node, goal)
        current_state = self.blackboard.copy()

        for node_ in ordered_path:
            current_state.update(node_.current_state)

        for key, goal_value in node.goal_state.items():
            current_value = current_state[key]
            if not current_value == goal_value:
                return False

        return True

    @staticmethod
    def reconstruct_path(node, goal):
        result = deque()
        while node:
            result.appendleft(node)
            node = node.parent

        return result


class GOAPPlannerFailedException(Exception):
    pass


class GOAPAIPlan:

    def __init__(self, actions):
        self._actions_it = iter(actions)
        self._actions = actions
        self.current_action = next(self._actions_it)
        print(self)

    def __repr__(self):
        return "[{}]".format(" -> ".join(["{}{}".format("*" if x is self.current_action else "", repr(x)) for x in self._actions]))

    def update(self, blackboard):
        state = self.current_action.evaluate(blackboard)

        if state == EvaluationState.success:
            try:
                self.current_action = next(self._actions_it)

            # Unless we're finished
            except StopIteration:
                return EvaluationState.success

            return self.update(blackboard)

        return state


class Scheduler:

    def arrange(self, path, goal_state):
        return path


class GOAPAIManager:

    def __init__(self, blackboard, goals, actions):
        self.actions = actions
        self.goals = sorted(goals, key=attrgetter("relevance"), reverse=True)
        self.blackboard = blackboard
        self.planner = Planner(self.actions, self.blackboard)
        self.scheduler = Scheduler()

        self._plan = None

    def find_best_plan(self):
        build_plan = self.planner.find_plan_for_goal
        arrange_plan = self.scheduler.arrange

        for goal in self.goals:
            try:
                path = build_plan(goal.state)

            except PathNotFoundException:
                continue

            ordered_path = arrange_plan(path, goal.state)
            return GOAPAIPlan(ordered_path)

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
            print(self._plan)
            plan_state = self._plan.update(blackboard)

            if plan_state == EvaluationState.failure:
                print("Plan failed: {}".format(self._plan.current_action))
                self._plan = None
                self.update()

            elif plan_state == EvaluationState.success:
                self._plan = None
                self.update()



