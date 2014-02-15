import bge
import bgui

from os import path, listdir

from collections import OrderedDict
from network import SignalListener

CENTERY = bgui.BGUI_DEFAULT | bgui.BGUI_CENTERY
CENTERX = bgui.BGUI_DEFAULT | bgui.BGUI_CENTERX
CENTERED = bgui.BGUI_DEFAULT | bgui.BGUI_CENTERED


class ConsoleRenderer(bgui.ListBoxRenderer):
    def __init__(self, listbox):
        super().__init__(listbox)

        self.label.color = 0, 0, 0, 1


class TableRenderer(bgui.ListBoxRenderer):

    def __init__(self, listbox, labels=[],
                 theming={}, pt_size=None):
        super().__init__(listbox)

        self.listbox = listbox

        self.frame = bgui.Frame(listbox, "frame", size=[1, 1], pos=[0, 0])

        self.labels = OrderedDict()
        self.frames = OrderedDict()

        total = len(labels)

        for index, name in enumerate(labels):
            frame_pos = [(index / total), 0.0]
            label_pos = [0.0, 0.3]

            frame = bgui.Frame(self.frame, "{}_frame".format(name),
                                size=[1 / total, 1],
                                pos=list(frame_pos),
                                sub_theme="TableEntryFrame")
            label = bgui.Label(parent=frame, name="{}_label".format(name),
                               pos=list(label_pos), pt_size=pt_size,
                               sub_theme="TableEntryLabel",
                               options=bgui.BGUI_DEFAULT | bgui.BGUI_CENTERED,
                               font=theming.get("Font"))

            self.frames[name] = frame
            self.labels[name] = label

        self.theming = theming

    def render_item(self, collection):

        if collection == self.listbox.selected:
            self.frame.colors = [self.theming.get("Selected", (0, 0, 0, 0.5))
                                 for i in range(4)]

        else:
            self.frame.colors = [self.theming.get("Deselected", (0, 0, 0, 0))
                                 for i in range(4)]

        for (name, item) in collection:

            if name in self.labels:
                self.labels[name].text = str(item)

        return self.frame


class System(bgui.System, SignalListener):

    def __init__(self):
        theme_path = bge.logic.expandPath("//themes")
        super().__init__(theme_path)

        self.scene = bge.logic.getCurrentScene()

        self._subscribers = []
        self._keymap = {getattr(bge.events, val): getattr(bgui, val)
                        for val in dir(bge.events) if (val.endswith('KEY') or \
                               val.startswith('PAD')) and hasattr(bgui, val)}

        self.scene.post_draw.append(self.render)

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

        mouse_required = False

        for panel in self.children.values():

            if panel.visible:
                panel.update(delta_time)
                if panel.uses_mouse:
                    mouse_required = True

        bge.logic.mouse.visible = mouse_required


class SpriteSequence(bgui.Image):

    def __init__(self, *args, length, loop=False, frame_index=0, **kwargs):
        # Create internal image
        super().__init__(*args, **kwargs)

        self.length = length
        self.loop = loop
        self.frame = frame_index

    @property
    def frame(self):
        return self._index

    @frame.setter
    def frame(self, index):
        x_size = 1 / self.length
        if not 0 <= index < self.length:
            raise IndexError("Frame not found")

        self._index = index
        self.texco = [[x_size * index, 0], [x_size * (index + 1), 0],
                      [x_size * (index + 1), 1], [x_size * index, 1]]

    def next_frame(self):
        try:
            self.frame += 1

        except IndexError:
            self.frame = 0 if self.loop else -1

    def previous_frame(self):
        try:
            self.frame -= 1

        except IndexError:
            self.frame = -1 if self.loop else 0


class ImageSequence(SpriteSequence):

    def __init__(self, parent, name, source, *args, **kwargs):
        self._source = source
        self._images = []

        self.update_images()

        # Create internal image
        super().__init__(parent, name, "", *args, **kwargs)

    def update_images(self):
        tail, head = path.split(self._source)
        self._images = sorted(n for n in listdir(tail)
                           if n.startswith(head)
                           )

    @property
    def frame(self):
        return super().frame

    @frame.setter
    def frame(self, index):
        try:
            source = self._images[index]

        except IndexError as err:
            raise IndexError("Could not find image with this index") from err

        self.update_image(source)


class Panel(SignalListener, bgui.Frame):

    def __init__(self, system, name):
        super().__init__(parent=system, name=name,
                         size=[1, 1], options=CENTERED)

        self.uses_mouse = False

    def update(self, delta_time):
        pass
