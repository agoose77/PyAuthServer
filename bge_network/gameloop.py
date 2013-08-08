from bge import logic, events, types

class GameLoop(types.KX_PythonLogicLoop):
    
    def __init__(self):
        print(dir(self))
        self.tick_rate = logic.getLogicTicRate()
        self.use_tick_rate = logic.getUseFrameRate()
        
        self.animation_rate = logic.getAnimationTicRate()
        self.use_animation_rate = logic.getRestrictAnimationUpdates()
        
        self.last_time = self.get_time()
        self.last_animation_time = self.get_time()
        
        self.network = self.create_network()
        self.network_scene = None#logic.getSceneList()[0]
        
        print("Network initialised")
                
    def create_network(self):
        return NotImplemented
        
    def main(self):
        self.__init__()
        while not self.check_quit():
            
            start_time = current_time = self.get_time()
            delta_time = current_time - self.last_time
            print("Tick elapsed")
            
            # If this is too early, skip frame
            if self.use_tick_rate and delta_time < (1 / self.tick_rate):
                continue
            
            for scene in logic.getSceneList():
                current_time = self.get_time()
                print(dir(scene), scene.objects)
                self.get_time()

                if 0:
                    pass
                    
                if 0:
                    self.update_physics(current_time, delta_time)
                    self.update_scenegraph(current_time)
                
                if 0:
                    self.network.send()
                
            # Update IO events from Blender
            self.update_blender()
            print("consider scenes", logic.getSceneList())
            self.get_time()
                
            print("EVents")
            # End of frame updates
            self.update_mouse()
            self.update_keyboard()
            self.update_scenes()
            self.update_render()
            print("profile")
            self.start_profile(logic.KX_ENGINE_DEBUG_OUTSIDE)
            self.last_time = start_time
        
        self.network.stop()
            