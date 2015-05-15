from network.enums import Netmodes
from network.network import Network
from network.signals import SignalListener, Signal
from network.world_info import WorldInfo
from network.signals import DisconnectSignal
from network.replicable import Replicable

from game_system.enums import PhysicsType
from game_system.timer import Timer
from game_system.signals import ConnectToSignal, TimerUpdateSignal, UIUpdateSignal, PlayerInputSignal, \
    LogicUpdateSignal, PhysicsTickSignal, PostPhysicsSignal
from game_system.level_manager import LevelManager
from game_system.game_loop import FixedTimeStepManager, OnExitUpdate
from game_system.enums import ButtonState, InputButtons


import bpy

from .physics import BlenderPhysicsSystem

from game_system.controllers import *
from game_system.entities import Actor

from game_system.resources import ResourceManager
ResourceManager.environment = "Blender"
ResourceManager.data_path = bpy.path.abspath("//data")

from network.decorators import with_tag
from network.signals import SignalListener
from network.tagged_delegate import FindByTag
from game_system.definitions import ComponentLoader, ComponentLoaderResult


from mathutils import *


class BlenderComponent(FindByTag):
    """Base class for Blender component"""

    subclasses = {}

    def destroy(self):
        """Destroy component"""
        pass


class BlenderParentableBase:

    def __init__(self, obj):
        self._object = obj
        self.children = set()


@with_tag("physics")
class BlenderPhysicsInterface(BlenderComponent):

    def __init__(self, config_section, entity, nodepath):
        self._object = nodepath
        self._entity = entity

        self._level_manager = LevelManager()


        self._suspended_mass = None

    @staticmethod
    def entity_from_nodepath(nodepath):
        return

    def destroy(self):
        pass

    def ray_test(self, target, source=None, distance=0.0):
        """Perform a ray trace to a target

        :param target: target to trace towards
        :param source: optional origin of trace, otherwise object position
        :param distance: distance to use instead of vector length
        :rtype: :py:class:`game_system.physics.RayTestResult`
        """
        return

        return RayTestResult(Vector(), Vector(), None, 10)

    @property
    def type(self):
        return PhysicsType.dynamic

    @property
    def suspended(self):
        return self._suspended_mass is not None

    @suspended.setter
    def suspended(self, value):
        if value == self.suspended:
            return

        return

    @property
    def mass(self):
        if self.suspended:
            return self._suspended_mass

        else:
            return 1.0

    @mass.setter
    def mass(self, value):
        if self.suspended:
            self._suspended_mass = value

        else:
            pass

    @property
    def is_colliding(self):
        return bool(self._level_manager)

    @property
    def world_velocity(self):
        from math import sqrt
        sign = 1 if self._object.location.z > 0 else -1
        return Vector((0, 0, sign *  sqrt(2 * 9.81 * abs(self._object.location.z))))

    @world_velocity.setter
    def world_velocity(self, velocity):
        pass

    @property
    def world_angular(self):
        return Vector()

    @world_angular.setter
    def world_angular(self, angular):
        pass

    @property
    def local_velocity(self):
        return Vector()

    @local_velocity.setter
    def local_velocity(self, velocity):
        pass

    @property
    def local_angular(self):
        return Vector()

    @local_angular.setter
    def local_angular(self, angular):
        pass


from network.world_info import WorldInfo


@with_tag("transform")
class BlenderTransformInterface(BlenderComponent, SignalListener, BlenderParentableBase):
    """Transform implementation for Blender entity"""

    def __init__(self, config_section, entity, nodepath):
        super().__init__(nodepath)

        self._entity = entity

        self.sockets = self.create_sockets(nodepath)
        self._parent = None

        self.register_signals()

    @property
    def parent(self):
        return None

    def create_sockets(self, nodepath):
        sockets = set()
        return sockets

    @property
    def world_position(self):
        return self._object.location

    @world_position.setter
    def world_position(self, position):
        self._object.location = position

    @property
    def world_orientation(self):
        return self._object.rotation_euler

    @world_orientation.setter
    def world_orientation(self, orientation):
        self._object.rotation_euler = orientation

    def get_direction_vector(self, axis):
        """Get the axis vector of this object in world space

        :param axis: :py:class:`game_system.enums.Axis` value
        :rtype: :py:class:`game_system.coordinates.Vector`
        """
        direction = Vector((0, 0, 0))
        direction[axis] = 1

        rotation = self._object.matrix_world
        return rotation * direction


@with_tag("Blender")
class BlenderComponentLoader(ComponentLoader):

    def __init__(self, *component_tags):
        self.component_tags = component_tags
        self.component_classes = {tag: BlenderComponent.find_subclass_for(tag) for tag in component_tags}

    @staticmethod
    def create_object(config_parser, entity):
        object_name = config_parser['object_name']

    @classmethod
    def find_object(cls, config_parser):
        object_name = config_parser['object_name']
        return bpy.context.scene.objects[object_name]

    # todo: don't use name, use some tag to indicate top level parent

    @classmethod
    def find_or_create_object(cls, entity, config_parser):
        if entity.is_static:
            return cls.find_object(config_parser)

        raise ValueError(entity)
        return cls.create_object(config_parser, entity)

    def load(self, entity, config_parser):
        nodepath = self.find_or_create_object(entity, config_parser)
        components = self._load_components(config_parser, entity, nodepath)

        def on_unloaded():
            raise ValueError()

        result = ComponentLoaderResult(components)
        result.on_unloaded = on_unloaded

        return result


