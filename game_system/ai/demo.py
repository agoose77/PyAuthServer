from game_system.ai.planning.goap import Action, Goal, GOAPAIManager, Variable
from game_system.ai.state_machine.fsm import FiniteStateMachine
from game_system.ai.state_machine.state import State
from game_system.enums import EvaluationState


def find_visible(player, tag):
    for obj in player.scene.objects:
        if not tag in obj:
            continue

        if player.rayCastTo(obj) is not obj:
            continue

        return obj


class GOTORequest:

    def __init__(self, target):
        self.target = target
        self.status = EvaluationState.running

    def on_completed(self):
        self.status = EvaluationState.success


class GetWood(Action):
    effects = {"has_firewood": True}
    preconditions = {"at_location": "woods", "has_axe": True}


class GetAxe(Action):
    effects = {"has_axe": True}
    preconditions = {"has_axe": False, "at_location": "axe"}


class GOTONearestAxe(Action):
    effects = {"at_location": "axe"}

    def check_procedural_precondition(self, blackboard, world_state, is_planning=True):
        player = blackboard['player']
        return find_visible(player, "axe") is not None

    def evaluate(self, blackboard, world_state):
        player = blackboard['player']
        target = find_visible(player, "axe")

        fsm = blackboard['fsm']
        goto_state = fsm.states["GOTO"]

        if target:
            if goto_state.request is None or goto_state.request.target is not target:
                goto_state.request = GOTORequest(target)

        return goto_state.request.status


class GOTONearestWoods(Action):
    effects = {"at_location": "woods"}

    def check_procedural_precondition(self, blackboard, world_state, is_planning=True):
        player = blackboard['player']
        return find_visible(player, "trees") is not None

    def evaluate(self, blackboard, world_state):
        player = blackboard['player']
        target = find_visible(player, "trees")

        fsm = blackboard['fsm']
        goto_state = fsm.states["GOTO"]

        if target:
            if goto_state.request is None or goto_state.request.target is not target:
                goto_state.request = GOTORequest(target)

        return goto_state.request.status



# class GOTOAction(Action):
#     effects = {"at_location": Variable("at_location")}
#
#     def repr(self, no):
#         return "GOTO: {}".format(no.goal_state['at_location'])
#
#     def evaluate(self, blackboard, world_state):
#         target = world_state['at_location']
#
#         fsm = blackboard['fsm']
#         goto_state = fsm.states["GOTO"]
#
#         if goto_state.request is None or goto_state.request.target is not target:
#             goto_state.request = GOTORequest(target)
#
#         return goto_state.request.status
#
#
# LookForAxe = create_finder_class("axe")
# LookForWoods = create_finder_class("woods")
# LookForSticks = create_finder_class("sticks")
#
#
# class GetAxe(Action):
#     preconditions = {"at_location": Variable("axe_location")}
#     effects = {"has_axe": True}
#
#     def get_procedural_cost(self, blackboard):
#         return super().get_procedural_cost(blackboard)
#
#         player = blackboard['player']
#         axe = blackboard['axe']
#
#         return (player.worldPosition - axe.worldPosition).length / 10
#
#     def evaluate(self, blackboard):
#         axe = blackboard['axe']
#
#         fsm = blackboard['fsm']
#         goto_state = fsm.states["GOTO"]
#
#         if goto_state.request is None or goto_state.request.target is not axe:
#             goto_state.request = GOTORequest(axe)
#
#         return goto_state.request.status
#
#
# class ChopLog(Action):
#     preconditions = {"has_axe": True, "at_woods": True}
#     effects = {"has_firewood": True}
#     cost = 2
#
#     def evaluate(self, blackboard):
#         blackboard['woods'].endObject()
#         blackboard['at_woods'] = False
#         return EvaluationState.success
#
#


class CollectBranches(Action):
    effects = {"has_firewood": True}
    # preconditions = {"sticks_available": True}
    cost = 70

    # def evaluate(self, world_state):
    #     sticks = blackboard['sticks']
    #
    #     fsm = blackboard['fsm']
    #     goto_state = fsm.states["GOTO"]
    #
    #     if goto_state.request is None or goto_state.request.target is not sticks:
    #         goto_state.request = GOTORequest(sticks)
    #
    #     return goto_state.request.status


class GetFirewoodGoal(Goal):
    state = {"has_firewood": True}


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

        player = self.blackboard["player"]
        to_target = request.target.worldPosition - player.worldPosition

        if to_target.length_squared < 1:
            request.status = EvaluationState.success

        else:
            player.worldPosition += to_target.normalized() * 0.15


class AnimateState(State):

    def __init__(self, blackboard):
        super().__init__("Animate")

        self.blackboard = blackboard


def init(cont):
    own = cont.owner

    blackboard = GameObjBlackboard(own)

    fsm = FiniteStateMachine()

    goto_state = GOTOState(blackboard)
    animate_state = AnimateState(blackboard)

    fsm.add_state(goto_state)
    fsm.add_state(animate_state)

    blackboard["player"] = own
    blackboard["fsm"] = fsm
    blackboard["at_location"] = None

    actions = Action.__subclasses__()
    goals = [GetFirewoodGoal()]

    goap_ai_manager = GOAPAIManager(blackboard, goals, actions)

    own['ai'] = goap_ai_manager
    own['fsm'] = fsm


def main(cont):
    own = cont.owner
    
    ai_manager = own['ai']
    fsm = own['fsm']

    ai_manager.update()
    fsm.state.update()
