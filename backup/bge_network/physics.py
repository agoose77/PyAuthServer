from bge import types
from network import WorldInfo
from functools import partial

def save(replicable, deltatime):
    replicable.render_state.save()

def switch(obj, replicable, deltatime):
    if (replicable in obj.childrenRecursive or replicable == obj):
        replicable.render_state.save()
    else:
        replicable.render_state.restore()

def update_for(obj, deltatime):
    ''' Calls a physics simulation for deltatime
    Rewinds other actors so that the individual is the only one that is changed by the end'''
   
    # Get all children    
    for replicable in WorldInfo.subclass_of(types.KX_GameObject):
        # Start at the parents and traverse
        if not replicable.parent:
            replicable.physics_to_world(post_callback=save, deltatime=deltatime)
            
    # Tick physics
    obj.scene.updatePhysics(deltatime)
    # Create a callback with the obj argument
    switch_cb = partial(switch, obj)
    
    # Restore objects that aren't affiliated with obj
    for replicable in WorldInfo.subclass_of(types.KX_GameObject):
        if not replicable.parent:
            # Apply results
            replicable.world_to_physics(post_callback=switch_cb, deltatime=deltatime)