class OperatorPanel(bpy.types.Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_label = "Blender Networking"
    bl_context = "scene"

    COMPAT_ENGINES = {'BLENDER_GAME'}

    @classmethod
    def register(cls):
        pass

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.operator("wm.run_network", text="Run Server")

        client = layout.operator("wm.run_network", text="Run Client")
        client.server = False


class RunIntervalOperator(bpy.types.Operator):
    """Operator which runs its self from a timer"""
    bl_idname = "wm.run_network"
    bl_label = "Run Network"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None

    dt = bpy.props.FloatProperty(name="Delta Time", default=1/60, min=1/80, max=1/5)
    server = bpy.props.BoolProperty(name="Server", default=True)

    def modal(self, context, event):
        if event.type in {'ESC'}:
            return self.cancel(context)

        if event.type == 'TIMER':
            # change theme color, silly!
            self._gameloop.on_step(self.dt)

        return {'PASS_THROUGH'}

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):

        wm = context.window_manager
        self._timer = wm.event_timer_add(self.dt, context.window)

        if self.server:
            self._gameloop = Server()
            print("SERVER")

        else:
            WorldInfo.netmode = Netmodes.client
            self._gameloop = Client()
            print("Client")
            self.con = self._gameloop.new_connection("localhost", 1200)

        print("Running!")
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        print("CANCELLED")
        return {'CANCELLED'}


class GameLoop(SignalListener, FixedTimeStepManager):

    def __init__(self):
        FixedTimeStepManager.__init__(self)

        self.register_signals()

        # Todo: Copy Panda data
        WorldInfo.tick_rate = 60
        self.use_tick_rate = True
        self.animation_rate = 24
        self.use_animation_rate = True

        # Create sub systems
        self.network_system = self.create_network()
       # self.input_manager = PandaInputManager()
        self.physics_system = BlenderPhysicsSystem()

        # Timing information
        self.last_sent_time = 0
        self.current_time = 0

        self.network_tick_rate = 25
        self.metric_interval = 0.10

        # Load world
        self.pending_exit = False

        print("Network initialised")

    def cleanup(self):
        pass

    def invoke_exit(self):
        self.pending_exit = True

    def on_step(self, delta_time):
        self.network_system.receive()

        # Update inputs
        # base.taskMgr.step()
        # self.input_manager.update()
        #
        # input_state = self.input_manager.state
        #
        # # Todo: allow this to be specified by game
        # if input_state.buttons[InputButtons.ESCKEY] == ButtonState.pressed:
        #     self.invoke_exit()
        #
        # if self.pending_exit:
        #     raise OnExitUpdate()
        #
        # # Update Player Controller inputs for client
        # if WorldInfo.netmode != Netmodes.server:
        #     PlayerInputSignal.invoke(delta_time, input_state)
        #     self.update_graphs()

        # Update main logic (Replicable update)
        LogicUpdateSignal.invoke(delta_time)

        # Update Physics, which also handles Scene-graph
        PhysicsTickSignal.invoke(delta_time)

        # Clean up following Physics update
        PostPhysicsSignal.invoke()

        # Transmit new state to remote peer
        is_full_update = ((self.current_time - self.last_sent_time) >= (1 / self.network_tick_rate))

        if is_full_update:
            self.last_sent_time = self.current_time

        self.network_system.send(is_full_update)

        network_metrics = self.network_system.metrics
        if network_metrics.sample_age >= self.metric_interval:
            network_metrics.reset_sample_window()

        # Update UI
        UIUpdateSignal.invoke(delta_time)

        # Update Timers
        TimerUpdateSignal.invoke(delta_time)

        # Handle this outside of usual update
        WorldInfo.update_clock(delta_time)
        self.current_time += delta_time


class Server(GameLoop):

    @staticmethod
    def create_network():
        return Network("", 1200)


class Client(GameLoop):

    graceful_exit_time_out = 0.6

    def invoke_exit(self):
        """Gracefully quit server"""
        quit_func = super().invoke_exit()
        # Try and quit gracefully
        DisconnectSignal.invoke(quit_func)
        # But include a time out
        timeout = Timer(self.graceful_exit_time_out)
        timeout.on_target = quit_func

    @staticmethod
    def create_network():
        return Network("", 0)

    @ConnectToSignal.on_global
    def new_connection(self, address, port):
        return self.network_system.connect_to(address, port)


def register():
    bpy.utils.register_class(RunIntervalOperator)
    bpy.utils.register_class(OperatorPanel)


def unregister():
    bpy.utils.unregister_class(RunIntervalOperator)
    bpy.utils.unregister_class(OperatorPanel)


if __name__ == "__main__":
    register()
