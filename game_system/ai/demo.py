from game_system.ai.planning.goap import Action, Goal, GOAPAIManager, Variable
from game_system.ai.state_machine.fsm import FiniteStateMachine
from game_system.ai.state_machine.state import State
from game_system.enums import EvaluationState

from time import monotonic


class GOTORequest:

    def __init__(self, target):
        self.target = target
        self.status = EvaluationState.running

    def on_completed(self):
        self.status = EvaluationState.success


# class GOTONearItem(Action):
#     effects = {"near_item": Variable("near_item")}
#
#     max_distance = 30
#
#     def get_near_object(self, tag, player):
#         for obj in player.scene.objects:
#             if tag not in obj:
#                 continue
#
#             if obj.getDistanceTo(player) > self.max_distance:
#                 continue
#
#             if player.rayCastTo(obj) is not obj:
#                 continue
#
#             return obj
#
#         return None
#
#     def check_procedural_precondition(self, blackboard, world_state, is_planning=True):
#         tag = world_state["near_item"]
#         player = blackboard["player"]
#         return self.get_near_object(tag, player) is not None
#
#     def evaluate(self, blackboard, world_state):
#         tag = world_state["near_item"]
#         fsm = blackboard.fsm
#         goto_state = fsm.states["GOTO"]
#
#         # If no request exists or belongs elsewhere (shouldn't happen, might)
#         if goto_state.request is None or goto_state.request.name is not tag:
#             player = blackboard.player
#
#             # Find near object
#             obj = self.get_near_object(tag, player)
#
#             if obj is None:
#                 return EvaluationState.failure
#
#             goto_state.request = GOTORequest(tag, obj)
#
#         return goto_state.request.status
#


class ChaseTarget(Action):
    effects = {"in_weapons_range": True}

    def check_procedural_precondition(self, blackboard, world_state, is_planning=True):
        return blackboard['target'] is not None

    def on_enter(self, blackboard, world_state):
        target = blackboard['target']
        blackboard.fsm.states['GOTO'].request = GOTORequest(target)


class Attack(Action):
    effects = {"target_is_dead": True}
    preconditions = {"weapon_is_loaded": True, "in_weapons_range": True}

    def on_enter(self, blackboard, world_state):
        blackboard['fire_weapon'] = True

    def on_exit(self, blackboard):
        blackboard['fire_weapon'] = False

    def get_status(self, blackboard):
        if not blackboard['weapon_is_loaded']:
            return EvaluationState.failure

        target = blackboard['target']

        if target is None:
            return EvaluationState.failure

        if target.invalid or target['health'] < 0:
            return EvaluationState.success

        else:
            return EvaluationState.failure


class ReloadWeapon(Action):
    """Reload weapon if we have ammo"""
    effects = {"weapon_is_loaded": True}
    preconditions = {"has_ammo": True}


class GetNearestAmmoPickup(Action):
    """GOTO nearest ammo pickup in level"""
    effects = {"has_ammo": True}

    def on_enter(self, blackboard, world_state):
        goto_state = blackboard.fsm.states['GOTO']

        player = blackboard.player
        nearest_pickup = min([o for o in player.scene.objects if "ammo" in o and "pickup" in o],
                             key=player.getDistanceTo)

        goto_state.request = GOTORequest(nearest_pickup)

    def on_exit(self, blackboard):
        goto_state = blackboard.fsm.states['GOTO']
        blackboard["ammo"] += goto_state.request.target["ammo"]

    def get_status(self, blackboard):
        goto_state = blackboard.fsm.states['GOTO']
        return goto_state.request.status


class KillEnemyGoal(Goal):
    """Kill enemy if target exists"""
    state = {"target_is_dead": True}

    def get_relevance(self, blackboard):
        if blackboard["target"] is not None:
            return 0.7

        return 0.0


class ReloadWeaponGoal(Goal):
    """Reload weapon if not loaded"""

    priority = 0.45
    state = {"weapon_is_loaded": True}


