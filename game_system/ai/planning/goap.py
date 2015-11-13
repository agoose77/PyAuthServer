from operator import attrgetter
from sys import float_info
from logging import getLogger

from ...enums import AITaskState
from ...pathfinding import AStarAlgorithm, PathNotFoundException
from ...utilities import PriorityQueue

__all__ = "Goal", "Action", "GOAPPlanner", "GOAPActionPlanManager", "GOAPAStarActionNode", "GOAPAStarGoalNode", "Goal"


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

    def get_relevance(self, blackboard):
        return self.priority

    def is_satisfied(self, blackboard):
        for key, value in self.state.items():
            if blackboard[key] != value:
                return False

        return True


class Action:

    cost = 1
    precedence = 0

    effects = {}
    preconditions = {}

    def __repr__(self):
        return self.__class__.__name__

    def check_procedural_precondition(self, controller, world_state, is_planning=True):
        return True

    def is_interruptible(self, controller):
        return True     

    def get_status(self, controller):
        return AITaskState.success

    def apply_effects(self, destination_state, goal_state):
        """Apply action effects to state, resolving any variables

        :param destination_state: state to modify
        :param goal_state: source for variables
        """
        for key, value in self.effects.items():
            if isinstance(value, Variable):
                value = value.resolve(goal_state)

            destination_state[key] = value

    def on_enter(self, controller, goal_state):
        pass

    def on_exit(self, controller, goal_state):
        pass

    def validate_preconditions(self, current_state, goal_state):
        """Ensure that all preconditions are met in current state

        :param current_state: state to compare against
        :param goal_state: state to resolve variables
        """
        for key, value in self.preconditions.items():
            current_value = current_state[key]
            if isinstance(value, Variable):
                value = value.resolve(goal_state)

            if current_value != value:
                return False

        return True


class GOAPAStarNode:

    f_score = MAX_FLOAT

    def __init__(self, planner):
        self.current_state = {}
        self.goal_state = {}

        self.planner = planner

    @property
    def unsatisfied_keys(self):
        """Return the keys of the unsatisfied state symbols between the goal and current state"""
        current_state = self.current_state
        return [k for k, v in self.goal_state.items() if not current_state[k] == v]

    def satisfies_goal_state(self, state):
        """Determine if provided state satisfies required goal state

        :param state: state to test
        """
        goal_state = self.goal_state
        for key, current_value in state.items():
            if key not in goal_state:
                continue

            if current_value != goal_state[key]:
                return False

        return True


class GOAPAStarGoalNode(GOAPAStarNode):
    """A* Node associated with GOAP Goal"""

    def __repr__(self):
        return "<GOAPAStarGoalNode: {}>".format(self.goal_state)


@total_ordering
class GOAPAStarActionNode(GOAPAStarNode):
    """A* Node with associated GOAP action"""

    def __init__(self, planner, action):
        super().__init__(planner)

        self.action = action

    def __lt__(self, other):
        return self.action.precedence < other.action.precedence

    def __repr__(self):
        return "<GOAPAStarActionNode {}>".format(self.action)

    def update_internal_states(self):
        """Update internal current and goal states, according to action effects and preconditions

        Required for heuristic estimate
        """
        # Get state of preconditions
        action_preconditions = self.action.preconditions
        blackboard = self.planner.controller.blackboard
        goal_state = self.goal_state

        # 1 Update current state from effects, resolve variables
        for key, value in self.action.effects.items():

            if isinstance(value, Variable):
                value = value.resolve(self.goal_state)

            self.current_state[key] = value

        # 2 Update goal state from action preconditions, resolve variables
        for key, value in action_preconditions.items():

            if isinstance(value, Variable):
                value = value.resolve(self.goal_state)

            goal_state[key] = value

        # 3 Update current state with current values of missing precondition keys
        self.current_state.update({k: blackboard.get(k) for k in action_preconditions if k not in self.current_state})


