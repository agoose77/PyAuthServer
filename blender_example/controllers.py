from network.decorators import requires_netmode, simulated
from network.descriptors import Attribute, TypeFlag, MarkAttribute
from network.enums import Netmodes, Roles
from network.replicable import Replicable
from network.structures import TypedList, TypedSet
from network.world_info import WorldInfo

from bge_network.actors import Actor
from bge_network.behaviour_tree import SequenceNode, SelectorNode
from bge_network.controllers import AIController, PlayerController
from bge_network.enums import CollisionType
from bge_network.replication_infos import ReplicationInfo, PlayerReplicationInfo
from bge_network.signals import *

from mathutils import Vector

from .actors import CTFFlag
from .controls import camera_control, inputs_control
from .behaviours import attack_behaviour, dying_behaviour, idle_behaviour
from .signals import *

__all__ = ["EnemyController", "CTFPlayerController"]


class EnemyController(AIController):

    def on_initialised(self):
        super().on_initialised()

        behaviour = SelectorNode(dying_behaviour(), attack_behaviour(), idle_behaviour())

        behaviour.should_restart = True
        self.behaviour.root = behaviour


CTFPlayerMovementStruct = PlayerController.create_movement_struct("forward", "backwards", "left", "right", "shoot",
                                                                  "run", "voice", "jump", "debug")
CTFPlayerMissingMoveStruct = PlayerController.create_missing_moves_struct(CTFPlayerMovementStruct, 20)


class CTFPlayerController(PlayerController):

    movement_struct = CTFPlayerMovementStruct
    missing_movement_struct = CTFPlayerMissingMoveStruct

    def clear_inventory(self):
        for item in self.inventory:
            item.unpossessed()

        self.inventory.clear()

    @CollisionSignal.listener
    def on_collision(self, collision_result):
        target = collision_result.hit_object

        # We need a valid collision
        if not (target and collision_result.collision_type == CollisionType.started):
            return

        # If we can pick it up
        if isinstance(target, CTFFlag) and target.owner is None:
            self.pickup_flag(target)

    def on_initialised(self):
        super().on_initialised()

        behaviour = SequenceNode(camera_control(), inputs_control())

        behaviour.should_restart = True
        self.behaviour.root.add_child(behaviour)

        self.inventory = []

    @PawnKilledSignal.listener
    def on_killed(self, attacker, target):
        self.clear_inventory()

    def on_unregistered(self):
        super().on_unregistered()

        self.clear_inventory()

    def on_notify(self, name):
        super().on_notify(name)

        if name == "weapon":
            UIWeaponChangedSignal.invoke(self.weapon)
            UIWeaponDataChangedSignal.invoke("ammo", self.weapon.ammo)
            #UIWeaponDataChangedSignal.invoke("clips", self.weapon.clips)

        elif name == "pawn":
            UIHealthChangedSignal.invoke(self.pawn.health)

    def pickup_flag(self, flag):
        # Replication specifics
        self.inventory.append(flag)
        self.pawn.attach_flag(flag)
        self.pawn.flag = flag

    @PlayerInputSignal.global_listener
    def player_update(self, delta_time):
        super().player_update(delta_time)

        # Only record when we need to
        if self.inputs.voice != self.microphone.active:
            self.microphone.active = self.inputs.voice

    def set_team(self, team: TypeFlag(Replicable)) -> Netmodes.server:
        TeamSelectionQuerySignal.invoke(self, team)

    @ActorDamagedSignal.listener
    def take_damage(self, damage, instigator, hit_position, momentum):
        if self.pawn.health == 0:
            PawnKilledSignal.invoke(instigator, target=self.pawn)

    def team_changed(self, team: TypeFlag(Replicable)) -> Netmodes.client:
        TeamSelectionUpdatedSignal.invoke()


