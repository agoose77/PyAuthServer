from game_system.entities import Actor
from game_system.enums import CollisionState
from game_system.signals import LogicUpdateSignal, CollisionSignal

from network.descriptors import Attribute
from network.decorators import simulated
from network.enums import Roles


class TestActor(Actor):
    mass = Attribute(1.0, notify=True)
    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy))

    replicate_physics_to_owner = False

    def create_object(self):
        from panda3d.core import Filename, NodePath
        from panda3d.bullet import BulletRigidBodyNode, BulletBoxShape

        from game_system.resources import ResourceManager
        f = Filename.fromOsSpecific(ResourceManager.get_absolute_path(ResourceManager["TestActor"]["Cube.egg"]))
        model = loader.loadModel(f)

        bullet_node = BulletRigidBodyNode("BulletPlane")
        bullet_nodepath = NodePath(bullet_node)

        shape = BulletBoxShape((1, 1, 1))
        bullet_node.addShape(shape)
        bullet_node.setMass(1.0)

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
        from panda3d.core import Filename, NodePath
        from panda3d.bullet import BulletRigidBodyNode, BulletPlaneShape

        from game_system.resources import ResourceManager
        f = Filename.fromOsSpecific(ResourceManager.get_absolute_path(ResourceManager["Plane"]["Plane.egg"]))
        model = loader.loadModel(f)

        bullet_node = BulletRigidBodyNode("BulletPlane")
        bullet_nodepath = NodePath(bullet_node)

        shape = BulletPlaneShape((0, 0, 1), 0)
        bullet_node.addShape(shape)
        bullet_node.setMass(1.0)

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