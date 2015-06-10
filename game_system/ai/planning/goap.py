from operator import attrgetter
from sys import float_info

from game_system.enums import EvaluationState
from game_system.pathfinding.algorithm import AStarAlgorithm, PathNotFoundException, AStarNode, AStarGoalNode
from game_system.pathfinding.priority_queue import PriorityQueue


__all__ = "Goal", "Action", "Planner", "GOAPAIPlanManager", "GOAPAStarActionNode", "GOAPAStarGoalNode", "Goal"


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

    def check_procedural_precondition(self, blackboard, world_state, is_planning=True):
        return True

    def get_status(self, blackboard):
        return EvaluationState.success

    def get_cost(self):
        return self.cost

    def apply_effects(self, destination_state, goal_state):
        """Apply action effects to state, resolving any variables

        :param destination_state: state to modify
        :param goal_state: source for variables
        """
        for key, value in self.effects.items():
            if isinstance(value, Variable):
                value = value.resolve(goal_state)

            destination_state[key] = value

    def on_enter(self, blackboard, goal_state):
        pass

    def on_exit(self, blackboard, goal_state):
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


class IGOAPAStarNode:

    f_score = MAX_FLOAT

    def __init__(self, planner):
        self.current_state = {}
        self.goal_state = {}

        self.planner = planner

    @property
    def neighbours(self):
        """Find neighbours of node, which fulfil unsatisfied state

        :param node: node to evaluate
        """
        return self.planner.get_neighbour_nodes_for(self)

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


class GOAPAStarGoalNode(IGOAPAStarNode, AStarGoalNode):
    """GOAP A* Goal Node"""

    def __repr__(self):
        return "<GOAPAStarGoalNode: {}>".format(self.goal_state)

    def get_h_score_from(self, node):
        """Rough estimate of cost of node, based upon satisfaction of goal state

        :param node: node to evaluate heuristic
        """
        node.update_internal_states()
        return len(node.unsatisfied_keys)


@total_ordering
class GOAPAStarActionNode(IGOAPAStarNode, AStarNode):
    """A* Node with associated GOAP action"""

    def __init__(self, planner, action):
        super().__init__(planner)

        self.action = action

    def __lt__(self, other):
        return self.action.precedence < other.action.precedence

    def __repr__(self):
        return "<GOAPAStarActionNode {}>".format(self.action)

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
        for key in self.action.effects:
            try:
                value = self.goal_state[key]
            except KeyError:
                continue

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

        goal_node = GOAPAStarGoalNode(self)

        goal_node.current_state = {k: blackboard.get(k) for k in goal_state}
        goal_node.goal_state = goal_state

        node_path = list(self.find_path(goal_node))[1:]

        plan_steps = []
        for node in node_path:
            plan_step = GOAPAIPlanStep(node.action, node.parent.goal_state)
            plan_steps.append(plan_step)

        plan_steps.reverse()

        return GOAPAIPlan(plan_steps)

    def find_path(self, goal, start=None):
        """Find shortest path from goal to start

        :param goal: goal node
        :param start: start node (none)
        """
        if start is None:
            start = goal

        start.f_score = 0
        open_set = PriorityQueue(start, key=attrgetter("f_score"))

        is_finished = self.is_finished

        while open_set:
            current = open_set.pop()

            if is_finished(current, goal):
                return self.reconstruct_path(current, goal)

            current_parent = current.parent

            for neighbour in current.neighbours:
                if current_parent is neighbour:
                    continue

                tentative_g_score = current.g_score + neighbour.get_g_score_from(current)
                h_score = goal.get_h_score_from(neighbour)
                f_score = tentative_g_score + h_score

                if f_score >= neighbour.f_score * 0.99:
                    continue

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

        node_action = getattr(node, "action", None)
        for effect in node.unsatisfied_keys:
            try:
                actions = effects_to_actions[effect]

            except KeyError:
                continue

            # Create new node instances for every node
            effect_neighbours = [GOAPAStarActionNode(self, a) for a in actions
                                 # Ensure action can be included at this stage
                                 if a.check_procedural_precondition(blackboard, world_state, is_planning=True)
                                 # Ensure we don't get recursive neighbours!
                                 and a is not node_action]
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
        """Determine if the algorithm has completed

        :param node: current node
        :param goal: goal node
        """
        # Get world state
        world_state = {key: self.blackboard[key] for key in node.current_state}

        parent = None

        while node is not goal:
            action = node.action
            parent = node.parent
            parent_goal_state = parent.goal_state

            if not action.validate_preconditions(world_state, parent_goal_state):
                return False

            # May be able to remove this, should already be checked?
            if not action.check_procedural_precondition(self.blackboard, parent_goal_state):
                return False

            # Apply effects to world state
            action.apply_effects(world_state, parent_goal_state)
            node = parent

        if parent and parent.satisfies_goal_state(world_state):
            return True

    @staticmethod
    def reconstruct_path(node, goal):
        """Reconstruct path from parent tree

        :param node: final node
        :param goal: goal node
        """
        result = []
        while node:
            result.append(node)
            node = node.parent

        result.reverse()
        return result


