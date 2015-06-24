from game_system.ai.state_machine.fsm import FiniteStateMachine
from game_system.ai.state_machine.state import State
from game_system.entities import Actor, Pawn
from game_system.enums import Axis, CollisionState
from game_system.signals import LogicUpdateSignal, CollisionSignal

from network.descriptors import Attribute
from network.decorators import simulated
from network.enums import Roles


class TestActor(Actor):
    mass = Attribute(1.0, notify=True)
    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy))

    replicate_physics_to_owner = False

    @property
    def on_ground(self):
        downwards = -self.transform.get_direction_vector(Axis.z)
        target = self.transform.world_position + downwards
        trace = self.physics.ray_test(target, distance=1.3)
        return bool(trace)

    def create_object(self):
        from panda3d.core import Filename, NodePath, BitMask32
        from panda3d.bullet import BulletRigidBodyNode, BulletBoxShape

        from game_system.resources import ResourceManager
        f = Filename.fromOsSpecific(ResourceManager.get_absolute_path(ResourceManager["TestActor"]["Cube.egg"]))
        model = loader.loadModel(f)

        bullet_node = BulletRigidBodyNode("BulletPlane")
        bullet_nodepath = NodePath(bullet_node)

        shape = BulletBoxShape((1, 1, 1))
        bullet_node.addShape(shape)
        bullet_node.setMass(1.0)

        bullet_nodepath.set_collide_mask(BitMask32.bit(0))

        model.reparentTo(bullet_nodepath)
        return bullet_nodepath

    def on_initialised(self):
        super().on_initialised()

      #  self.transform.world_position = [0, 30, 2]

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        yield "mass"

    def on_notify(self, name):
        if name == "mass":
            self.physics.mass = self.mass
        else:
            super().on_notify(name)

    @simulated
    @CollisionSignal.on_context
    def on_collided(self, collision_result):
        pass

    @LogicUpdateSignal.on_global
    def on_update(self, delta_time):
        # new_pos = self.transform.world_position
        # new_pos.z -= 1 / 200
        # self.transform.world_position = new_pos
        return


class Plane(Actor):
    mass = Attribute(1.0, notify=True)
    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy))

    replicate_physics_to_owner = False

    def create_object(self):
        from panda3d.core import Filename, NodePath, BitMask32
        from panda3d.bullet import BulletRigidBodyNode, BulletPlaneShape

        from game_system.resources import ResourceManager
        f = Filename.fromOsSpecific(ResourceManager.get_absolute_path(ResourceManager["Plane"]["Plane.egg"]))
        model = loader.loadModel(f)

        bullet_node = BulletRigidBodyNode("BulletPlane")
        bullet_nodepath = NodePath(bullet_node)

        shape = BulletPlaneShape((0, 0, 1), 0)
        bullet_node.addShape(shape)
        bullet_node.setMass(1.0)

        bullet_nodepath.set_collide_mask(BitMask32.bit(0))
        model.reparentTo(bullet_nodepath)
        return bullet_nodepath

    def on_initialised(self):
        super().on_initialised()

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        yield "mass"

    def on_notify(self, name):
        if name == "mass":
            self.physics.mass = self.mass
        else:
            super().on_notify(name)

    @simulated
    @CollisionSignal.on_context
    def on_collided(self, collision_result):
        pass

    @LogicUpdateSignal.on_global
    def on_update(self, delta_time):

        # new_pos = self.transform.world_position
        # new_pos.z -= 1 / 200
        # self.transform.world_position = new_pos
        return


class Map(Actor):
    mass = Attribute(1.0, notify=True)
    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy))

    replicate_physics_to_owner = False

    def create_object(self):
        from panda3d.core import Filename, NodePath, BitMask32
        from panda3d.bullet import BulletRigidBodyNode, BulletTriangleMesh, BulletTriangleMeshShape

        from game_system.resources import ResourceManager
        f = Filename.fromOsSpecific(ResourceManager.get_absolute_path(ResourceManager["Map"]["map.egg"]))
        model = loader.loadModel(f)

        bullet_node = BulletRigidBodyNode("MapCollision")
        bullet_nodepath = NodePath(bullet_node)
        mesh = BulletTriangleMesh()

        for geomNP in model.findAllMatches('**/+GeomNode'):
            geomNode = geomNP.node()
            ts = geomNode.getTransform()
            for geom in geomNode.getGeoms():
                mesh.addGeom(geom, True, ts)

        shape = BulletTriangleMeshShape(mesh, dynamic=False)
        bullet_node.addShape(shape)
        bullet_nodepath.set_collide_mask(BitMask32.bit(0))
        model.reparentTo(bullet_nodepath)
        return bullet_nodepath

    def on_initialised(self):
        super().on_initialised()

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        yield "mass"

    def on_notify(self, name):
        if name == "mass":
            self.physics.mass = self.mass
        else:
            super().on_notify(name)

    @simulated
    @CollisionSignal.on_context
    def on_collided(self, collision_result):
        pass

    @LogicUpdateSignal.on_global
    def on_update(self, delta_time):

        # new_pos = self.transform.world_position
        # new_pos.z -= 1 / 200
        # self.transform.world_position = new_pos
        return


