from bge_network import Actor, PlayerController, InputManager
from network import WorldInfo, StaticValue, Attribute, RPC, Netmodes, Roles, reliable, simulated, LazyReplicableProxy

from bge import events, logic
from mathutils import Vector, Euler

from time import monotonic
from collections import namedtuple
from functools import wraps

class RacingInputs(InputManager):
    mappings = {"forward": events.WKEY, "back": events.SKEY, "shift": events.MKEY, 'right': events.DKEY, 'left': events.AKEY}

def SafeException(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except Exception as err:
            Exception().__str__()
            print("{} exception suppressed: {}".format(err, err.__traceback__))
    return wrapper

#PlayerMove = namedtuple("PlayerMove", ("timestamp", "deltatime", "inputs"))

class RPGController(PlayerController):
    
    input_class = RacingInputs
    
    def on_create(self):
        super().on_create()
        
        self.correction = None
        
        logic.getCurrentScene().pre_draw.append(self.post_physics)
    
    def calculate_move(self, move):
        """Returns velocity and angular velocity of movement
        @param move: move to execute"""
        move_speed = 10.0 
        rotation_speed = 4.0 
        
        velocity = Vector((0.000, (move.forward - move.back) * move_speed, 0.000))
        angular = Vector((0.000, 0.000, (move.left - move.right) * rotation_speed))
        
        return self.pawn.local_space(velocity), angular
    
    def post_physics(self):
        if self.correction is None and False:
            self.server_check_move()
    
    def player_update(self, delta_time):
        # Make sure we have a pawn object
        
        pawn = self.pawn
        
        if not pawn.registered:
            return

        timestamp = WorldInfo.elapsed
        
        if False:
            move = PlayerMove(timestamp=timestamp, deltatime=delta_time, inputs=self.player_input)
            
            # If no correction
            if self.correction is None:
                velocity, angular = self.calculate_move(move)
                
            else:
                # Start from correction
                pawn.worldPosition = self.correction.position
                pawn.worldOrientation = self.correction.rotation
                
                velocity, angular = self.calculate_move(self.correction.move)
            
            # Set angular velocity
            pawn.worldLinearVelocity = velocity
            pawn.worldAngularVelocity = angular

class RPGController_old(PlayerController):
    
    input_class = RacingInputs
    
    def on_create(self):
        super().on_create()
        
        self.saved_moves = {}
        self.current_move = 0
        
        self.last_timestamp = None
        self.to_correct = None
        
        if WorldInfo.netmode == Netmodes.client:
            logic.getCurrentScene().pre_draw.append(self.process_moves)
    
    def process_move(self, move):
        """Returns velocity and angular velocity of movement
        @param move: move to execute"""
        move_speed = 10.0 
        rotation_speed = 4.0 
        
        velocity = Vector((0.000, (move.forward - move.back) * move_speed, 0.000))
        angular = Vector((0.000, 0.000, (move.left - move.right) * rotation_speed))
        
        return self.pawn.local_space(velocity), angular
    
    def resimulate_from(self, move_id):
        # Cache
        remove_keys = []

        # Get previous timestamp
        move = self.saved_moves[move_id]
        
        timestamp = move.timestamp
        
        update_physics = logic.getCurrentScene().updatePhysics
        
        # Save actors render state (as physics modifies them later)
        for actor in WorldInfo.subclass_of(Actor):
            actor.render_state.save()
        
        # Iterate over moves since this update
        for move_id, move in self.saved_moves.items():
            
            # Remove older moves, and re simulate new ones
            if move.timestamp > timestamp:
                delta_time = move.deltatime
                    
                # Get mov2e
                velocity, angular = self.process_move(move)
                    
                # Apply to object 
                self.pawn.worldLinearVelocity = velocity
                self.pawn.worldAngularVelocity = angular
                
                # Update object
                update_physics(delta_time)
            
            # These are now old moves, we can remove them
            else:
                remove_keys.append(move_id)

        # Remove old moves
        for move_id in remove_keys:
            self.saved_moves.pop(move_id)
        
        # Restore other actor render states
        for actor in WorldInfo.subclass_of(Actor):
            if actor is not self.pawn:
                actor.render_state.restore()
    
    def apply_move(self, move):
        pass
    
    def pre_physics(self, move):
        if self.to_correct is None:
            pass
    
    def process_moves(self):
        # Collect move after physics update
        render_state = self.pawn.render_state
        # Get latest move
        move = self.saved_moves[self.current_move]
        # Update move object
        move = self.saved_moves[self.current_move] = move._replace(velocity=render_state.velocity, angular=render_state.angular, position=render_state.transform.to_translation(), rotation=render_state.transform.to_euler())
        # Ask server to check it
        self.ServerMove(*move)
        
        # Check if any moves need re running
        if self.to_correct is None:
            return
        
        self.resimulate_from(self.to_correct)
    
    @RPC
    def ServerMove(self, move_id: StaticValue(int), timestamp: StaticValue(float), delta_time: StaticValue(float), 
                   forward: StaticValue(bool), back: StaticValue(bool), 
                   left: StaticValue(bool), right: StaticValue(bool), 
                   client_loc: StaticValue(Vector), client_rot: StaticValue(Euler),
                   in_velocity: StaticValue(Vector), 
                   in_angular: StaticValue(Vector)) -> Netmodes.server:        
            
        # Get calculations of inputs
        velocity, angular = self.process_move(Move(move_id, timestamp, delta_time, forward, back, left, right,  None, None, None, None))
        
        # Error margins
        ang_error = vel_error = 0.1
        pos_error = 0.1
        rot_error = 0.1
        
        # Save actors render state (as physics modified them)
        for actor in WorldInfo.subclass_of(Actor):
            actor.render_state.save()
        
        # Update local object data before call update physics
        self.pawn.worldLinearVelocity = velocity
        self.pawn.worldAngularVelocity = angular
        
        # Update physics
        with self.pawn.render_state:
            logic.getCurrentScene().updatePhysics(delta_time)
            
            pos = self.pawn.worldPosition
            vel = self.pawn.worldLinearVelocity
            ang = self.pawn.worldAngularVelocity
            rot = self.pawn.worldOrientation.to_euler()
            print(vel)
        # Restore actor render states
        for actor in WorldInfo.subclass_of(Actor):
            
            if actor is self.pawn:
                # Get errors that are larger than error margins
                errors = ((pos - client_loc).length > pos_error), ((vel - in_velocity).length > vel_error), ((ang - in_angular).length > ang_error) , ((rot.z - client_rot.z) > rot_error)
                not_correct = any(errors)
                
                # Store move for collection
                if not_correct:
                    self.ClientCorrectMove(move_id, vel, ang, pos, rot)
                    
                else:
                    self.ClientAckMove(move_id)
                
                actor.render_state.save()
                
            actor.render_state.restore()
    
    @RPC
    @SafeException
    def ClientAckMove(self, move_id:StaticValue(int))->Netmodes.client:
        self.saved_moves.pop(move_id)
    
    @RPC
    @SafeException
    def ClientCorrectMove(self, move_id: StaticValue(int), velocity: StaticValue(Vector), angular: StaticValue(Vector), location: StaticValue(Vector), rotation: StaticValue(Euler))->Netmodes.client:
        
         # Apply new state
        self.pawn.worldLinearVelocity = velocity
        self.pawn.worldAngularVelocity = angular
        self.pawn.worldPosition = location
        self.pawn.worldOrientation = rotation
       
        # Update object
        update_physics(move.deltatime)

        # Iterate over moves since this update
        for move_id, move in self.saved_moves.items():
            
            # Remove older moves, and re simulate new ones
            if move.timestamp > timestamp:
                delta_time = move.deltatime
                    
                # Get mov2e
                velocity, angular = self.process_move(move)
                    
                # Apply to object 
                self.pawn.worldLinearVelocity = velocity
                self.pawn.worldAngularVelocity = angular
                
                # Update object
                update_physics(delta_time)
            
            # These are now old moves, we can remove them
            else:
                remove_keys.append(move_id)

        # Remove old moves
        for move_id in remove_keys:
            self.saved_moves.pop(move_id)
        
        # Restore other actor render states
        for actor in WorldInfo.subclass_of(Actor):
            if actor is self.pawn:
                actor.render_state.save()
            
            actor.render_state.restore()
    
    @property
    def next_move_id(self):
        self.current_move += 1
        if self.current_move > 255:
            self.current_move = 0
        return self.current_move
    
    def player_update(self, delta_time):
        if not self.pawn.registered:
            return 
        
        timestamp = WorldInfo.elapsed
        inputs = self.player_input
        
        # Read inputs
        forward = inputs.forward.active
        back = inputs.back.active
        left = inputs.left.active
        right = inputs.right.active
        
        # Create move object
        move = Move(self.next_move_id, timestamp, delta_time, forward, back, left, right, None, None, None, None)
        
        # Store for sending
        self.saved_moves[move.id] = move
        
        self.pre_physics(move)
        
        if inputs.shift.active:
            self.shift()

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
    
    def on_create(self):
        super().on_create()
        
        self.allowed_transitions = [LadderPoint, FloorMesh]
        self.lift_time = 0.0
        
        # Mark as simulated
        simulated(self.on_new_collision)
        simulated(self.on_end_collision)
    
    @RPC
    def test(self) ->Netmodes.server:
        print("LOL")
    
    def on_transition(self, last, new):
        return
        if isinstance(last, LadderPoint): 
            self.physics.velocity.zero() 
            
        if new is None:
            self.lift_time = monotonic()
            self.physics.velocity.zero()  
    
    @property
    def time_airbourne(self):
        return monotonic() - self.lift_time
    
    