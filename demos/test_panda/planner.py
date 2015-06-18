from game_system.ai.planning.goap import Action, Goal
from game_system.ai.working_memory import WMFact
from game_system.ai.sensors import SightInterpreter
from game_system.controllers import GOTORequest
from game_system.enums import EvaluationState
from network.replicable import Replicable

from .actors import AmmoPickup
from operator import attrgetter


class FindAmmoGoal(Goal):
    state = {"has_ammo": True}

    priority = 0.5


class GetNearestAmmoPickup(Action):
    effects = {"has_ammo": True}

    def find_nearest_ammo_pickup(self, controller):
        return controller.working_memory.find_single_fact('nearest_ammo').data

    def on_enter(self, controller, goal_state):
        goto_state = controller.fsm.states['GOTO']

        try:
            pickup = self.find_nearest_ammo_pickup(controller)

        except LookupError:
            request = None

        else:
            request = GOTORequest(pickup)

        goto_state.request = request

    def on_exit(self, controller, goal_state):
        goto_state = controller.fsm.states['GOTO']

        request = goto_state.request
        if request is None:
            return

        controller.blackboard["ammo"] += request.target.ammo
        request.target.deregister()

        # Apply to world state
        self.apply_effects(controller.blackboard, goal_state)

    def get_status(self, controller):
        goto_state = controller.fsm.states['GOTO']

        # We failed to set a target
        if goto_state.request is None:
            return EvaluationState.failure

        return goto_state.request.status


class PickupInterpreter(SightInterpreter):

    def __init__(self):
        self.sensor = None

    def handle_visible_actors(self, actors):
        pawn = self.sensor.controller.pawn
        if pawn is None:
            return

        pawn_position = pawn.transform.world_position
        distance_key = lambda a: (a.transform.world_position - pawn_position).length_squared

        try:
            closest_pickup = min(Replicable.subclass_of_type(AmmoPickup), key=distance_key)
        except ValueError:
            return

        working_memory = self.sensor.controller.working_memory

        try:
            fact = working_memory.find_single_fact('nearest_ammo')

        except KeyError:
            fact = WMFact('nearest_ammo')
            working_memory.add_fact(fact)

        fact.data = closest_pickup
        fact._uncertainty_accumulator = 0.0