class AmmoPickup(Actor):
    mass = Attribute(1.0, notify=True)
    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy))

    replicate_physics_to_owner = False
    ammo = 5

    @property
    def on_ground(self):
        downwards = -self.transform.get_direction_vector(Axis.z)
        target = self.transform.world_position + downwards
        trace = self.physics.ray_test(target, distance=1.3)
        return bool(trace)

    def create_object(self):
        from panda3d.core import Filename, NodePath, BitMask32
        from panda3d.bullet import BulletRigidBodyNode, BulletBoxShape

        from game_system.resources import ResourceManager
        f = Filename.fromOsSpecific(ResourceManager.get_absolute_path(ResourceManager["AmmoPickup"]["Cube.egg"]))
        model = loader.loadModel(f)

        bullet_node = BulletRigidBodyNode("AmmoPickup")
        bullet_nodepath = NodePath(bullet_node)

        shape = BulletBoxShape((1, 1, 1))
        bullet_node.addShape(shape)
        bullet_node.setMass(1.0)

        bullet_nodepath.set_collide_mask(BitMask32.bit(0))
        model.reparentTo(bullet_nodepath)
        return bullet_nodepath

    def on_initialised(self):
        super().on_initialised()

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        yield "mass"

    def on_notify(self, name):
        if name == "mass":
            self.physics.mass = self.mass

        else:
            super().on_notify(name)

    @simulated
    @CollisionSignal.on_context
    def on_collided(self, collision_result):
        pass

    @LogicUpdateSignal.on_global
    def on_update(self, delta_time):
        # new_pos = self.transform.world_position
        # new_pos.z -= 1 / 200
        # self.transform.world_position = new_pos
        return


class Zombie(Pawn):

    @simulated
    def create_object(self):
        from panda3d.core import Filename, NodePath, BitMask32
        from direct.actor.Actor import Actor
        from panda3d.bullet import BulletRigidBodyNode, BulletBoxShape

        from game_system.resources import ResourceManager
        f = Filename.fromOsSpecific(ResourceManager.get_absolute_path(ResourceManager["Zombie"]["Zombie.egg"]))
        model = Actor(f)

        bullet_node = BulletRigidBodyNode("BulletPlane")
        bullet_nodepath = NodePath(bullet_node)

        shape = BulletBoxShape((1, 1, 1))
        bullet_node.addShape(shape)
        bullet_node.setMass(1.0)

        model.reparentTo(bullet_nodepath)
        #model.set_scale(0.12)
        model.set_pos(0, 0, -1)

        bullet_nodepath.set_python_tag("actor", model)
        bullet_nodepath.set_collide_mask(BitMask32.bit(0))

        return bullet_nodepath

    def on_initialised(self):
        super().on_initialised()

        self.animation_fsm = FiniteStateMachine()
        self.animation_fsm.add_state(IdleState(self))
        self.animation_fsm.add_state(WalkState(self, "walk_limp"))

        self.walk_speed = 2

    @LogicUpdateSignal.on_global
    def on_update(self, dt):
        if self.physics.world_velocity.xy.length > 0.1:
            self.animation_fsm.state = self.animation_fsm.states["Walk"]

        else:
            self.animation_fsm.state = self.animation_fsm.states["Idle"]

        self.animation_fsm.state.update(dt)


class WalkState(State):

    def __init__(self, pawn, animation_name):
        super().__init__("Walk")

        self.pawn = pawn
        self.animation_name = animation_name

        self._animation_handle = None

    def on_enter(self):
        self._animation_handle = self.pawn.animation.play(self.animation_name, loop=True)

    def on_exit(self):
        self._animation_handle.stop()

    def update(self, dt):
        pass


class IdleState(State):

    def __init__(self, pawn):
        super().__init__("Idle")

        self.pawn = pawn

    def update(self, dt):
        pass


class TestAI(Pawn):

    def create_object(self):
        from panda3d.core import Filename, NodePath, BitMask32
        from direct.actor.Actor import Actor
        from panda3d.bullet import BulletRigidBodyNode, BulletCapsuleShape

        from game_system.resources import ResourceManager
        f = Filename.fromOsSpecific(ResourceManager.get_absolute_path(ResourceManager["TestAI"]["lp_char_bs.egg"]))
        model = Actor(f)

        bullet_node = BulletRigidBodyNode("TestAIBulletNode")
        bullet_nodepath = NodePath(bullet_node)

        bullet_node.set_angular_factor((0, 0, 1))

        shape = BulletCapsuleShape(0.3, 1.4, 2)
        bullet_node.addShape(shape)
        bullet_node.setMass(1.0)

        model.reparentTo(bullet_nodepath)
        model.set_hpr(180, 0, 0)
        model.set_pos(0, 0, -1)

        bullet_nodepath.set_collide_mask(BitMask32.bit(0))
        bullet_nodepath.set_python_tag("actor", model)

        return bullet_nodepath

    def on_initialised(self):
        super().on_initialised()

        self.animation_fsm = FiniteStateMachine()
        self.animation_fsm.add_state(IdleState(self))
        self.animation_fsm.add_state(WalkState(self, "walk_patrol"))

        self.walk_speed = 2

    @simulated
    @LogicUpdateSignal.on_global
    def on_update(self, dt):
        if self.physics.world_velocity.xy.length > 0.1:
            self.animation_fsm.state = self.animation_fsm.states["Walk"]

        else:
            self.animation_fsm.state = self.animation_fsm.states["Idle"]

        self.animation_fsm.state.update(dt)


from game_system.entities import Navmesh


class TestNavmesh(Navmesh):
    pass
