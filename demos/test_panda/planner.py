from game_system.ai.planning.goap import Action, Goal
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
