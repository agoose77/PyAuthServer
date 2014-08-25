from bge import logic
from network.decorators import with_tag
from game_system.definitions import ActorDefinition
from game_system.enums import AnimationMode, AnimationBlend


class BGEPhysicsInterface:

    def __init__(self, obj, config_section):
        self._obj = obj

    @property
    def world_position(self):
        return self._obj.worldPosition

    @world_position.setter
    def world_position(self, position):
        self._obj.worldPosition = position

    @property
    def world_velocity(self):
        return self._obj.worldLinearVelocity

    @world_velocity.setter
    def world_velocity(self, velocity):
        self._obj.worldLinearVelocity = velocity

    @property
    def world_orientation(self):
        return self._obj.worldOrientation.to_euler()

    @world_orientation.setter
    def world_orientation(self, orientation):
        self._obj.worldOrientation = orientation


class BGEAnimationInterface:

    def __init__(self, obj, config_section):
        self._obj = obj

        # Define conversions from Blender behaviours to Network animation enum
        self._bge_play_constants = {AnimationMode.play: logic.KX_ACTION_MODE_PLAY,
                                    AnimationMode.loop: logic.KX_ACTION_MODE_LOOP,
                                    AnimationMode.ping_pong: logic.KX_ACTION_MODE_PING_PONG}

        self._bge_blend_constants = {AnimationBlend.interpolate: logic.KX_ACTION_BLEND_BLEND,
                                     AnimationBlend.add: logic.KX_ACTION_BLEND_ADD}

    def play_animation(self, animation):
        play_mode = self._bge_play_constants[animation.mode]
        blend_mode = self._bge_blend_constants[animation.blend_mode]
        self._obj.playAction(animation.name, animation.start, animation.end, animation.layer, animation.priority,
                             animation.blend, play_mode, animation.weight, speed=animation.speed, blend_mode=blend_mode)

    def stop_animation(self, animation):
        self._obj.stopAction(animation.layer)

    def is_playing(self, animation):
        return self._obj.isPlayingAction(animation.layer)


@with_tag("BGE")
class BGEActorDefinition(ActorDefinition):

    def __init__(self, config_parser):
        scene = logic.getCurrentScene()

        object_name = config_parser['object_name']
        obj = scene.addObject(object_name, object_name)

        self.physics = BGEPhysicsInterface(obj, config_parser)
        self.animation = BGEAnimationInterface(obj, config_parser)