class GOAPPlanner(AStarAlgorithm):

    def __init__(self, controller):
        self.controller = controller

        self.effects_to_actions = self.get_actions_by_effects(controller.actions)

    def find_plan_for_goal(self, goal_state):
        """Find shortest plan to produce goal state

        :param goal_state: state of goal
        """
        controller = self.controller
        blackboard = controller.blackboard

        goal_node = GOAPAStarGoalNode(self)

        goal_node.current_state = {k: blackboard.get(k) for k in goal_state}
        goal_node.goal_state = goal_state

        a_star_nodes = self.find_path(goal_node)
        a_star_parents = iter(a_star_nodes)
        next(a_star_parents)

        plan_steps = [(node.action, parent.goal_state) for node, parent in zip(a_star_nodes, a_star_parents)]

        return GOAPActionPlan(controller, plan_steps)

    def find_path(self, goal, start=None):
        """Find shortest path from goal to start

        :param goal: goal node
        :param start: start node (none)
        """
        if start is None:
            start = goal

        open_set = PriorityQueue()
        open_set.add(start, 0)

        is_complete = self.is_finished

        get_g_score = self.get_g_score
        get_h_score = self.get_h_score

        f_scores = {start: 0}
        g_scores = {start: 0}
        path = {}

        while open_set:
            current = open_set.pop()

            if is_complete(current, goal, path):
                return self.reconstruct_path(current, path, reverse_path=False)

            for neighbour in self.get_neighbours(current):
                tentative_g_score = g_scores[current] + get_g_score(current, neighbour)
                h_score = get_h_score(neighbour, goal)
                f_score = tentative_g_score + h_score

                if neighbour in f_scores and f_score >= f_scores[neighbour]:
                    continue

                g_scores[neighbour] = tentative_g_score
                f_scores[neighbour] = f_score

                open_set.add(neighbour, f_score)
                path[neighbour] = current

        raise PathNotFoundException("Couldn't find path for given nodes")

    def get_g_score(self, node, neighbour):
        """Determine procedural (or static) cost of this action

        :param node: node to move from (unused)
        """
        # Update world states
        neighbour.current_state.update(node.current_state)
        neighbour.goal_state.update(node.goal_state)

        return neighbour.action.cost

    def get_h_score(self, node, goal):
        node.update_internal_states()
        return len(node.unsatisfied_keys)

    def get_neighbours(self, node):
        """Return new nodes for given node which satisfy missing state

        :param node: node performing request
        """
        controller = self.controller
        effects_to_actions = self.effects_to_actions
        world_state = node.goal_state

        neighbours = []

        node_action = getattr(node, "action", None)
        for effect in node.unsatisfied_keys:
            try:
                actions = effects_to_actions[effect]

            except KeyError:
                continue

            # Create new node instances for every node
            effect_neighbours = [GOAPAStarActionNode(self, a) for a in actions
                                 # Ensure action can be included at this stage
                                 if a.check_procedural_precondition(controller, world_state, is_planning=True)
                                 # Ensure we don't get recursive neighbours!
                                 and a is not node_action]
            neighbours.extend(effect_neighbours)

        neighbours.sort(key=attrgetter("action.precedence"))

        return neighbours

    @staticmethod
    def get_actions_by_effects(actions):
        """Associate effects with appropriate actions

        :param actions: valid action instances
        """
        mapping = {}

        for action in actions:

            for effect in action.effects:
                try:
                    effect_classes = mapping[effect]

                except KeyError:
                    effect_classes = mapping[effect] = []

                effect_classes.append(action)

        return mapping

    def is_finished(self, node, goal, path):
        """Determine if the algorithm has completed

        :param node: current node
        :param goal: goal node
        """
        # Get world state
        controller = self.controller
        blackboard = controller.blackboard

        # Get world state values of node final state, goal
        world_state = {key: blackboard[key] for key in node.current_state}

        parent = None
        while node is not goal:
            action = node.action

            parent = path[node]
            parent_goal_state = parent.goal_state

            if not action.validate_preconditions(world_state, parent_goal_state):
                return False

            # May be able to remove this, should already be checked?
            if not action.check_procedural_precondition(controller, parent_goal_state):
                return False

            # Apply effects to world state
            action.apply_effects(world_state, parent_goal_state)
            node = parent

        if parent and parent.satisfies_goal_state(world_state):
            return True