class GameObjBlackboard:

    def __init__(self, obj):
        self._obj = obj

    def __getitem__(self, name):
        return self._obj[name]

    def __setitem__(self, name, value):
        self._obj[name] = value

    def copy(self):
        return dict(self.items())

    def get(self, name, default=None):
        try:
            return self[name]

        except KeyError:
            return default

    def setdefault(self, name, value):
        try:
            return self[name]

        except KeyError:
            self[name] = value
            return value

    def keys(self):
        return iter(self._obj.getPropertyNames())

    def update(self, other):
        for key, value in other.items():
            self._obj[key] = value

    def values(self):
        return (self._obj[x] for x in self.keys())

    def items(self):
        return ((x, y) for x, y in zip(self.keys(), self.values()))

    def __repr__(self):
        return repr(dict(self.items()))


class GOTOState(State):

    def __init__(self, blackboard):
        super().__init__("GOTO")

        self.blackboard = blackboard
        self.request = None

    def update(self):
        request = self.request

        if request is None:
            return

        if request.status != EvaluationState.running:
            return

        player = self.blackboard.player
        to_target = request.target.worldPosition - player.worldPosition

        if to_target.length_squared < 1:
            request.status = EvaluationState.success

        else:
            player.worldPosition += to_target.normalized() * 0.15


class AnimateState(State):

    def __init__(self, blackboard):
        super().__init__("Animate")

        self.blackboard = blackboard


class SystemManager:

    def __init__(self):
        self.systems = []

    def update(self):
        for system in self.systems:
            system.update()


class WeaponFireManager:

    def __init__(self, blackboard):
        self.blackboard = blackboard
        blackboard['fire_weapon'] = False

        self.shoot_time = 0.1
        self.last_fired_time = 0

    def update(self):
        if self.blackboard['fire_weapon']:
            now = monotonic()
            if now - self.last_fired_time > self.shoot_time:
                self.last_fired_time = now
                self.blackboard['target']['health'] -= 10
                if self.blackboard['target']['health'] <= 0:
                    self.blackboard['target'].endObject()
                    self.blackboard['fire_weapon'] = False

                self.blackboard['ammo'] -= 1

                if not self.blackboard['ammo']:
                    self.blackboard['has_ammo'] = False
                    self.blackboard['fire_weapon'] = False
                    self.blackboard['weapon_is_loaded'] = False


class TargetManager:

    def __init__(self, blackboard):
        self.blackboard = blackboard
        self.player = blackboard.player

        blackboard['target'] = None

    def get_closest_enemy(self):
        enemies = [o for o in self.player.scene.objects if "enemy" in o]
        if not enemies:
            return None
        return min(enemies, key=self.player.getDistanceTo)

    def update(self):
        blackboard = self.blackboard
        if blackboard['target'] is None:
            blackboard['target'] = self.get_closest_enemy()


def init(cont):
    own = cont.owner

    blackboard = GameObjBlackboard(own)

    fsm = FiniteStateMachine()

    goto_state = GOTOState(blackboard)
    animate_state = AnimateState(blackboard)

    fsm.add_state(goto_state)
    fsm.add_state(animate_state)

    blackboard.player = own
    blackboard.fsm = fsm

    sys_man = SystemManager()
    sys_man.systems.append(TargetManager(blackboard))
    sys_man.systems.append(WeaponFireManager(blackboard))

    actions = Action.__subclasses__()
    goals = [c() for c in Goal.__subclasses__()]

    goap_ai_manager = GOAPAIManager(blackboard, goals, actions)

    own['ai'] = goap_ai_manager
    own['fsm'] = fsm
    own['system_manager'] = sys_man


def main(cont):
    own = cont.owner
    
    ai_manager = own['ai']
    fsm = own['fsm']
    sys_man = own['system_manager']

    sys_man.update()
    ai_manager.update()
    fsm.state.update()