class GOAPPlannerFailedException(Exception):
    pass


class GOAPAIPlanStep:
    """Container object for bound action and its goal state"""

    def __init__(self, action, state):
        self.action = action
        self.state = state

    def __repr__(self):
        return repr(self.action)


class GOAPAIPlan:
    """Manager of a series of Actions which fulfil a goal state"""

    def __init__(self, plan_steps):
        self._plan_steps_it = iter(plan_steps)
        self._plan_steps = plan_steps
        self.current_plan_step = None

    def __repr__(self):
        return "[{}]".format(" -> ".join(["{}{}".format("*" if x is self.current_plan_step else "", repr(x)) for x in self._plan_steps]))

    def update(self, blackboard):
        """Update the plan, ensuring it is valid

        :param blackboard: blackboard object
        """
        finished_state = EvaluationState.success
        running_state = EvaluationState.running

        current_step = self.current_plan_step

        while True:
            # Before initialisation
            if current_step is not None:
                action = current_step.action
                state = current_step.state

                plan_state = action.get_status(blackboard)

                # If the plan isn't finished, return its state (failure / running)
                if plan_state == running_state:
                    return running_state

                # Leave previous step
                action.on_exit(blackboard, state)

                # Return if not finished
                if plan_state != finished_state:
                    return plan_state

            # Get next step
            try:
                current_step = self.current_plan_step = next(self._plan_steps_it)

            except StopIteration:
                return EvaluationState.success

            action = current_step.action
            state = current_step.state

            # Check preconditions
            if not action.check_procedural_precondition(blackboard, state, is_planning=False):
                return EvaluationState.failure

            # Enter step
            action.on_enter(blackboard, state)

        return finished_state


class GOAPAIPlanManager:
    """Determine and update GOAP plans for AI"""

    def __init__(self, blackboard, goals, actions):
        self.actions = actions

        self.blackboard = blackboard
        self.planner = Planner(self.actions, self.blackboard)

        self.goals = goals

        self._plan = None

    @property
    def sorted_goals(self):
        """Return sorted list of goals, if relevant"""
        # Update goals with sorted list
        blackboard = self.blackboard

        goal_pairs = []
        for goal in self.goals:
            relevance = goal.get_relevance(blackboard)
            if relevance <= 0.0:
                continue

            goal_pairs.append((relevance, goal))

        goal_pairs.sort()

        return [g for r, g in goal_pairs]

    def find_best_plan(self):
        """Find best plan to satisfy most relevant, valid goal"""
        build_plan = self.planner.find_plan_for_goal

        # Try all goals to see if we can satisfy them
        for goal in self.sorted_goals:
            # Check the goal isn't satisfied already
            if goal.is_satisfied(self.blackboard):
                continue

            try:
                return build_plan(goal.state)

            except PathNotFoundException:
                continue

        raise GOAPPlannerFailedException("Couldn't find suitable plan")

    def update(self):
        """Update current plan, or find new plan"""
        blackboard = self.blackboard

        # Rebuild plan
        if self._plan is None:
            try:
                self._plan = self.find_best_plan()
                print(self._plan)

            except GOAPPlannerFailedException as err:
                print(err)

        else:
            plan_state = self._plan.update(blackboard)

            if plan_state == EvaluationState.failure:
                print("Plan failed during exection of {}".format(self._plan.current_plan_step))
                self._plan = None
                self.update()

            elif plan_state == EvaluationState.success:
                self._plan = None
                self.update()



