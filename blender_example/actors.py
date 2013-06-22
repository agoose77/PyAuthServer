from bge_network import Actor, PlayerController, InputManager, PhysicsData, Physics
from network import WorldInfo, StaticValue, Attribute, RPC, Netmodes, Roles, reliable, simulated, NetmodeOnly, Replicable

from bge import events, logic, render
from mathutils import Vector, Euler

from collections import namedtuple, OrderedDict
from itertools import chain
from math import radians, ceil
from functools import partial
from operator import lt

PlayerMove = namedtuple("PlayerMove", ("timestamp", "deltatime", "inputs"))

def ignore(replicable):
    return replicable.name == "Weapon"

def update_physics_for(obj, deltatime):
    ''' Calls a physics simulation for deltatime
    Rewinds other actors so that the individual is the only one that is changed by the end'''
    for replicable in WorldInfo.subclass_of(Actor):
        if not ignore(replicable):
            replicable.render_state.save()
        
    obj.scene.updatePhysics(deltatime)
    
    for replicable in WorldInfo.subclass_of(Actor):
        if replicable is obj:
            replicable.render_state.save()
        elif not ignore(replicable):
            replicable.render_state.restore()

class Weapon(Actor):
    obj_name = "Weapon"
    
    clip = Attribute(20)
    bullets = Attribute(100)
    
    def on_create(self):
        super().on_create()
        
        # Hertz
        self.fire_rate = 20
        self.range = 10
        self.clip_size = 20
        self.round_damage = 2
        self.automatic = True
        self.sound = "//sounds/sfx_gunshot6.wav"
        self.update_simulated_position = False
        self.last_fired_time = 0
    
    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)
        
        if is_complaint:
            yield "bullets"
            yield "clip"
    
    def fireable(self, timestamp):
        # Assume time validity check handled by movement
        return bool(self.clip) and (timestamp - self.last_fired_time) >= (1/self.fire_rate)
    
    def fired(self, timestamp):
        self.last_fired_time = timestamp
    
    def reload(self):
        needed_refill = self.clip_size - self.clip
        new_clip = min(self.bullets, needed_refill)
        self.bullets -= new_clip
        self.clip += new_clip
    
    def get_fired_bullets(self, deltatime):
        max_bullets = ceil(deltatime * self.fire_rate)
        fired_bullets = min(self.clip, max_bullets)
        return fired_bullets
    
    def fire(self, deltatime):
        fired_bullets = self.get_fired_bullets(deltatime)
        self.clip -= fired_bullets
        
        fire_range = self.range
        ray_cast = self.rayCast
        shoot_rule = WorldInfo.rules.on_shoot
        
        offset = 1.0
        y_axis = self.getAxisVect((0, 1, 0))
        origin = self.physics.position + y_axis * offset
        
        render.drawLine(origin, origin + y_axis*fire_range, [1,0,0])
        
        for shot in range(fired_bullets):
            result = ray_cast(origin + y_axis, origin, fire_range)
                
            if not result:
                continue
            
            if not hasattr(result, "on_shot"):
                continue
            
            shoot_rule(result, self.owner, self.round_damage)

class RPGInputs(InputManager):
    mappings = {"forward": events.WKEY, "back": events.SKEY, "shift": events.MKEY, 'right': events.DKEY, 'left': events.AKEY, 'shoot': events.LEFTMOUSE}

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
    
    def add_move(self, move):
        move_id = self.increment_move()
        self.saved_moves[move_id] = move
    
    def get_move(self, move_id):
        return self.saved_moves[move_id]
    
    def remove_move(self, move_id):
        self.saved_moves.pop(move_id)
        
    def sorted_moves(self, sort_filter=None):
        if callable(sort_filter):
            for k, v in self.saved_moves.items():
                if not sort_filter(k):
                    continue
                yield k, v
        else:
            yield from self.saved_moves.items()
    