class GOAPPlannerFailedException(Exception):
    pass


class GOAPActionPlan:
    """Manager of a series of Actions which fulfil a goal state"""

    def __init__(self, controller, plan_steps):
        self._plan_steps = plan_steps
        self._plan_steps_it = iter(plan_steps)

        self.controller = controller
        self.current_step = None

        self._invalidated = False

    def __repr__(self):
        action_names = []

        current_step = self.current_step
        for step in self._plan_steps:
            action, state = step
            name = repr(action)

            # Indicate current action with a * symbol
            if step is current_step:
                name = "*" + name

            action_names.append(name)

        return "[{}]".format(" -> ".join(action_names))

    def invalidate(self):
        if self._invalidated:
            return

        self._invalidated = True

        current_step = self.current_step
        if current_step is None:
            return

        # Exit plan
        action, goal_state = current_step
        action.on_exit(self.controller, goal_state)

    def update(self):
        """Update the plan, ensuring it is valid

        :param blackboard: blackboard object
        """
        # If plan invalidated, don't update
        if self._invalidated:
            return AITaskState.failure

        finished_state = AITaskState.success
        running_state = AITaskState.running

        # Get current step
        current_step = self.current_step
        controller = self.controller

        while True:
            # Before initialisation
            if current_step is not None:
                action, goal_state = current_step

                # Check if the plan is done?
                plan_state = action.get_status(controller)

                # If the plan isn't finished, return its state (failure / running)
                if plan_state == running_state:
                    return running_state

                # Leave previous steps
                action.on_exit(controller, goal_state)

                # Return if not finished
                if plan_state != finished_state:
                    return plan_state

            # Get next step
            try:
                current_step = self.current_step = next(self._plan_steps_it)

            except StopIteration:
                return AITaskState.success

            action, goal_state = current_step

            # Check preconditions
            if not action.check_procedural_precondition(controller, goal_state, is_planning=False):
                return AITaskState.failure

            # Enter step
            action.on_enter(controller, goal_state)

        return finished_state


class GOAPActionPlanManager:
    """Determine and update GOAP plans for AI"""

    def __init__(self, controller, logger=None):
        self.controller = controller
        self.planner = GOAPPlanner(controller)

        if logger is None:
            logger = getLogger("<GOAP>")

        self.logger = logger
        self._current_plan = None

    @property
    def current_plan(self):
        return self._current_plan

    @property
    def sorted_goals(self):
        """Return sorted list of goals, if relevant"""
        # Update goals with sorted list
        blackboard = self.controller.blackboard

        goal_pairs = []
        for goal in self.controller.goals:
            relevance = goal.get_relevance(blackboard)
            if relevance <= 0.0:
                continue

            goal_pairs.append((relevance, goal))

        goal_pairs.sort(reverse=True)

        return [g for r, g in goal_pairs]

    def find_best_plan(self):
        """Find best plan to satisfy most relevant, valid goal"""
        build_plan = self.planner.find_plan_for_goal
        blackboard = self.controller.blackboard

        # Try all goals to see if we can satisfy them
        for goal in self.sorted_goals:
            # Check the goal isn't satisfied already
            if goal.is_satisfied(blackboard):
                continue

            try:
                return build_plan(goal.state)

            except PathNotFoundException:
                continue

        raise GOAPPlannerFailedException("Couldn't find suitable plan")

    def update(self):
        """Update current plan, or find new plan"""
        # Rebuild plan
        if self._current_plan is None:
            try:
                self._current_plan = self.find_best_plan()

            except GOAPPlannerFailedException as err:
                self.logger.info(err)

        else:
            # Update plan naturally
            plan_state = self._current_plan.update()

            if plan_state == AITaskState.failure:
                self.logger.info("Plan failed during execution: {}".format(self._current_plan))
                self._current_plan = None
                self.update()

            elif plan_state == AITaskState.success:
                self.logger.info("Plan succeeded: {}".format(self._current_plan))
                self._current_plan = None
                self.update()
