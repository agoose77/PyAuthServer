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

    def resolve(self, source):
        """Determine true value of variable

        :param source: variable dictionary
        """
        return source[self._key]


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

    def check_procedural_precondition(self, blackboard, world_state, is_planning=True):
        return True

    def get_cost(self):
        return self.cost

    def evaluate(self, blackboard, world_state):
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
    def unsatisfied_state(self):
        """Return the keys of the unsatisfied state symbols between the goal and current state"""
        current_state = self.current_state
        return [k for k, v in self.goal_state.items() if not current_state[k] == v]

    @property
    def neighbours(self):
        """Find neighbours of node, which fulfil unsatisfied state

        :param node: node to evaluate
        """
        return self.planner.get_neighbour_nodes_for(self)

    def validate_preconditions(self, current_state, goal_state):
        for key, value in self.action.preconditions.items():
            current_value = current_state[key]
            if isinstance(value, Variable):
                value = value.resolve(goal_state)

            if current_value != value:
                return False

        return True

    def copy_state(self, source, destination, resolve_source):
        """Copy state from one state to another, resolving any variables

        :param source: source of state
        :param destination: state to modify
        :param resolve_source: source for variables
        """
        for key, value in source.items():
            if isinstance(value, Variable):
                value = value.resolve(resolve_source)

            destination[key] = value

    def satisfies_goal_state(self, current_state):
        goal_state = self.goal_state
        for key, current_value in current_state.items():
            if key not in goal_state:
                continue

            if current_value != goal_state[key]:
                return False

        return True


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

        return self.action.get_cost()

    def update_internal_states(self):
        """Update internal current and goal states, according to action effects and preconditions

        Required for heuristic estimate
        """
        # Get state of preconditions
        action_preconditions = self.action.preconditions
        blackboard = self.planner.blackboard
        goal_state = self.goal_state

        # 1 Update current state from effects, resolve variables
        #self.copy_state(self.action.effects, self.current_state, resolve_source=goal_state)
        for key in self.action.effects:
            try:
                value = self.goal_state[key]
            except KeyError:
                continue

            if isinstance(value, Variable):
                value = value.resolve(self.goal_state)

            self.current_state[key] = value

        # 2 Update goal state from action preconditions, resolve variables
        self.copy_state(action_preconditions, goal_state, resolve_source=goal_state)

        # 3 Update current state with current values of missing precondition keys
        self.current_state.update({k: blackboard.get(k) for k in action_preconditions if k not in self.current_state})


def f(d):
    return "[{}]".format(", ".join("{}={}".format(k, v) for k, v in d.items()))


class Planner(AStarAlgorithm):

    def __init__(self, action_classes, blackboard):
        self.action_classes = action_classes
        self.blackboard = blackboard

        self.effects_to_actions = self.get_actions_by_effects(action_classes)

    def find_plan_for_goal(self, goal_state):
        """Find shortest plan to produce goal state

        :param goal_state: state of goal
        """
        blackboard = self.blackboard

        goal_node = GOAPGoalNode(self)

        goal_node.current_state = {k: blackboard.get(k) for k in goal_state}
        goal_node.goal_state = goal_state

        node_path = self.find_path(goal_node)

        plan_steps = [GOAPAIPlanStep(node.action, node.parent.goal_state) for node in list(node_path)[1:]]
        plan_steps.reverse()

        return GOAPAIPlan(plan_steps)

    def find_path(self, goal, start=None):
        """Find shortest path from goal to start"""
        if start is None:
            start = goal

        start.f_score = 0
        open_set = PriorityQueue(start, key=attrgetter("f_score"))

        is_finished = self.is_finished
        from time import monotonic
        s=monotonic()
        while open_set:
            current = open_set.pop()
            if (monotonic() - s) > 0.4:
                import bge
                bge.logic.endGame()
                print("BREAK")
                break

            if is_finished(current, goal):
                return self.reconstruct_path(current, goal)

            current_parent = current.parent

            for neighbour in current.neighbours:
                if current_parent is neighbour:
                    continue

                tentative_g_score = current.g_score + neighbour.get_g_score_from(current)
                h_score = goal.get_h_score_from(neighbour)
                f_score = tentative_g_score + h_score

                if f_score >= (neighbour.f_score * 0.9999):
                    continue
                print(neighbour,current)
                neighbour.g_score = tentative_g_score
                neighbour.f_score = f_score
                neighbour.h_score = h_score

                open_set.add(neighbour)
                neighbour.parent = current

        raise PathNotFoundException("Couldn't find path for given nodes")

    def get_neighbour_nodes_for(self, node):
        """Return new nodes for given node which satisfy missing state

        :param node: node performing request
        """
        effects_to_actions = self.effects_to_actions
        blackboard = self.blackboard
        world_state = node.goal_state

        neighbours = []

        for effect in node.unsatisfied_state:
            try:
                actions = effects_to_actions[effect]

            except KeyError:
                continue

            # Create new node instances for every node
            effect_neighbours = [ActionAStarNode(self, a) for a in actions
                                 if a.check_procedural_precondition(blackboard, world_state, is_planning=True)]
            neighbours.extend(effect_neighbours)

        neighbours.sort(key=attrgetter("action.precedence"))
        return neighbours

    @staticmethod
    def get_actions_by_effects(action_classes):
        """Associate effects with appropriate actions

        :param action_classes: valid action classes
        """
        mapping = {}

        for cls in action_classes:
            action = cls()

            for effect in action.effects:
                try:
                    effect_classes = mapping[effect]

                except KeyError:
                    effect_classes = mapping[effect] = []

                effect_classes.append(action)

        return mapping

    def is_finished(self, node, goal):
        # Get world state
        world_state = {key: self.blackboard[key] for key in node.current_state}

        parent = None

        while node is not goal:
            action = node.action
            parent = node.parent
            parent_goal_state = parent.goal_state
           # print(node)
            if not node.validate_preconditions(world_state, parent_goal_state):
                return False

            # May be able to remove this, should already be checked?
            if not action.check_procedural_precondition(self.blackboard, parent_goal_state):
                return False

            # Apply effects to world state
            node.copy_state(action.effects, world_state, resolve_source=parent_goal_state)
            node = parent

        if parent and parent.satisfies_goal_state(world_state):
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


class GOAPAIPlanStep:

    def __init__(self, action, state):
        self.action = action
        self.state = state

    def evaluate(self, blackboard):
        return self.action.evaluate(blackboard, self.state)

    def __repr__(self):
        return repr(self.action)


class GOAPAIPlan:

    def __init__(self, plan_steps):
        self._plan_steps_it = iter(plan_steps)
        self._plan_steps = plan_steps
        self.current_plan_step = next(self._plan_steps_it)
        print(self)

    def __repr__(self):
        return "[{}]".format(" -> ".join(["{}{}".format("*" if x is self.current_plan_step else "", repr(x)) for x in self._plan_steps]))

    def update(self, blackboard):
        state = self.current_plan_step.evaluate(blackboard)

        if state == EvaluationState.success:
            try:
                self.current_plan_step = next(self._plan_steps_it)

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

        for goal in self.goals:
            try:
                return build_plan(goal.state)

            except PathNotFoundException:
                continue

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



