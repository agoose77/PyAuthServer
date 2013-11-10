from bge_network import *
from mathutils import Vector
from random import random
from functools import partial
from time import monotonic


class Navmesh:

    def find_path(self, source, destination):
        return [destination]


def walk_animation():
    group = SequenceNode(
                         IsWalking(),
                         WalkAnimation(),
                         )

    return group


def idle_behaviour():
    group = SequenceNode(
                         GetPawn(),
                         FindRandomPoint(),
                         HasPointTarget(),
                         MoveToPoint(),
                         ConsumePoint()
                         )

    return group


def attack_behaviour():
    can_hit_target = SelectorNode(
                                    WithinAttackRange(),
                                    MoveToActor(),
                                )
    can_hit_target.should_restart = True

    engage_target = SequenceNode(
                                 can_hit_target,
                                 SelectorNode(
                                              HasAmmo(),
                                              ReloadWeapon()
                                              ),
                                 AimAtActor(),
                                 CheckTimer(),
                                 FireWeapon(),
                                 SetTimer()
                                 )
    engage_target.should_restart = True

    group = SequenceNode(
                         GetPawn(),
                         GetCamera(),
                         GetWeapon(),
                         SelectorNode(
                                      HasActorTarget(),
                                      FindVisibleActor(),
                                      ),

                         FailedAsRunning(engage_target),
                         )
    group.should_restart = True
    return group


def climb_behaviour():

    root = SequenceNode(
                        GetPawn(),
                        FindObstacle(),
                        )
    return root


def fire_behind_shelter():
    return """SequenceNode(
                                IsInShelter(),
                                Stand(),
                                )"""


class StateModifier(SequenceNode, SignalInnerNode):

    def transform(self, old_state):
        return old_state

    def evaluate(self, blackboard):
        state = super().evaluate(blackboard)
        return self.transform(state)


class BlackboardModifier(SequenceNode, SignalInnerNode):

    def evaluate(self, blackboard):
        state = super().evaluate(blackboard.__class__())
        return self.transform(state)


class IntervalDecorator(SequenceNode, SignalInnerNode):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.last_time = 0.0

    @property
    def interval(self):
        return 0.0

    def evaluate(self, blackboard):
        if (monotonic() - self.last_time) > self.interval:
            self.last_time = monotonic()
            return super().evaluate(blackboard)

        return EvaluationState.failure


class ConditionSequence(SequenceNode, SignalInnerNode):

    @property
    def condition(self):
        return True

    def evaluate(self, blackboard):
        if self.condition:
            return super().evaluate(blackboard)
        return EvaluationState.failure


class ConditionNode(SignalLeafNode):

    def condition(self, blackboard):
        return True

    def evaluate(self, blackboard):
        return (EvaluationState.success if self.condition(blackboard)
                else EvaluationState.failure)


class GetObstacle(ConditionNode):

    def condition(self, blackboard):
        forwards = Vector((0, 1, 0))
        hit_obj, *_ = blackboard['pawn'].trace_ray(forwards)
        return bool(hit_obj)


class FindCeiling(SignalLeafNode):

    def evaluate(self, blackboard):
        climbable_height = 10
        upwards = Vector((0, 0, climbable_height))
        hit_obj, hit_pos, hit_normal = blackboard['pawn'].trace_ray(upwards)
        if not hit_obj:
            return EvaluationState.failure

        blackboard['ceiling'] = hit_pos


class IsWalking(ConditionNode):

    def condition(self, blackboard):
        pawn = blackboard['pawn']
        return abs(pawn.velocity.length - pawn.walk_speed) <= 0.1


class WalkAnimation(SignalLeafNode):

    def on_enter(self, blackboard):
        pawn = blackboard['pawn']
        pawn.play_animation("walk", 1, 49)

    def evaluate(self, blackboard):
        pawn = blackboard['pawn']

        if pawn.get_animation_frame() != 49:
            return EvaluationState.running
        else:
            return EvaluationState.success 


class HasAmmo(ConditionNode):

    def condition(self, blackboard):
        return blackboard['weapon'].ammo != 0


class CheckTimer(ConditionNode):

    def condition(self, blackboard):
        weapon = blackboard['weapon']
        return (WorldInfo.elapsed - weapon.last_fired_time
                ) >= weapon.shoot_interval


class SetTimer(SignalLeafNode):

    def evaluate(self, blackboard):
        blackboard['weapon'].last_fired_time = WorldInfo.elapsed
        return (EvaluationState.success)


class FailedAsRunning(StateModifier):

    def transform(self, old_state):
        if old_state == EvaluationState.failure:
            return EvaluationState.running
        return old_state


