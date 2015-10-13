from game_system.entity import EntityConfigurationManager, ITransformInterface


class BGEConfigurationManager(EntityConfigurationManager):

    _interface_classes = {}

    def __init__(self, bge_scene, resource_manager):
        super().__init__(resource_manager)

        self._bge_scene = bge_scene

    @classmethod
    def register_interface(cls, name, interface_cls):
        if name in cls._interface_classes:
            raise ValueError("'{}' interface already registered".format(name))

        cls._interface_classes[name] = interface_cls

    def _apply_configuration(self, configuration, entity):
        bge_configuration = configuration["BGE"]

        object_name = bge_configuration["object_name"]
        print("CONFIGURE", object_name)
        return
        game_obj = self._bge_scene.addObject(object_name)

        # Interface mapping
        for interface_name in entity.interface_names:
            interface_cls = self._interface_classes[interface_name]
            interface = interface_cls(configuration, game_obj)

            # Store on entity
            setattr(entity, interface_name, interface)

    def deconfigure_entity(self, entity):
        print("DECONFIGURE", entity)
#
# class BGETransformInterface(ITransformInterface):
#     """Physics implementation for BGE entity"""
#
#     def __init__(self, config_section, entity, obj):
#         self._entity = entity
#
#         #self.sockets = self.create_sockets(self._game_object)
#         self._parent = None
#
#     @property
#     def parent(self):
#         return self._parent
#
#     @parent.setter
#     def parent(self, parent):
#         if parent is self._parent:
#             return
#
#         self._parent.children.remove(self._entity)
#         self._game_object.removeParent()
#
#         if parent is None:
#             return
#
#         if not isinstance(parent, BGEParentableBase):
#             raise TypeError("Invalid parent type {}".format(parent.__class__.__name__))
#
#         self._game_object.setParent(parent._game_object)
#         parent.children.add(self._entity)
#         self._parent = parent
#
#     @property
#     def world_position(self):
#         return self._game_object.worldPosition
#
#     @world_position.setter
#     def world_position(self, position):
#         self._game_object.worldPosition = position
#
#     @property
#     def world_orientation(self):
#         return self._game_object.worldOrientation.to_euler()
#
#     @world_orientation.setter
#     def world_orientation(self, orientation):
#         self._game_object.worldOrientation = orientation
#
#     def align_to(self, vector, factor=1, axis=Axis.y):
#         """Align object to vector
#         :param vector: direction vector
#         :param factor: slerp factor
#         :param axis: alignment direction
#         """
#         if not vector.length_squared:
#             return
#
#         forward_axis = Axis[axis].upper()
#
#         rotation_quaternion = vector.to_track_quat(forward_axis, "Z")
#         current_rotation = self.world_orientation.to_quaternion()
#         self.world_orientation = current_rotation.slerp(rotation_quaternion, factor).to_euler()
#
#     def create_sockets(self, obj):
#         return {BGESocket(c, self) for c in obj.childrenRecursive if "socket" in c}
#
#     def get_direction_vector(self, axis):
#         """Get the axis vector of this object in world space
#         :param axis: :py:class:`game_system.enums.Axis` value
#         :rtype: :py:class:`game_system.coordinates.Vector`
#         """
#         vector = [0, 0, 0]
#         vector[axis] = 1
#
#         return Vector(self.object.getAxisVect(vector))
#
#
# # Register interfaces
# EntityConfigurationManager.register_interface("transform", BGETransformInterface)