class RPGController(PlayerController):
    
    input_class = RPGInputs
    
    def on_create(self):
        super().on_create()
        
        self.moves = MoveManager()
        self.correction = None
        
        self.previous_time = None
        self.last_sent = None
        
        self.delta_threshold = 0.8
        self.considered_error = 0.1
        self.valid_inputs = 0
        self.invalid_inputs = 0
        self.invalid = False
        
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
    
    def play_fire_effects(self, weapon):
        sound = weapon.sound
        self.client_hear_sound(sound, self.pawn.physics.position)
    
    def check_delta_time(self, timestamp, deltatime):
        '''A boolean check that the deltatime we're sent is close to the calculated one
        There will be "differences" so this is crude'''
        current_time = WorldInfo.elapsed
        
        try:
            rough_deltatime = current_time - self.previous_time
        except TypeError:
            return True
        else:
            try:
                error_fraction = (rough_deltatime / deltatime)
            except ZeroDivisionError:
                pass
            else:
                allowed = (1 + self.delta_threshold) > error_fraction > (1 - self.delta_threshold)
                
                if allowed:
                    self.valid_inputs += 1
                else:
                    self.invalid_inputs += 1
                    
                try:
                    logic.getCurrentScene().objects['Empty']['test'] = self.invalid_inputs/self.valid_inputs
                    if (self.invalid_inputs / self.valid_inputs):
                        self.invalid = True
                except ZeroDivisionError:
                    pass
            
        finally:
            self.previous_time = current_time
            
        return True
        
    @RPC
    def server_perform_move(self, move_id: StaticValue(int, max_value=65535), timestamp: StaticValue(float), deltatime: StaticValue(float), inputs: StaticValue(InputManager), position: StaticValue(Vector), orientation: StaticValue(Euler)) -> Netmodes.server:
        allowed = self.check_delta_time(timestamp, deltatime)
        
        if not allowed:
            print("Move delta time invalid")
            return
        
        # Get current pawn object that we control
        pawn = self.pawn
        
        # Perform weapon firing before physics
        if inputs.shoot.active and pawn.weapon:
            if pawn.weapon.fireable(timestamp):
                pawn.weapon.fire(deltatime)
                pawn.weapon.fired(timestamp)
                
        # Create a move to simulate
        move = PlayerMove(timestamp, deltatime, inputs)
        # Determine the velocity and rotation outputs
        pawn.physics.velocity, pawn.physics.angular = self.calculate_move(move)
        # We can't use angular velocity with character physics
        pawn.physics.simulate_angular_velocity(deltatime)
        
        # Set physics
        pawn.physics_to_world()
        # Simulate
        update_physics_for(pawn, deltatime)
        # Apply results
        pawn.world_to_physics()
        
        # Stop bullet simulating this in the normal tick
        pawn.stop_moving()
        
        # Error between server and client
        position_difference = (pawn.physics.position - position).length
        rotation_difference = abs(pawn.physics.orientation.z - orientation.z)
        
        # Margin of error allowed between the two
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
        
        # Get the result of the blender physics operation
        pawn.world_to_physics()

        # If we have no moves we can't re-simulate or send latest move
        if not moves:
            return
        
        # If we have no correction then the latest move is set
        if not self.correction:
            # Get the move ID
            move_id = moves.latest_move
            
            # If we've not sent it before
            if move_id != self.last_sent:
                
                # Get the latest move
                latest_move = moves.get_move(move_id)
                
                # Send move
                self.server_perform_move(move_id, *chain(latest_move, (pawn.physics.position, pawn.physics.orientation)))
                self.last_sent = move_id
        
        # Otherwise we need to simulate the move
        else:
            # Get ID of correction
            correction_id = self.correction[0]
            # Find the successive moves
            following_moves = self.moves.sorted_moves(partial(lt, correction_id))
            # Inform console we're resimulating
            print("Resimulating from {}".format(correction_id))
            
            # Re run all moves
            for replay_id, replay_move in following_moves:
                pawn.physics.velocity, pawn.physics.angular = self.calculate_move(replay_move)
                # We can't use angular velocity with character physics
                pawn.physics.simulate_angular_velocity(replay_move.deltatime)
                # Apply the simulation
                pawn.physics_to_world()
                # Update bullet
                update_physics_for(pawn, replay_move.deltatime)
                # Apply result
                pawn.world_to_physics()
            
            # We didn't send the last one as it needed simulating
            if replay_id != self.last_sent:
                # Tell server about move
                self.server_perform_move(replay_id, *chain(replay_move, (pawn.physics.position, pawn.physics.orientation)))
                self.last_sent = replay_id
            
            # Ensure no velocity could be further simulated by accident
            pawn.stop_moving()
            # Remove the corrected move (no longer needed)
            self.moves.remove_move(correction_id)
            # Empty correction to prevent recorrecting
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
            # Set angular velocity and velocity (keep Z velocity)
            pawn.physics.velocity[:-1] = velocity[:-1]
            pawn.physics.angular = angular
        
        # Play fire effects if can shoot
        if self.player_input.shoot.active and pawn.weapon:
            if pawn.weapon.fireable(timestamp):
    
                fired_bullets = pawn.weapon.get_fired_bullets(delta_time)
                for i in range( fired_bullets):
                    self.play_fire_effects(pawn.weapon)
                pawn.weapon.fired(timestamp)
                
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
    
    health = Attribute(100)
    weapon = Attribute(type_of=Replicable, notify=True)
    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy))
    physics = Attribute(
                        PhysicsData(mode=Physics.character, 
                                    position=Vector((0,0, 3))
                                    )
                        )
    
    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)
        
        if is_complaint:
            yield "weapon"
    
    def on_notify(self, name):
        if name == "weapon":
            weapon = self.weapon
            weapon.setParent(self)
    
    def on_unregistered(self):        
        '''Ensure that the weapon remains in the world'''
        if self.weapon:
            self.weapon.removeParent()
            self.weapon.physics.mode = Physics.rigidbody
            
        super().on_unregistered()
    
    def on_new_collision(self, other):
        if isinstance(other, Weapon):
            
            if WorldInfo.netmode == Netmodes.server:
                self.weapon = other
                
            self.pickup_weapon(other)

    def pickup_weapon(self, weapon):
        weapon.setParent(self)
    
    def on_shot(self, shooter, damage):
        self.health -= damage
        print("shot by {}".format(shooter.name))
        
    def on_create(self):
        super().on_create()
        
        self.allowed_transitions = [LadderPoint, FloorMesh]
        self.lift_time = 0.0
        
        # Mark as simulated
        simulated(self.on_new_collision)
        simulated(self.on_end_collision)