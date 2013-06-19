from bge_network import Actor, PlayerController, InputManager, PhysicsData, Physics
from network import WorldInfo, StaticValue, Attribute, RPC, Netmodes, Roles, reliable, simulated, NetmodeOnly

from bge import events, logic
from mathutils import Vector, Euler

from time import monotonic
from collections import namedtuple, OrderedDict
from functools import wraps
from itertools import chain, islice
from math import radians
from functools import partial
from operator import lt

PlayerMove = namedtuple("PlayerMove", ("timestamp", "deltatime", "inputs"))

def update_physics_for(obj, deltatime):
    for replicable in WorldInfo.subclass_of(Actor):
        replicable.render_state.save()
    
    obj.scene.updatePhysics(deltatime)
    
    for replicable in WorldInfo.subclass_of(Actor):
        if replicable is obj:
            replicable.render_state.save()
        else:
            replicable.render_state.restore()

class RacingInputs(InputManager):
    mappings = {"forward": events.WKEY, "back": events.SKEY, "shift": events.MKEY, 'right': events.DKEY, 'left': events.AKEY}

class MoveManager:
    def __init__(self):
        self.saved_moves = OrderedDict()
        self.to_correct = OrderedDict()
        
        self.latest_move = 0
        self.latest_correction = 0
        self.max_id = 65535 
    
    def __bool__(self):
        return bool(self.saved_moves) or bool(self.to_correct)
    
    def increment_move(self):
        self.latest_move += 1
        if self.latest_move > self.max_id:
            self.latest_move = 0
        return self.latest_move
    
    def increment_correction(self):
        self.latest_correction += 1
        if self.latest_correction > self.max_id:
            self.latest_correction = 0
        return self.latest_correction
    
    def add_move(self, move):
        move_id = self.increment_move()
        self.saved_moves[move_id] = move
    
    def get_move(self, move_id):
        return self.saved_moves[move_id]
    
    def add_correction(self, move):
        move_id = self.increment_correction()
        self.to_correct[move_id] = move
    
    def get_correction(self, move_id):
        return self.to_correct[move_id]
    
    def remove_move(self, move_id):
        self.saved_moves.pop(move_id)
        
    def remove_correction(self, move_id):
        self.to_correct.pop(move_id)
        
    def sorted_moves(self, filter=None):
        if callable(filter):
            for k, v in self.saved_moves.items():
                if not filter(k):
                    continue
                yield k, v
        else:
            yield from self.saved_moves.values()
    
