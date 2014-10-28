from network.world_info import WorldInfo

from .behaviour import LeafNode, EvaluationState
from ..controllers import AIController, PlayerController


class GetNearestPlayerPawn(LeafNode):

    def evaluate(self, blackboard):
        try:
            pawn = blackboard["pawn"]
        except KeyError:
            return EvaluationState.failed

        origin = pawn.transform.world_position
        distance_to = lambda p: (p.pawn.transform.world_position - origin).length_squared

        controller = min([p for p in WorldInfo.subclass_of(PlayerController) if p.pawn], key=distance_to)
        blackboard['nearest_pawn'] = controller

        return EvaluationState.success


class GetNearestAIPawn(LeafNode):

    def evaluate(self, blackboard):
        try:
            pawn = blackboard["pawn"]
        except KeyError:
            return EvaluationState.failed

        origin = pawn.transform.world_position
        distance_to = lambda p: (p.pawn.transform.world_position - origin).length_squared

        controller = min([p for p in WorldInfo.subclass_of(AIController) if p.pawn], key=distance_to)
        blackboard['nearest_pawn'] = controller

        return EvaluationState.success


class TargetNearestPawn(LeafNode):

    def evaluate(self, blackboard):
        try:
            blackboard['target'] = blackboard['nearest_pawn']
        except KeyError:
            return EvaluationState.failed

        return EvaluationState.success


class MoveToTarget(LeafNode):

    def __init__(self):
        self._path = None

    def evaluate(self, blackboard):
