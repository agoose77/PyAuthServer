from game_system.coordinates import Quaternion, Vector
from game_system.entity import AbstractTransformInstanceComponent, AbstractPhysicsInstanceComponent, MeshComponent, \
    InstanceComponent

from math import radians, degrees
from os import path

from panda3d.bullet import BulletRigidBodyNode, BulletBodyNode, BulletTriangleMeshShape, BulletTriangleMesh
from panda3d.core import Filename, Camera, Vec3F, NodePath


__all__ = "TransformInstanceComponent", "PhysicsInstanceComponent", "MeshInstanceComponent", \
          "AnimationInstanceComponent", "CameraInstanceComponent"


class PandaInstanceComponent(InstanceComponent):

    def update_root_nodepath(self, nodepath):
        return nodepath

    def set_root_nodepath(self, nodepath):
        pass


class TransformInstanceComponent(AbstractTransformInstanceComponent, PandaInstanceComponent):

    def __init__(self, entity, component):
        self._class_component = component
        self._nodepath = None
        self._entity = entity

    def set_root_nodepath(self, nodepath):
        self._nodepath = nodepath

        original_position = self._class_component.position
        if original_position:
            self.world_position = original_position

        original_orientation = self._class_component.orientation
        if original_orientation:
            self.world_orientation = original_orientation

    def move(self, dr, local=False):
        if not local:
            pos = self._nodepath.get_pos(self._entity.scene._root_nodepath)

        else:
            pos = self._nodepath.get_pos()

        pos += Vec3F(dr.x, dr.y, dr.z)
        self._nodepath.set_pos(pos)

    @property
    def world_position(self):
        return Vector(self._nodepath.get_pos(self._entity.scene._root_nodepath))

    @world_position.setter
    def world_position(self, position):
        self._nodepath.set_pos(self._entity.scene._root_nodepath, *position)

    @property
    def world_orientation(self):
        l, i, j, k = self._nodepath.get_quat(self._entity.scene._root_nodepath)
        return Quaternion((l, i, j, k))

    @world_orientation.setter
    def world_orientation(self, orientation):
        l, i, j, k = orientation
        self._nodepath.set_quat(self._entity.scene._root_nodepath, (l, i, j, k))


class PhysicsInstanceComponent(AbstractPhysicsInstanceComponent, PandaInstanceComponent):

    def __init__(self, entity, component):
        self.body = None
        self._entity = entity

        self._class_component = component

    def set_root_nodepath(self, nodepath):
        self._entity.scene.physics_manager.add_entity(self._entity, self)

    def update_root_nodepath(self, nodepath):
        entity = self._entity
        component = self._class_component

        # Find appropriate mesh source
        mesh_name = component.mesh_name
        if mesh_name is None:
            physics_node = BulletRigidBodyNode()

            # Load mesh from first MeshComponent
            for cls_component in entity.components.values():
                if isinstance(cls_component, MeshComponent):
                    shape = self._shape_from_mesh_component(entity, cls_component)
                    physics_node.add_shape(shape)
                    break

        else:
            physics_node = self._node_from_bam_name(entity, mesh_name)

        # Set mass
        if component.mass is not None:
            physics_node.set_mass(component.mass)

        physics_node.notify_collisions(True)
        physics_node.set_deactivation_enabled(False)

        physics_nodepath = NodePath(physics_node)
        nodepath.reparent_to(physics_nodepath)

        self.body = physics_node
        self._nodepath = physics_nodepath

        return physics_nodepath

    @staticmethod
    def _node_from_bam_name(entity, bam_name):
        mesh_filename = "{}.bam".format(bam_name)

        root_path = entity.scene.resource_manager.root_path
        model_path = path.join(root_path, "meshes", mesh_filename)

        filename = Filename.from_os_specific(model_path)
        nodepath = loader.loadModel(filename)

        if not isinstance(nodepath.node(), BulletBodyNode):
            raise ValueError("Invalid node type {}".format(nodepath.node().get_class_type()))

        return nodepath.node()

    @staticmethod
    def _shape_from_mesh_component(entity, component):
        """Load triangle mesh from class MeshComponent"""
        mesh_filename = "{}.egg".format(component.mesh_name)

        root_path = entity.scene.resource_manager.root_path
        model_path = path.join(root_path, "meshes", mesh_filename)

        filename = Filename.from_os_specific(model_path)
        nodepath = loader.loadModel(filename)

        geom_nodepath = nodepath.find('**/+GeomNode')
        geom_node = geom_nodepath.node()
        geom = geom_node.get_geom(0)

        transform = geom_node.getTransform()
        mesh = BulletTriangleMesh()
        mesh.addGeom(geom, True, transform)
        return BulletTriangleMeshShape(mesh, dynamic=False)

    @property
    def mass(self):
        return self.body.get_mass()

    @mass.setter
    def mass(self, value):
        self.body.set_mass(value)

    @property
    def world_velocity(self):
        return Vector(self.body.get_linear_velocity())

    @world_velocity.setter
    def world_velocity(self, value):
        self.body.set_linear_velocity(value[:])

    @property
    def world_angular(self):
        return Vector(self.body.get_angular_velocity())

    @world_angular.setter
    def world_angular(self, value):
        self.body.set_angular_velocity(value[:])

    def apply_force(self, force, position):
        self.body.apply_force(force[:], position[:])

    def apply_impulse(self, impulse, position):
        self.body.apply_impulse(impulse[:], position[:])

    def apply_torque(self, torque):
        self.body.apply_torque(torque[:])

    def on_destroyed(self):
        self._entity.scene.physics_manager.remove_entity(self._entity, self)


class MeshInstanceComponent(PandaInstanceComponent):

    def __init__(self, entity, component):
        self._root_path = entity.scene.resource_manager.root_path
        self._root_nodepath = None

        self._entity = entity
        self._model = self._load_mesh_from_name(component.mesh_name, self._root_path)

    def _load_mesh_from_name(self, mesh_name, root_path):
        mesh_filename = "{}.egg".format(mesh_name)
        model_path = path.join(root_path, "meshes", mesh_filename)

        filename = Filename.from_os_specific(model_path)
        return loader.loadModel(filename)

    def change_mesh(self, mesh_name):
        nodepath = self._load_mesh_from_name(mesh_name, self._root_path)
        nodepath.reparent_to(self._root_nodepath)

        self._model.remove_node()
        self._model = nodepath

    def set_root_nodepath(self, nodepath):
        self._root_nodepath = nodepath
        self._model.reparent_to(nodepath)

    def on_destroyed(self):
        self._model.remove_node()


class AnimationInstanceComponent(PandaInstanceComponent):

    def __init__(self, entity, component):
        print("Animation", component)


class CameraInstanceComponent(PandaInstanceComponent):

    def __init__(self, entity, component):
        self._camera = Camera(entity.__class__.__name__)

    def set_root_nodepath(self, nodepath):
        nodepath.attach_new_node(self._camera)

    def on_destroyed(self):
        self._camera.remove_node()