from bge_network import *
from mathutils import Vector
from random import random
from time import monotonic


class Navmesh:

    def find_path(self, source, destination):
        return [destination]


def idle_behaviour():
    group = SequenceSelectorNode(
                                HasPawn(),
                                FindRandomPoint(),
                                PrioritySelectorNode(
                                                     HasPointTarget(),
                                                     HasActorTarget()
                                                     ),
                                MoveToActorOrPoint()
                                 )

    return group


def attack_behaviour():
    move_or_attack = PrioritySelectorNode(
                                    WithinAttackRange(),
                                    MoveToActorOrPoint(),
                                )
    move_or_attack.should_restart = True

    group = SequenceSelectorNode(
                HasPawn(),
                HasCamera(),
                HasWeapon(),
                PrioritySelectorNode(
                                     HasActorTarget(),
                                     FindVisibleTarget(),
                                     ),
                SequenceSelectorNode(
                                     move_or_attack,
                                     FailedAsRunning(
                                                    AimAtActor(),
                                                     CanFireWeapon(),
                                                     FireWeapon(),
                                                     )
                                     )
                                 )

    group.should_restart = True
    return group


class StateModifier(SequenceSelectorNode, SignalDecoratorNode):

    def transform(self, old_state):
        return old_state

    def evaluate(self):
        state = super().evaluate()
        return self.transform(state)


class FailedAsRunning(StateModifier):

    def transform(self, old_state):
        if old_state == EvaluationState.failure:
            return EvaluationState.running
        return old_state


class LatchAsRunning(SignalDecoratorNode):

    def on_enter(self):
        self.entered = monotonic()
        self._state = EvaluationState.success

    @property
    def interval(self):
        return 1

    def evaluate(self):
        time = monotonic()

        if (time - self.entered) <= self.interval:
            self._state = super().evaluate()
            return EvaluationState.running

        return self._state


class AimAtActor(SignalActionNode):

    def evaluate(self):
        target = self.signaller.pawn.target
        camera = self.signaller.camera

        target_vector = (target.position -
                         camera.position).normalized()

        world_z = Vector((0, 0, 1))
        camera_vector = -world_z.copy()
        camera_vector.rotate(camera.rotation)
        turn_speed = 0.1

        camera.align_to(-target_vector, axis=Axis.z, time=turn_speed)
        camera.align_to(-world_z.cross(target_vector),
                             axis=Axis.x, time=turn_speed)
        self.signaller.pawn.align_to(world_z.cross(-target_vector), axis=Axis.x, time=turn_speed)
        return EvaluationState.success


class SignalConditionDecorator(SequenceSelectorNode, SignalDecoratorNode):

    @property
    def condition(self):
        return True

    def evaluate(self):
        if self.condition:
            return super().evaluate()
        return EvaluationState.failure


class WithinAttackRange(SignalConditionDecorator):

    @property
    def condition(self):
        return self.signaller.within_attack_range(self.signaller.pawn.target)


class IntervalDecorator(SequenceSelectorNode, SignalDecoratorNode):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.last_time = 0.0

    @property
    def interval(self):
        return 0.0

    def evaluate(self):
        if (monotonic() - self.last_time) > self.interval:
            self.last_time = monotonic()
            return super().evaluate()

        return EvaluationState.failure


class CanFireWeapon(SignalConditionDecorator):

    @property
    def condition(self):
        return self.signaller.weapon.can_fire


class FireWeapon(SignalActionNode):

    def evaluate(self):
        self.signaller.start_server_fire()
        return EvaluationState.success


class FindRandomPoint(SignalActionNode):

    def evaluate(self):
        point = Vector(((random() - 0.5) * 100, (random() - 0.5) * 100, 1))
        SetMoveTarget.invoke(point, target=self.signaller.pawn)
        return EvaluationState.success


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


class HasWeapon(SignalConditionDecorator):

    @property
    def condition(self):
        return bool(self.signaller.weapon)


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


class HasActorTarget(SignalConditionDecorator):

    @property
    def condition(self):
        return self.signaller.pawn.target and isinstance(self.signaller.pawn.target, Actor)


class HasPointTarget(SignalConditionDecorator):

    @property
    def condition(self):
        return isinstance(self.signaller.pawn.target, Vector)


class UnsetActorOrPoint(SignalActionNode):

    def evaluate(self):
        self.signaller.pawn.target = None
        return EvaluationState.success


class MoveToActorOrPoint(SignalActionNode):

    def __init__(self):
        super().__init__()

        self.navmesh = Navmesh()
        self.target = None
        self.path = None
        self.tolerance = 5

    def on_exit(self):
        self.signaller.pawn.velocity.y = 0

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
