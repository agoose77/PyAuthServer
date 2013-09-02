import bge
import bgui


CENTERY = bgui.BGUI_DEFAULT|bgui.BGUI_CENTERY
CENTERX = bgui.BGUI_DEFAULT|bgui.BGUI_CENTERX
CENTERED = bgui.BGUI_DEFAULT|bgui.BGUI_CENTERED


class System(bgui.System):

    def __init__(self):
        theme_path = bge.logic.expandPath("//themes")

        super().__init__(theme_path)

        self._subscribers = []
        self._keymap = {getattr(bge.events, val): getattr(bgui, val)
                        for val in dir(bge.events) if (val.endswith('KEY') or \
                               val.startswith('PAD')) and hasattr(bgui, val)}

        bge.logic.getCurrentScene().post_draw.append(self.render)

    def update(self, delta_time):
        # Handle the mouse
        mouse = bge.logic.mouse

        pos = list(mouse.position)
        pos[0] *= bge.render.getWindowWidth()
        pos[1] = bge.render.getWindowHeight() - \
                (bge.render.getWindowHeight() * pos[1])

        mouse_state = bgui.BGUI_MOUSE_NONE
        mouse_events = mouse.events

        if mouse_events[bge.events.LEFTMOUSE] == \
            bge.logic.KX_INPUT_JUST_ACTIVATED:
            mouse_state = bgui.BGUI_MOUSE_CLICK
        elif mouse_events[bge.events.LEFTMOUSE] == \
            bge.logic.KX_INPUT_JUST_RELEASED:
            mouse_state = bgui.BGUI_MOUSE_RELEASE
        elif mouse_events[bge.events.LEFTMOUSE] == \
            bge.logic.KX_INPUT_ACTIVE:
            mouse_state = bgui.BGUI_MOUSE_ACTIVE

        self.update_mouse(pos, mouse_state)

        # Handle the keyboard
        keyboard = bge.logic.keyboard

        key_events = keyboard.events
        is_shifted = key_events[bge.events.LEFTSHIFTKEY] == \
            bge.logic.KX_INPUT_ACTIVE or \
            key_events[bge.events.RIGHTSHIFTKEY] == \
            bge.logic.KX_INPUT_ACTIVE

        for key, state in keyboard.events.items():
            if state == bge.logic.KX_INPUT_JUST_ACTIVATED:
                self.update_keyboard(self._keymap[key], is_shifted)

        visible_panel = False

        for panel_name, panel in self.children.items():

            if panel.visible:
                panel.update(delta_time)
                visible_panel = True

        bge.logic.mouse.visible = visible_panel


class Panel(bgui.Frame):

    def __init__(self, system, name):
        super().__init__(parent=system, name=name, size=[1, 1])

    def update(self, delta_time):
        pass


class ConnectPanel(Panel):

    def __init__(self, system):
        super().__init__(system, "Connect")

        self.connecter = None

        self.center_column = bgui.Frame(parent=self, name="center",
                                        size=[0.8, 0.8], options=CENTERED,
                                        sub_theme="ContentBox")
        self.connect_label = bgui.Label(parent=self.center_column,
                                        name="label", pos=[0.0, 0.90],
                                        text="Connection Wizard",
                                        options=CENTERX, sub_theme="Title")

        # Ip input
        self.connection_row = bgui.Frame(parent=self.center_column,
                                         name="connection_frame",
                                         size=[0.8, 0.1], pos=[0.0, 0.7],
                                         sub_theme="ContentRow",
                                         options=CENTERX)

        self.addr_group = bgui.Frame(parent=self.connection_row,
                                     name="addr_group", size=[0.70, 1.0],
                                     pos=[0.0, 0.5], options=CENTERY,
                                     sub_theme="RowGroup")
        self.port_group = bgui.Frame(parent=self.connection_row,
                                     name="port_group", size=[0.3, 1.0],
                                     pos=[0.7, 0.5], options=CENTERY,
                                     sub_theme="RowGroup")

        self.addr_label = bgui.Label(parent=self.addr_group, name="addr_label",
                                     text="IP Address:", options=CENTERY,
                                     pos=[0.05, 0.0])
        self.port_label = bgui.Label(parent=self.port_group, name="port_label",
                                     text="Port:", options=CENTERY,
                                     pos=[0.05, 0.0])

        self.addr_field = bgui.TextInput(parent=self.addr_group,
                                         name="addr_field", size=[0.6, 1.0],
                                         pos=[0.4, 0.0], options=CENTERY,
                                         text="localhost",
                                         allow_empty=False)
        self.port_field = bgui.TextInput(parent=self.port_group,
                                         name="port_field", size=[0.6, 1.0],
                                         pos=[0.4, 0.0], options=CENTERY,
                                         type=bgui.BGUI_INPUT_INTEGER,
                                         text="1200",
                                         allow_empty=False)

        # Allows input fields to accept input when not hovered
        self.connection_row.is_listener = True

        # Data input
        self.data_row = bgui.Frame(parent=self.center_column,
                                   name="data_frame", size=[0.8, 0.1],
                                   pos=[0.0, 0.5], sub_theme="ContentRow",
                                   options=CENTERX)

        self.connect_group = bgui.Frame(parent=self.data_row,
                                     name="connect_group", size=[0.3, 1.0],
                                     pos=[0.0, 0.5], options=CENTERY,
                                     sub_theme="RowGroup")

        self.connect_button = bgui.FrameButton(parent=self.connect_group,
                                               name="connect_button",
                                               text="Connect", size=[1.0, 1.0],
                                               options=CENTERED)

        self.error_group = bgui.Frame(parent=self.data_row,
                                     name="error_group", size=[0.7, 1.0],
                                     pos=[0.3, 0.5], options=CENTERY,
                                     sub_theme="RowGroup")

        self.connect_message = bgui.Label(parent=self.error_group,
                                          name="connect_status",
                                          text="",
                                          pos=[0.0, 0.0],
                                          options=CENTERED)
        self.connect_button.on_click = self.on_connect

    def on_connect(self, button):
        if not callable(self.connecter):
            return

        self.connecter(self.addr_field.text, int(self.port_field.text))

    def on_error(self, error):
        self.connect_message.text = str(error)

    def update(self, delta_time):
        self.connect_button.frozen = self.port_field.invalid


class BGESystem(System):

    def __init__(self):
        super().__init__()

        self.connect_panel = ConnectPanel(self)
