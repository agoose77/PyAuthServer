import bgui

from bge import logic, events, render
from network import System, InstanceRegister, ConnectionStatus, WorldInfo, keyeddefaultdict
from bge_network import Actor

class UISystem(bgui.System, metaclass=InstanceRegister):
    
    def __init__(self, manager, theme):
        super().__init__(instance_id=None, allow_random_key=True, register=False, theme=theme)

        self.manager = manager
        
        self.active = True
    
    def update(self):
        pass

class UIManager(System):
    
    def __init__(self, game):
        super().__init__()
        
        self.game = game
        self.keymap = {getattr(events, val): getattr(bgui, val) for val in dir(events) if val.endswith('KEY') or val.startswith('PAD')}
        
        logic.getCurrentScene().post_draw.append(self.render_handler)
        
        # Display dimensions
        self._width = render.getWindowWidth()
        self._height = render.getWindowHeight()
        
    @property
    def active_systems(self):
        return (s for s in UISystem if s.active)
    
    def render_handler(self):
        for system in self.active_systems:
            system.render()
    
    def transform_mouse(self, position):
        pos = list(position)
        pos[0] *= self._width
        pos[1] = self._height - (self._height * pos[1])
        return pos
    
    def get_system(self, system_name):
        system_type = UISystem.from_type_name(system_name)
        try:
            return next(s for s in UISystem if isinstance(s, system_type))               
        except StopIteration:
            return system_type(self)
        
    def post_update(self, delta_time):
        """A high-level method to be run every frame"""
        
        # Handle the mouse
        mouse = logic.mouse
        
        pos = self.transform_mouse(mouse.position)
        
        mouse_events = mouse.events
                
        if mouse_events[events.LEFTMOUSE] == logic.KX_INPUT_JUST_ACTIVATED:
            mouse_state = bgui.BGUI_MOUSE_CLICK
        elif mouse_events[events.LEFTMOUSE] == logic.KX_INPUT_JUST_RELEASED:
            mouse_state = bgui.BGUI_MOUSE_RELEASE
        elif mouse_events[events.LEFTMOUSE] == logic.KX_INPUT_ACTIVE:
            mouse_state = bgui.BGUI_MOUSE_ACTIVE
        else:
            mouse_state = bgui.BGUI_MOUSE_NONE
        
        # Handle the keyboard
        keyboard = logic.keyboard
        
        key_events = keyboard.events
        
        is_shifted = key_events[events.LEFTSHIFTKEY] == logic.KX_INPUT_ACTIVE or \
                    key_events[events.RIGHTSHIFTKEY] == logic.KX_INPUT_ACTIVE
        
        just_activated = [self.keymap[key] for key, state in keyboard.active_events.items() if state == logic.KX_INPUT_JUST_ACTIVATED]
        
        # Update all UI systems
        for system in self.active_systems:
        
            system.update_mouse(pos, mouse_state)
            update_keyboard = system.update_keyboard
            
            for keymap in just_activated:
                update_keyboard(keymap, is_shifted)  
            
            system.update()
        
        # Reflect graph updates
        UISystem.update_graph()

class OverlayUI(UISystem):
    
    def __init__(self, manager):
        super().__init__(manager, "")
        
        # Use a frame to store all of our widgets
        self.frame = bgui.Frame(self, 'window', border=0)
        self.frame.colors = [(0, 0, 0, 0) for i in range(4)]
        
        self.labels = keyeddefaultdict(self.new_actor)
        
    def bgui_position(self, actor):
        camera = logic.getCurrentScene().active_camera
        position = list(camera.getScreenPosition(actor.worldPosition))
        position[1] = 1 - position[1]
        return position
    
    def new_actor(self, actor):
        return bgui.Label(parent=self, name='label', text=str(actor.instance_id), pos=self.bgui_position(actor),
                           sub_theme='Large', options = bgui.BGUI_DEFAULT)
        
    def update(self):
        for actor in WorldInfo.subclass_of(Actor):
            label = self.labels[actor]
            
            label.position = self.bgui_position(actor)
            label.text = str(actor.instance_id)

class FindGameUI(UISystem):

    def __init__(self, manager):
        super().__init__(manager, "")
        
        # Use a frame to store all of our widgets
        self.frame = bgui.Frame(self, 'window', border=0)
        self.frame.colors = [(0, 0, 0, 0) for i in range(4)]
        
        # Store connector function
        self.connector = None
        self.matchmaker = None

        # An empty frame
        self.win = bgui.Frame(self, 'win', size=[0.6, 0.8],
            options=bgui.BGUI_DEFAULT|bgui.BGUI_CENTERED)
        
        # A "submit" button
        self.button = bgui.FrameButton(self.win, 'button', text='Join game!', size=[.3, .09], pos=[.815, .03],
            options = bgui.BGUI_DEFAULT)
            
        # IP address input
        self.input = bgui.TextInput(self.win, 'input', "localhost", size=[.4, .04], pos=[.04, 0.02],
            input_options = bgui.BGUI_INPUT_NONE, options = bgui.BGUI_DEFAULT)
        
        # Input handling
        self.input.activate()
        self.input.on_enter_key = self.join_game

        # Submission handling
        self.button.on_click = self.join_game
        self.input.on_click = self.clear_input
        
        self.conn = None
    
    def set_connector(self, connector):
        self.connector = connector
    
    def set_matchmaker(self, matchmaker):
        self.matchmaker = matchmaker
    
    def clear_input(self, widget):
        widget.text = ""
    
    def join_game(self, widget):
        connection = self.input.text, 1200
        self.conn = self.connector(connection)
    
    def update(self):
        if self.conn and self.conn.status == ConnectionStatus.connected:
            self.active = False
          #  self.manager.get_system("OverlayUI")
                       