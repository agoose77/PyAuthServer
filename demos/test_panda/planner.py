from game_system.ai.planning.goap import Action, Goal
from game_system.controllers import GOTORequest
from game_system.enums import EvaluationState
from network.replicable import Replicable

from .actors import AmmoPickup


class FindAmmoGoal(Goal):
    state = {"has_ammo": True}

    priority = 0.5


class GetNearestAmmoPickup(Action):
    effects = {"has_ammo": True}

    def on_enter(self, controller, goal_state):
        goto_state = controller.fsm.states['GOTO']

        pawn_position = controller.pawn.transform.world_position

        def get_distance_to_squared(actor):
            return (actor.transform.world_position - pawn_position).length_squared

        nearest_pickup = min(Replicable.subclass_of_type(AmmoPickup), key=get_distance_to_squared)
        goto_state.request = GOTORequest(nearest_pickup)

    def on_exit(self, controller, goal_state):
        goto_state = controller.fsm.states['GOTO']
        controller.blackboard["ammo"] += goto_state.request.target.ammo
        goto_state.request.target.deregister()

        # Apply to world state
        self.apply_effects(controller.blackboard, goal_state)

    def get_status(self, controller):
        goto_state = controller.fsm.states['GOTO']
        print(controller.fact_manager.facts)
        return goto_state.request.status
