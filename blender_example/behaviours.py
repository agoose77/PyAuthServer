from bge_network import *
from mathutils import Vector
from random import random


class Navmesh:

    def find_path(self, source, destination):
        return [destination]


def follow_path_behaviour(parent=None):
    group = SequenceSelectorNode(
                                HasPawn(),
                                HasTarget(),
                                MoveToActorOrPoint()
                                 )

    if parent is not None:
        parent.add_child(group)
    return group


def idle_around_behaviour(parent=None):
    group = FindRandomPoint()

    if parent is not None:
        parent.add_child(group)
    return group


def follow_behaviour():
    behaviour = SequenceSelectorNode(
                                HasCamera(),
                                HasPawn(),
                                FindVisibleTarget(),
                                HasTarget(),
                                MoveToActorOrPoint(),
                                )
    behaviour.should_restart = True
    return behaviour

def idle_behaviour():
    return SequenceSelectorNode(idle_around_behaviour(),
                                follow_path_behaviour())


class FindRandomPoint(SignalActionNode):

    def evaluate(self):
        point = Vector(((random() - 0.5) * 100, (random() - 0.5) * 100, 1))
        SetMoveTarget.invoke(point, target=self.signaller.pawn)
        return EvaluationState.success


class SignalConditionDecorator(SequenceSelectorNode, SignalDecoratorNode):

    @property
    def condition(self):
        return True

    def evaluate(self):
        if self.condition:
            return super().evaluate()
        return EvaluationState.failure


class RunOnce(SignalConditionDecorator):

    def __init__(self, *children):
        super().__init__(*children)

        self.run = True

    @property
    def condition(self):
        return self.run

    def on_exit(self):
        self.run = False


class HasPawn(SignalConditionDecorator):

    @property
    def condition(self):
        return bool(self.signaller.pawn)


class HasCamera(SignalConditionDecorator):

    @property
    def condition(self):
        return bool(self.signaller.camera)


class FindVisibleTarget(SignalActionNode):

    def get_distance(self, actor):
        return (self.signaller.pawn.position - actor.position).length

    def on_enter(self):
        found_actors = []
        is_visible = self.signaller.camera.sees_actor

        for actor in WorldInfo.replicables:

            if not isinstance(actor, Pawn):
                continue

            if actor == self.signaller.pawn or actor == self.signaller.camera:
                continue

            if not is_visible(actor):
                continue

            found_actors.append(actor)

        if found_actors:
            self.actor = min(found_actors, key=self.get_distance)

        else:
            self.actor = None

    def evaluate(self):
        if self.actor is None:
            return EvaluationState.failure

        SetMoveTarget.invoke(self.actor, target=self.signaller.pawn)
        return EvaluationState.success


class HasTarget(SignalConditionDecorator):

    @property
    def condition(self):
        return self.signaller.pawn.target


class MoveToActorOrPoint(SignalActionNode):

    def __init__(self):
        super().__init__()

        self.navmesh = Navmesh()
        self.target = None
        self.path = None
        self.tolerance = 5

    def on_exit(self):
        self.signaller.pawn.velocity.y = 0
        self.signaller.pawn.target = None

        self.target = None
        self.path = None

    def on_enter(self):
        self.path = self.navmesh.find_path(self.signaller.pawn, self.signaller.pawn.target)
        self._target = self.signaller.pawn.target

    def evaluate(self):
        path = self.path
        pawn = self.signaller.pawn

        if path is None or pawn.target != self._target:
            return EvaluationState.failure

        target = path[0].position if hasattr(path[0], "position") else path[0]

        to_target = (target - pawn.position)

        if to_target.length < self.tolerance:
            path.pop()

        else:
            pawn.velocity.y = pawn.walk_speed 
            pawn.align_to(-Vector((0, 0, 1)).cross(to_target), 1, axis=Axis.x)

        if not path:
            return EvaluationState.success