class AimAtActor(SignalLeafNode):

    def evaluate(self, blackboard):
        target = blackboard['actor']
        camera = blackboard['camera']
        pawn = blackboard['pawn']

        target_vector = (target.position -
                         camera.position).normalized()
        world_z = Vector((0, 0, 1))
        camera_vector = -world_z.copy()
        camera_vector.rotate(camera.rotation)
        turn_speed = 0.1

        camera.align_to(-target_vector, axis=Axis.z, time=turn_speed)
        camera.align_to(-world_z.cross(target_vector),
                             axis=Axis.x, time=turn_speed)
        pawn.align_to(world_z.cross(-target_vector), axis=Axis.x, time=turn_speed)
        return EvaluationState.success


class WithinAttackRange(ConditionNode):

    def condition(self, blackboard):
        return ((blackboard['actor'].position - blackboard['pawn'].position)
                .length <= blackboard['weapon'].maximum_range)


class CanFireWeapon(ConditionNode):

    def condition(self, blackboard):
        return blackboard['weapon'].can_fire


class ReloadWeapon(SignalLeafNode):

    def evaluate(self, blackboard):
        return EvaluationState.success


class FireWeapon(SignalLeafNode):

    def evaluate(self, blackboard):
        blackboard['controller'].start_server_fire()
        return EvaluationState.success


class FindRandomPoint(SignalLeafNode):

    def evaluate(self, blackboard):
        point = Vector(((random() - 0.5) * 100, (random() - 0.5) * 100, 1))
        blackboard['point'] = point
        return EvaluationState.success


class RunOnce(ConditionSequence):

    def __init__(self, *children):
        super().__init__(*children)

        self.run = True

    def condition(self, blackboard):
        return self.run

    def on_exit(self, blackboard):
        self.run = False


class GetPawn(SignalLeafNode):

    def evaluate(self, blackboard):
        if not blackboard['controller'].pawn:
            return EvaluationState.failure

        blackboard['pawn'] = blackboard['controller'].pawn
        return EvaluationState.success


class GetWeapon(SignalLeafNode):

    def evaluate(self, blackboard):
        if not blackboard['controller'].weapon:
            return EvaluationState.failure

        blackboard['weapon'] = blackboard['controller'].weapon
        return EvaluationState.success


class GetCamera(SignalLeafNode):

    def evaluate(self, blackboard):
        if not blackboard['controller'].camera:
            return EvaluationState.failure

        blackboard['camera'] = blackboard['controller'].camera
        return EvaluationState.success


class FindVisibleActor(SignalLeafNode):

    def get_distance(self, pawn, actor):
        return (pawn.position - actor.position).length

    def on_enter(self, blackboard):
        found_actors = []

        camera = blackboard['camera']
        pawn = blackboard['pawn']

        is_visible = camera.sees_actor

        for actor in WorldInfo.replicables:

            if not isinstance(actor, Pawn):
                continue

            if actor == pawn or actor == camera:
                continue

            if not is_visible(actor):
                continue

            found_actors.append(actor)

        if found_actors:
            self.actor = min(found_actors, key=partial(self.get_distance, pawn))

        else:
            self.actor = None

    def evaluate(self, blackboard):
        if self.actor is None:
            return EvaluationState.failure

        blackboard['actor'] = self.actor
        return EvaluationState.success


class HasActorTarget(ConditionNode):

    def condition(self, blackboard):
        return bool(blackboard.get("actor"))


class HasPointTarget(ConditionNode):

    def condition(self, blackboard):
        return "point" in blackboard


class ConsumePoint(SignalLeafNode):

    def evaluate(self, blackboard):
        try:
            blackboard.pop("point")
        except KeyError:
            return EvaluationState.failure
        return EvaluationState.success


class ConsumeActor(SignalLeafNode):

    def evaluate(self, blackboard):
        try:
            blackboard.pop("actor")
        except KeyError:
            return EvaluationState.failure
        return EvaluationState.success


class MoveToActor(SignalLeafNode):

    def __init__(self):
        super().__init__()

        self.navmesh = Navmesh()
        self.target = None
        self.path = None
        self.tolerance = 5

    def get_target(self, blackboard):
        return blackboard['actor']

    def get_target_position(self, target):
        return target.position

    def on_exit(self, blackboard):
        blackboard['pawn'].velocity.y = 0

        self.target = None
        self.path = None

    def on_enter(self, blackboard):
        self._pawn = blackboard['pawn']
        self._target = self.get_target(blackboard)

        self.path = self.navmesh.find_path(blackboard['pawn'],
                                           self._target)

    def evaluate(self, blackboard):
        path = self.path
        pawn = self._pawn

        if (not path or not self._pawn or
            self.get_target(blackboard) != self._target):
            return EvaluationState.failure

        to_target = (self.get_target_position(path[0]) - pawn.position)

        if to_target.length < self.tolerance:
            path.pop()

        else:
            pawn.velocity.y = pawn.walk_speed
            pawn.align_to(-Vector((0, 0, 1)).cross(to_target), 1, axis=Axis.x)

        if not path:
            return EvaluationState.success


class MoveToPoint(MoveToActor):

    def get_target(self, blackboard):
        return blackboard['point']

    def get_target_position(self, target):
        return target
