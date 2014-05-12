import bgui


class Scrollbar(bgui.Widget):
	"""Scrollbar widget.
	
	Use the on_scroll attribute to call a function when the scrollbar is slid.
	
	The slider is the componenet that moves, the slot is the track is lies in."""
	theme_section = 'Scrollbar'
	theme_options = {'SlotColor1', 'SlotColor2', 'SlotColor3', 'SlotColor4',
			'SlotBorderSize', 'SlotBorderColor',
			'SliderColor1', 'SliderColor2', 'SliderColor3', 'SliderColor4',
			'SliderBorderSize', 'SliderBorderColor' }
			
	def __init__(self, parent, name, direction=bgui.BGUI_VERTICAL_SCROLLBAR, aspect=None, size=[1,1],\
			pos=[0,0], sub_theme='', options=bgui.BGUI_DEFAULT):
		"""
		:param parent: the widget's parent
		:param name: the name of the widget
		:param direction: specify whether the scollbar is to run horizontally or vertically
		:param aspect: constrain the widget size to a specified aspect ratio
		:param size: a tuple containing the width and height
		:param pos: a tuple containing the x and y position
		:param sub_theme: name of a sub_theme defined in the theme file (similar to CSS classes)
		:param options: various other options

		"""
		bgui.Widget.__init__(self, parent, name, aspect, size, pos, sub_theme, options)
		
		self._slot = bgui.Frame(self, name+'_slot', pos=[0,0], size=self.size, options=bgui.BGUI_NONE)
		self._slot.on_click = self._jump_to_point
		
		self._slider = bgui.Frame(self._slot, name+'_slider', pos=[0,0], size=self.size, options=bgui.BGUI_NONE)
		self._slider.on_click = self._begin_scroll
		
		if self.theme:
			self._slot.colors = [
					[float(i) for i in self.theme.get(self.theme_section, 'SlotColor1').split(',')],
					[float(i) for i in self.theme.get(self.theme_section, 'SlotColor2').split(',')],
					[float(i) for i in self.theme.get(self.theme_section, 'SlotColor3').split(',')],
					[float(i) for i in self.theme.get(self.theme_section, 'SlotColor4').split(',')],
					]
					
			self._slider.colors = [
					[float(i) for i in self.theme.get(self.theme_section, 'SliderColor1').split(',')],
					[float(i) for i in self.theme.get(self.theme_section, 'SliderColor2').split(',')],
					[float(i) for i in self.theme.get(self.theme_section, 'SliderColor3').split(',')],
					[float(i) for i in self.theme.get(self.theme_section, 'SliderColor4').split(',')],
					]
					
			self._slot.border_color = [float(i) for i in self.theme.get(self.theme_section, 'SlotBorderColor').split(',')]
			self._slider.border_color = [float(i) for i in self.theme.get(self.theme_section, 'SliderBorderColor').split(',')]
			self._slot.border = float(self.theme.get(self.theme_section, 'SlotBorderSize'))
			self._slot.border = float(self.theme.get(self.theme_section, 'SliderBorderSize'))
			
		else:
			self._slot.colors = [[0.3, 0.3, 0.3, 1.0]] * 4
			self._slider.colors = [[0.4, 0.4, 0.4, 1.0]] * 4
			
			self._slot.border = self._slider.border = 0
			self._slot.border_color = self._slider.border_color = (0.0, 0.0, 0.0, 1.0)
		
		self.direction = direction
		self.is_being_scrolled = False
		self._jump = False
		self._scroll_offset = 0 # how many pixels from the bottom of the slider scrolling started at
		self._change = 0 # how many pixels the slider has moved since last frame
		
		self._on_scroll = None # callback for when the slider is moving
	
	@property
	def normalized_slider_position(self):
		return (self.slider_position - self.position[self.direction]) / (self.size[self.direction] - self.slider_size)
	
	@normalized_slider_position.setter
	def normalized_slider_position(self, pos):
		self.slider_position = pos * (1 - (self.slider_size / self.size[self.direction]))
	
	@property
	def change(self):
		"""The number of pixels the slider has moved since the last frame."""
		return self._change
		
	@change.setter
	def change(self, change):
		self._change = change
		
	@property
	def on_scroll(self):
		"""Callback while the slider is being slid."""
		return self._on_scroll
		
	@on_scroll.setter
	def on_scroll(self, on_scroll):
		self._on_scroll = on_scroll
		
	@property
	def slider_size(self):
		"""The width or height of the slider, depending on whether it is a horizontal or VERTICAL scrollbar"""
		if self.direction == bgui.BGUI_HORIZONTAL_SCROLLBAR:
			return self._slider.size[0]
		elif self.direction == bgui.BGUI_VERTICAL_SCROLLBAR:
			return self._slider.size[1]
		
	@slider_size.setter
	def slider_size(self, size):
		if self.direction == bgui.BGUI_HORIZONTAL_SCROLLBAR:
			if self.options & bgui.BGUI_NORMALIZED:
				size *= self.size[0]
			self._slider.size = [min(self.size[0], size), self.size[1]]
			
		elif self.direction == bgui.BGUI_VERTICAL_SCROLLBAR:
			if self.options & bgui.BGUI_NORMALIZED:
				size *= self.size[1]
			
			self._slider.size = [self.size[0], min(self.size[1], size)]
		
	@property
	def slider_position(self):
		"""Sets the x or y coordinate of the slider, depending on whether it is a horizontal or VERTICAL scrollbar"""
		if self.direction == bgui.BGUI_HORIZONTAL_SCROLLBAR:
			return self._slider.position[0]
		elif self.direction == bgui.BGUI_VERTICAL_SCROLLBAR:
			return self._slider.position[1]
		
	@slider_position.setter
	def slider_position(self, pos):
		if self.direction == bgui.BGUI_HORIZONTAL_SCROLLBAR:
			if self.options & bgui.BGUI_NORMALIZED:
				pos *= self.size[0]
			self._slider.position = [min(self.size[0], max(0, pos)), 0]
			
		elif self.direction == bgui.BGUI_VERTICAL_SCROLLBAR:
			if self.options & bgui.BGUI_NORMALIZED:
				pos *= self.size[1]
				
			self._slider.position = [0, min(self.size[1], max(0, pos))]
		
	def _jump_to_point(self, widget):
		# called when the slot is clicked on
		if not self.is_being_scrolled:
			self._jump = True
			self.is_being_scrolled = True
		
	def _begin_scroll(self, widget):
		# called when the slider is clicked on
		self.is_being_scrolled = True
		if self.direction == bgui.BGUI_HORIZONTAL_SCROLLBAR:
			self._scroll_offset = self.system.cursor_pos[0] - self._slider.position[0]
		elif self.direction == bgui.BGUI_VERTICAL_SCROLLBAR:
			self._scroll_offset = self.system.cursor_pos[1] - self._slider.position[1]
		
	def _draw(self):
		# jump the slider (when clicking on the slot)
		if self._jump and not self.is_being_scrolled:
			if self.direction == bgui.BGUI_HORIZONTAL_SCROLLBAR:
				self.slider_position = (self.system.cursor_pos[0]-self.slider_size)/(1 - (1+self.size[0] * bool(self.options & bgui.BGUI_NORMALIZED)))
			elif self.direction == bgui.BGUI_VERTICAL_SCROLLBAR:
				self.slider_position = (self.system.cursor_pos[1]-self.slider_size)/(1 - (1+self.size[1] * bool(self.options & bgui.BGUI_NORMALIZED)))
		self._jump = False
		
		# update scrolling
		if self.is_being_scrolled:
			if self.system.click_state not in [bgui.BGUI_MOUSE_CLICK, bgui.BGUI_MOUSE_ACTIVE]:
				self.is_being_scrolled = False
			else:
				if self.direction == bgui.BGUI_HORIZONTAL_SCROLLBAR:
					if int(max(self.position[0]+self._scroll_offset, min(self.position[0]+self.size[0]+self._scroll_offset, \
							int(self.system.cursor_pos[0])))) != int(self._slider.position[0]+self._scroll_offset):
						self.change = self._slider.position[0]
						self._slider.position = [min(self.size[0]-self._slider.size[0], max(0, self.system.cursor_pos[0]-self.position[0]-self._scroll_offset)), 0]
						self.change -= self._slider.position[0]
						if self.on_scroll:
							self.on_scroll(self)
					else:
						self.change = 0
						
				elif self.direction == bgui.BGUI_VERTICAL_SCROLLBAR:
					if int(max(self.position[1]+self._scroll_offset, min(self.position[1]+self.size[1]+self._scroll_offset, \
							int(self.system.cursor_pos[1])))) != int(self._slider.position[1]+self._scroll_offset):
						self.change = self._slider.position[1]
						self._slider.position = [0, min(self.size[1]-self._slider.size[1], max(0, self.system.cursor_pos[1]-self.position[1]-self._scroll_offset))]
						self.change -= self._slider.position[1]
						if self.on_scroll:
							self.on_scroll(self)
					else:
						self.change = 0
		else:
			self.change = 0
		
		bgui.Widget._draw(self)