class RPGController(PlayerController):
    
    input_class = RacingInputs
    
    def on_create(self):
        super().on_create()
        
        self.moves = MoveManager()
        self.correction = None
        
        self.previous_informed = None
        self.previous_checked = None
        self.last_sent = None
        
        self.setup_physics()
    
    @NetmodeOnly(Netmodes.client)
    def setup_physics(self):
        logic.getCurrentScene().pre_draw.append(self.post_physics)
    
    def calculate_move(self, move):
        """Returns velocity and angular velocity of movement
        @param move: move to execute"""
        move_speed = 6.0 
        rotation_speed = 4.0 
        
        inputs = move.inputs
        
        y_direction = (inputs.forward.active - inputs.back.active)
        x_direction = (inputs.left.active - inputs.right.active)
        
        velocity = Vector((0.000, y_direction * move_speed, 0.000))
        angular = Vector((0.000, 0.000, x_direction * rotation_speed))
        
        return self.pawn.local_space(velocity), angular
    
    def check_delta_time(self, timestamp, deltatime):
        previous_time = timestamp - deltatime
        return True
        
    @RPC
    def server_perform_move(self, move_id: StaticValue(int, max_value=65535), timestamp: StaticValue(float), deltatime: StaticValue(float), inputs: StaticValue(InputManager), position: StaticValue(Vector), orientation: StaticValue(Euler)) -> Netmodes.server:
        assert self.check_delta_time(timestamp, deltatime), "Speedhacking detected"
        pawn = self.pawn
        
        # Create a move to simulate
        move = PlayerMove(timestamp, deltatime, inputs)
        # Determine the velocity and rotation outputs
        velocity, angular = self.calculate_move(move)
        # Set the physics properties and apply them
        pawn.physics.velocity = velocity
        # We can't use angular velocity with character physics
        pawn.physics.orientation.rotate(Euler(angular * deltatime))
        # Set physics
        pawn.physics_to_world()
        # Simulate
        update_physics_for(pawn, deltatime)
        # Apply results
        pawn.world_to_physics()
        # Stop bullet simulating this in the normal tick
        pawn.stop_moving()
        
        position_difference = (pawn.physics.position - position).length
        rotation_difference = abs(pawn.physics.orientation.z - orientation.z)
        
        position_margin = 0.15
        rotation_margin = radians(3)

        # Check the error between server and client
        if position_difference > position_margin or rotation_difference > rotation_margin:
            self.client_correct_move(move_id, pawn.physics)
        
        else:
            self.client_acknowledge_move(move_id)
     
    @RPC
    def client_acknowledge_move(self, move_id:StaticValue(int, max_value=65535)) -> Netmodes.client:
        self.moves.remove_move(move_id)
    
    @RPC
    def client_correct_move(self, move_id: StaticValue(int, max_value=65535), physics: StaticValue(PhysicsData)) -> Netmodes.client:
        self.correction = move_id, physics
        self.pawn.physics = physics
  
    def post_physics(self):
        moves = self.moves
        pawn = self.pawn
        
        if not pawn.registered:
            return
        
        # Get the result of the physics operation
        pawn.world_to_physics()

        # If we have no moves we can't resimulate/confirm moves
        if not moves:
            return
        
        move_id = moves.latest_move
        latest_move = moves.get_move(move_id)
        
        # If we have no correction then the latest move is set
        if not self.correction:
            # If we've not sent it
            if move_id != self.last_sent:
                # Send move
                self.server_perform_move(move_id, *chain(latest_move, (pawn.physics.position, pawn.physics.orientation)))
                self.last_sent = move_id
        
        # Otherwise we need to simulate the move
        else:
            # Get ID of correction
            correction_id = self.correction[0]
            # Find the successive moves
            following_moves = self.moves.sorted_moves(partial(lt, correction_id))
            
            print("Resimulating from {}".format(correction_id))
            
            # Re run all moves
            for replay_id, replay_move in following_moves:
                velocity, angular = self.calculate_move(replay_move)
                # Set the physics properties and apply them
                pawn.physics.velocity = velocity
                # We can't use angular velocity with character physics
                pawn.physics.orientation.rotate(Euler(angular * replay_move.deltatime))
                # Apply the simulation
                pawn.physics_to_world()
                update_physics_for(pawn, replay_move.deltatime)
                pawn.world_to_physics()
            
            # We didn't send the last one as it needed simulating
            if replay_id != self.last_sent:
                self.server_perform_move(replay_id, *chain(replay_move, (pawn.physics.position, pawn.physics.orientation)))
                self.last_sent = replay_id
            
            # Ensure no velocity could be further simulated
            pawn.stop_moving()
            # Remove the corrected move (no longer needed)
            self.moves.remove_move(correction_id)
            # Empty correction
            self.correction = None
            
    def player_update(self, delta_time):
        # Make sure we have a pawn object
        pawn = self.pawn
        
        if not pawn.registered:
            return
        
        timestamp = WorldInfo.elapsed
        
        # Create move object (as sent end of tick, playerinput is ok to be muteable)
        move = PlayerMove(timestamp=timestamp, deltatime=delta_time, inputs=self.player_input.static)
        
        # If no correction, make use of simulation
        # Otherwise it would be invalid anyway
        if self.correction is None:
            velocity, angular = self.calculate_move(move)
            # Set angular velocity and velocity
            pawn.physics.velocity[:-1] = velocity[:-1]
            pawn.physics.angular = angular
            
        # Store move regardless
        self.moves.add_move(move)        
        
        
class LadderPoint(Actor):
    pass

class LadderBase(LadderPoint):
    obj_name = "LadderBase"
    
class LadderTop(LadderPoint):
    obj_name = "LadderTop"

class FloorMesh(Actor):
    obj_name = "Plane"

class Player(Actor):
    obj_name = "Player"
    
    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy))
    physics = Attribute(
                        PhysicsData(mode=Physics.character, 
                                    position=Vector((0,0, 3))
                                    )
                        )
    
    
    def on_create(self):
        super().on_create()
        
        self.allowed_transitions = [LadderPoint, FloorMesh]
        self.lift_time = 0.0
        
        # Mark as simulated
        simulated(self.on_new_collision)
        simulated(self.on_end_collision)