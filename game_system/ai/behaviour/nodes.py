from collections import deque

from network.world_info import WorldInfo

from .behaviour import Node, EvaluationState
from ...controllers import AIPawnController, PlayerPawnController
from ...coordinates import Vector


class GetNearestPlayerPawn(Node):
    """Find the nearest Player pawn to the current pawn"""

    def evaluate(self, blackboard):
        try:
            pawn = blackboard["pawn"]

        except KeyError:
            return EvaluationState.failed

        origin = pawn.transform.world_position
        distance_to = lambda p: (p.pawn.transform.world_position - origin).length_squared

        controller = min([p for p in Replicable.subclass_of_type(PlayerPawnController) if p.pawn], key=distance_to)
        blackboard['nearest_pawn'] = controller

        return EvaluationState.success


class GetNearestAIPawn(Node):
    """Find the nearest AI pawn to the current pawn"""

    def evaluate(self, blackboard):
        try:
            pawn = blackboard["pawn"]

        except KeyError:
            return EvaluationState.failed

        origin = pawn.transform.world_position
        distance_to = lambda p: (p.pawn.transform.world_position - origin).length_squared

        controller = min([p for p in Replicable.subclass_of_type(AIPawnController) if p.pawn], key=distance_to)
        blackboard['nearest_pawn'] = controller

        return EvaluationState.success


class TargetNearestPawn(Node):
    """Establish nearest pawn as a target"""

    def evaluate(self, blackboard):
        try:
            blackboard['target'] = blackboard['nearest_pawn']

        except KeyError:
            return EvaluationState.failed

        return EvaluationState.success


class MoveToTarget(Node):
    """Move the current pawn to a target, following navigation mesh path"""

    def __init__(self, movement_speed):
        self._low_resolution_path = None
        self._high_resolution_path = None
        self._path = deque()

        self.threshold = 1.0
        self.movement_speed = movement_speed

    def evaluate(self, blackboard):
        try:
            pawn = blackboard["pawn"]
            target = blackboard["target"]

        except KeyError:
            return EvaluationState.failed

        goal = target.world_position

        low_resolution = self._low_resolution_path

        navmesh = pawn.navmesh

        find_node = navmesh.find_node
        find_low_res_path = navmesh.find_low_resolution_path
        find_high_res_path = navmesh.find_high_resolution_path

        goal_node = find_node(goal)

        # If we have no path, or the goal changed
        path_changed = low_resolution is None or (goal_node != low_resolution[-1])

        if path_changed:
            start = pawn.transform.world_position
            start_node = find_node(start)

            low_resolution = find_low_res_path(start_node, goal_node)
            high_resolution = find_high_res_path(start, goal, low_resolution)

            self._low_resolution_path = low_resolution
            self._high_resolution_path = high_resolution

            self._path = deque(high_resolution)

        # Invoke movement code
        path = self._path
        self.follow_path(pawn, path, goal)

        # Determine whether we finished
        if path:
            return EvaluationState.running

        else:
            return EvaluationState.success

    def follow_path(self, pawn, path, goal):
        """Follow path as a sequence of points to traverse

        :param pawn: pawn to move
        :param path: path to follow
        :param goal: final point in path
        """

        start = pawn.transform.world_position

        to_first_entry = path[0] - start

        if to_first_entry.length_squared < self.threshold:
            path.popleft()

            if path:
                self.follow_path(start, path, goal)

            return

        pawn.transform.align_to(to_first_entry)
        pawn.physics.local_velocity.xy = Vector((0.0, self.movement_speed, 0.0)).xy