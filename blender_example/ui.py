import bge
import bgui

from bgl import *

from os import path, listdir

from collections import OrderedDict
from network import SignalListener
from bge_network import UIRenderSignal, UIUpdateSignal
from math import ceil

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


class System(SignalListener, bgui.System):

    def __init__(self):
        theme_path = bge.logic.expandPath("//themes")
        super().__init__(theme_path)

        self.register_signals()
        self.scene = bge.logic.getCurrentScene()

        self._subscribers = []
        self._keymap = {getattr(bge.events, val): getattr(bgui, val) for val in dir(bge.events) if (val.endswith('KEY')
                        or val.startswith('PAD')) and hasattr(bgui, val)}

    render = UIRenderSignal.global_listener(bgui.System.render)

    @UIUpdateSignal.global_listener
    def update(self, delta_time):
        # Handle the mouse
        mouse = bge.logic.mouse

        pos = list(mouse.position)
        pos[0] *= bge.render.getWindowWidth()
        pos[1] = bge.render.getWindowHeight() - \
                (bge.render.getWindowHeight() * pos[1])

        mouse_state = bgui.BGUI_MOUSE_NONE
        mouse_events = mouse.events

        if mouse_events[bge.events.LEFTMOUSE] == bge.logic.KX_INPUT_JUST_ACTIVATED:
            mouse_state = bgui.BGUI_MOUSE_CLICK
        elif mouse_events[bge.events.LEFTMOUSE] == bge.logic.KX_INPUT_JUST_RELEASED:
            mouse_state = bgui.BGUI_MOUSE_RELEASE
        elif mouse_events[bge.events.LEFTMOUSE] == bge.logic.KX_INPUT_ACTIVE:
            mouse_state = bgui.BGUI_MOUSE_ACTIVE

        self.update_mouse(pos, mouse_state)

        # Handle the keyboard
        keyboard = bge.logic.keyboard

        key_events = keyboard.events
        is_shifted = key_events[bge.events.LEFTSHIFTKEY] == bge.logic.KX_INPUT_ACTIVE or \
                     key_events[bge.events.RIGHTSHIFTKEY] == bge.logic.KX_INPUT_ACTIVE

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
        super().__init__(parent=system, name=name, size=[1, 1], options=CENTERED)

        self.register_signals()
        self.uses_mouse = False

    def update(self, delta_time):
        pass


class Graph(bgui.Frame):
    """Graph widget"""
    theme_section = 'Graph'
    theme_options = {
                'Color1': (0, 0, 0, 0.5),
                'Color2': (0, 0, 0, 0),
                'Color3': (0, 0, 0, 0),
                'Color4': (0, 0, 0, 0),
                'BorderSize': 1,
                'BorderColor': (0, 0, 0, 1),
                }

    def __init__(self, parent, name, border=None, aspect=None, size=[1,1], pos=[0,0], sub_theme='',
                 options=bgui.BGUI_DEFAULT, resolution=1.0, scale=None, length=1.0):
        """
        :param parent: the widget's parent
        :param name: the name of the widget
        :param aspect: constrain the widget size to a specified aspect ratio
        :param size: a tuple containing the width and height
        :param pos: a tuple containing the x and y position
        :param sub_theme: name of a sub_theme defined in the theme file (similar to CSS classes)
        :param options: various other options

        """
        super().__init__(parent, name, border, aspect, size, pos, sub_theme, options)

        self._scale = scale
        self._resolution = resolution
        self._length = length

        self._points = []
        self._frame_time = 0.0
        self._start_height = 0

    @property
    def scale(self):
        if self._points and self._scale is None:
            return ceil(max((y_value for y_value, _ in self._points)))
        return self._scale

    @scale.setter
    def scale(self, scale):
        self._scale = scale

    @property
    def length(self):
        return self._length

    @length.setter
    def length(self, length):
        self._length = length

    @property
    def resolution(self):
        return self._resolution

    @resolution.setter
    def resolution(self, resolution):
        self._resolution = resolution

    def add_vertex(self, vertex, delta_time):
        self._points.append((vertex, delta_time))
        self._frame_time += delta_time

    def remove_vertex(self):
        point, delta_time = self._points.pop(0)
        self._frame_time -= delta_time
        self._start_height = point

    def update_scrolling(self):
        while self._points and (self._frame_time - self._points[0][1]) > self._length:
            self.remove_vertex()

    def plot(self, vertex, delta_time):
        self.add_vertex(vertex, delta_time)
        self.update_scrolling()

    def _draw_frame(self):
        # Enable alpha blending
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        # Enable polygon offset
        glEnable(GL_POLYGON_OFFSET_FILL)
        glPolygonOffset(1.0, 1.0)

        glBegin(GL_QUADS)
        for i in range(4):
            glColor4f(self.colors[i][0], self.colors[i][1], self.colors[i][2], self.colors[i][3])
            glVertex2f(self.gl_position[i][0], self.gl_position[i][1])
        glEnd()

        glDisable(GL_POLYGON_OFFSET_FILL)

    def _get_straddling_points(self, time):
        total_frame_time = 0.0
        previous_frame = None
        frame = None

        for point, delta_time in self._points:
            frame = point, total_frame_time
            if total_frame_time >= time:
                return previous_frame, frame

            previous_frame = point, total_frame_time
            total_frame_time += delta_time

    def _draw_points(self):
        glColor4f(1,1,1,1)
        glBegin(GL_LINE_STRIP)

        x_size, y_size = self._size
        x_pos, y_pos = self._position
        window_time = self.length
        scale_factor = self.scale

        if not self._points:
            return

        glVertex2f(x_pos, min(self._start_height / scale_factor, 1) * y_size + y_pos)

        steps = round(x_size * self.resolution)

        for step in range(steps):
            x_i_pos = round(step / self.resolution)
            time = (x_i_pos / x_size) * window_time

            result = self._get_straddling_points(time)

            if result is None:
                continue

            previous_frame, next_frame = result

            if previous_frame is None:
                continue

            next_y_coordinate, next_time = next_frame
            previous_y_coordinate, previous_time = previous_frame

            time_difference = next_time - previous_time
            time_to_step = time - previous_time
            position_difference = next_y_coordinate - previous_y_coordinate

            lerp_y_factor = (time_to_step / time_difference)
            lerp_y_value = previous_y_coordinate + position_difference * lerp_y_factor

            lerp_y_scaled = min(lerp_y_value / scale_factor, 0.98) * y_size

            glVertex2f(x_i_pos + x_pos, y_pos + lerp_y_scaled)

        glEnd()

    def _draw_border(self):
        r, g, b, a = self.border_color
        glColor4f(r, g, b, a)
        glPolygonMode(GL_FRONT, GL_LINE)
        glLineWidth(self.border)

        glBegin(GL_QUADS)
        for i in range(4):
            glVertex2f(self.gl_position[i][0], self.gl_position[i][1])

        glEnd()

        glLineWidth(1.0)
        glPolygonMode(GL_FRONT, GL_FILL)

    def _draw(self):
        """Draw the frame"""
        self._draw_frame()
        self._draw_points()
        if self.border > 0:
            self._draw_border()

        bgui.Widget._draw(self)
