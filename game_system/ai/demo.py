from game_system.ai.planning.goap import Action, Goal, GOAPAIManager, Variable
from game_system.ai.state_machine.fsm import FiniteStateMachine
from game_system.ai.state_machine.state import State
from game_system.enums import EvaluationState


class GOTORequest:

    def __init__(self, name, target):
        self.name = name
        self.target = target
        self.status = EvaluationState.running

    def on_completed(self):
        self.status = EvaluationState.success


class GetWood(Action):
    effects = {"has_firewood": True, "near_item": "asd"}
    preconditions = {"near_item": "trees", "has_axe": True}

    max_distance = 30

    def get_near_object(self, tag, player):
        return min([o for o in player.scene.objects if tag in o], key=player.getDistanceTo)

    def evaluate(self, blackboard, world_state):
        tag = "trees"
        player = blackboard["player"]
        wood = self.get_near_object(tag, player)
        wood.endObject()
        return EvaluationState.success


class GetAxe(Action):
    effects = {"has_axe": True}
    preconditions = {"has_axe": False, "near_item": "axe"}


class GOTONearItem(Action):
    effects = {"near_item": Variable("near_item")}

    max_distance = 30

    def get_near_object(self, tag, player):
        for obj in player.scene.objects:
            if tag not in obj:
                continue

            if obj.getDistanceTo(player) > self.max_distance:
                continue

            if player.rayCastTo(obj) is not obj:
                continue

            return obj

        return None

    def check_procedural_precondition(self, blackboard, world_state, is_planning=True):
        tag = world_state["near_item"]
        player = blackboard["player"]
        return self.get_near_object(tag, player) is not None

    def evaluate(self, blackboard, world_state):
        tag = world_state["near_item"]
        fsm = blackboard['fsm']
        goto_state = fsm.states["GOTO"]

        # If no request exists or belongs elsewhere (shouldn't happen, might)
        if goto_state.request is None or goto_state.request.name is not tag:
            player = blackboard["player"]

            # Find near object
            obj = self.get_near_object(tag, player)

            if obj is None:
                return EvaluationState.failure

            goto_state.request = GOTORequest(tag, obj)

        return goto_state.request.status


class CollectBranches(Action):
    effects = {"has_firewood": True}
    preconditions = {"near_item": "sticks"}
    cost = 7

    def evaluate(self, blackboard, world_state):
        return EvaluationState.success


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
