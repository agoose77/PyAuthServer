from game_system.ai.planning.goap import Action, Goal, GOAPAIManager
from game_system.ai.state_machine.fsm import FiniteStateMachine
from game_system.ai.state_machine.state import State
from game_system.enums import EvaluationState


class GOTORequest:

    def __init__(self, target):
        self.target = target
        self.status = EvaluationState.running

    def on_completed(self):
        self.status = EvaluationState.success


class LookForAxe(Action):
    effects = {"axe_available": True}

    def __init__(self):
        super().__init__()

        self._axe = None

    def check_procedural_precondition(self, blackboard):
        player = blackboard['player']
        for obj in player.scene.objects:
            if "axe" not in obj:
                continue

            hit_obj = player.rayCastTo(obj)

            if hit_obj is not obj:
                continue

            self._axe = hit_obj
            return True

        return False

    def evaluate(self, blackboard):
        blackboard['axe'] = self._axe
        self._axe = None

        return EvaluationState.success


class GetAxe(Action):
    preconditions = {"axe_available": True}
    effects = {"has_axe": True}

    def get_procedural_cost(self, blackboard):
        return super().get_procedural_cost(blackboard)
        assert self.check_procedural_precondition(blackboard)
        player = blackboard['player']
        axe = blackboard['axe']

        return (player.worldPosition - axe.worldPosition).length / 10

    def evaluate(self, blackboard):
        axe = blackboard['axe']
        goto_request = blackboard['goto_request']

        if goto_request is None or goto_request.target is not axe:
            blackboard['goto_request'] = GOTORequest(axe)
            return EvaluationState.running

        return goto_request.status


class ChopLog(Action):
    preconditions = {"has_axe": True}
    effects = {"has_firewood": True}
    cost = 2


class CollectBranches(Action):
    effects = {"has_firewood": True}
    cost = 4


class GetFirewoodGoal(Goal):
    state = {"has_firewood": True}


def init(cont):
    own = cont.owner
    
    blackboard = {"has_axe": False, "axe_available": False, "has_firewood": False, "goto_request": None,
                  "player": own}
    actions = [GetAxe(), ChopLog(),
               CollectBranches(),
               LookForAxe()]
    goals = [GetFirewoodGoal()]

    goap_ai_manager = GOAPAIManager(blackboard, goals, actions)
    own['ai'] = goap_ai_manager


def main(cont):
    own = cont.owner
    
    ai_manager = own['ai']
    ai_manager.update()
