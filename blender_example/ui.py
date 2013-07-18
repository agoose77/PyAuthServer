import bgui

from bge import logic, events, render
from network import System, InstanceRegister, ConnectionStatus, WorldInfo, keyeddefaultdict
from bge_network import Actor
from actors import Player
from collections import OrderedDict

def local_path(path):
    return logic.expandPath('//') + path

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
        self.keymap = {getattr(events, val): getattr(bgui, val, None) for val in dir(events) if val.endswith('KEY') or val.startswith('PAD')}
                
        # Display dimensions
        self._width = render.getWindowWidth()
        self._height = render.getWindowHeight()
        
    @property
    def active_systems(self):
        return (s for s in UISystem if s.active)
    
    def post_physics(self, deltatime):
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
        super().__init__(manager, local_path("themes/default"))
        
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
        for actor in WorldInfo.subclass_of(Player):
            label = self.labels[actor]            
            label.position = self.bgui_position(actor)
            label.text = str(actor.instance_id)

class TableRenderer(bgui.ListBoxRenderer):
    
    def __init__(self, parent, listbox, item_size=[.1, .1], label_data=OrderedDict(), theming={}):
        super().__init__(listbox)
        
        self.listbox = listbox
        
        self.frame = bgui.Frame(listbox, "frame", size=item_size)
        
        self.labels = OrderedDict()
        self.frames = OrderedDict()
        
        for name, data in label_data.items():
            frame_pos = data.get("frame_pos", [0.0, 0.0])
            
            frame = bgui.Frame(self.frame, "{}_frame".format(name), size=data.get("size", [0.5, 0.1]), pos=frame_pos, sub_theme="TableFrame")
            label = bgui.Label(parent=frame, name="{}_label".format(name), pos=data.get("label_pos", [0.0, 0.3]), sub_theme="TableEntry", options=bgui.BGUI_DEFAULT)
            
            self.frames[name] = frame
            self.labels[name] = label
                
        self.theming = theming
        
    def render_item(self, collection):
        
        if collection == self.listbox.selected:
            self.frame.colors = [self.theming.get("selected", (0, 0, 0, 0.5)) for i in range(4)]
        else:
            self.frame.colors = [self.theming.get("deselected", (0, 0, 0, 0)) for i in range(4)]
                    
        for (name, item) in collection:
            self.labels[name].text = str(item)            
            
        return self.frame

class FindGameUI(UISystem):

    def __init__(self, manager):
        super().__init__(manager, local_path("themes/default"))
        
        # Use a frame to store all of our widgets
        self.frame = bgui.Frame(self, 'window', border=0)
        self.frame.colors = [(0, 0, 0, 0.0) for i in range(4)]
        
        # Store connector function
        self.connector = None
        self.matchmaker = None

        # An empty frame
        self.win = bgui.Frame(self, 'win', size=[0.6, 0.8],
            options=bgui.BGUI_DEFAULT|bgui.BGUI_CENTERED)
        
        self.loading_frame = bgui.Frame(self, 'loading_frame', size=[0.5, 0.2], pos=[0.5, 0.5],  options=bgui.BGUI_DEFAULT|bgui.BGUI_CENTERED, sub_theme="Loading")
        self.loading_label = bgui.Label(parent=self.loading_frame, name="loading_label", pos=[0, 0], text="Loading ...", sub_theme="Large", options=bgui.BGUI_DEFAULT|bgui.BGUI_CENTERED)
        self.loading_frame.visible = False
        
        # Create empty server data
        self.server_data = []
        self.connection_data = {}
        
        self.setup_frame_info = OrderedDict(map=dict(frame_pos=[0.01, 0.15]), players=dict(frame_pos=[0.5, 0.15]), ping=dict(frame_pos=[0.85, 0.15]))
                
        self.game_info = bgui.ListBox(self.frame, "info", items=self.server_data, padding=0.05, size=[0.65, 0.9], pos=[0.2, 0.00])
        self.game_info.renderer = TableRenderer(self, self.game_info, item_size=[1, 0.05], label_data=self.setup_frame_info)
        
        self.title = bgui.Label(parent=self, name='label', text="Server list", pos=[0.45, 0.92],
                                sub_theme='Large', options = bgui.BGUI_DEFAULT)
        
        # A UI button
        self.refresh = bgui.FrameButton(self.win, 'find', text='Refresh', size=[.2, .07], pos=[.0, .03],
            options = bgui.BGUI_DEFAULT)
            
        # IP address input
        self.input = bgui.TextInput(self.win, 'input', "", size=[.4, .07], pos=[.45, 0.03],
            input_options = bgui.BGUI_INPUT_NONE, options = bgui.BGUI_DEFAULT)
        
        # A "submit" button
        self.submit = bgui.FrameButton(self.win, 'button', text='Join game!', size=[.2, .07], pos=[.85, .03],
            options = bgui.BGUI_DEFAULT)
        
        # Input handling
        self.input.activate()
        self.input.on_enter_key = self.join_game

        # Submission handling
        self.submit.on_click = self.join_game
        self.refresh.on_click = self.refresh_games
        self.game_info.on_click = self.store_ip
        self.input.on_click = self.clear_input
        
        self.conn = None
        self.selected_ip = None
    
    def set_connector(self, connector):
        self.connector = connector
    
    def set_matchmaker(self, matchmaker):
        self.matchmaker = matchmaker
    
    def clear_input(self, widget):
        widget.text = ""
    
    def store_ip(self, widget):
        selected = widget.selected
        
        if selected:
            self.selected_ip = self.connection_data[selected]
    
    def refresh_games(self, widget=None):
        if self.game_info.height < 0.3:
            return
        
        new_data = self.matchmaker.find_games()
       
        for game_address, game_data in new_data.items():
            
            data = tuple((k, game_data[k]) for k in self.game_info.renderer.labels)
            self.server_data.append(data)
            
            self.connection_data[data] = game_address
        self.game_info.items = self.server_data
        
    
    def join_game(self, widget):
        if not self.input.text:
            ip_address = self.selected_ip
            if ip_address is None:
                return
        else:
            ip_address = self.input.text
            
        connection = ip_address, 1200
        self.conn = self.connector(connection)
        self.loading_frame.visible = True
    
    def update(self):
        if self.conn and self.conn.status == ConnectionStatus.connected:
            self.active = False
            self.manager.get_system("OverlayUI")
                       