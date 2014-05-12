from bgl import *
from bge import texture
import aud

from .widget import Widget, BGUI_DEFAULT
from .image import Image


class ImageRender(Image):
	"""Widget for displaying ImageRender images"""

	def __init__(self, parent, name, source, aspect=None, size=[1, 1], pos=[0, 0],
				sub_theme='', options=BGUI_DEFAULT):
		"""
		:param parent: the widget's parent
		:param name: the name of the widget
		:param source: ImageSource to use for the widget
		:param aspect: constrain the widget size to a specified aspect ratio
		:param size: a tuple containing the width and height
		:param pos: a tuple containing the x and y position
		:param sub_theme: name of a sub_theme defined in the theme file (similar to CSS classes)
		:param options: various other options

		"""

		Image.__init__(self, parent=parent, name=name, img=None, aspect=aspect, size=size, pos=pos, sub_theme=sub_theme, options=options)

		# Bind and load the texture data
		glBindTexture(GL_TEXTURE_2D, self.tex_id)
				
		im_buf = source.image

		if im_buf:
			# Setup some parameters
			glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
			glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)

			glTexEnvf(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE)

			# Upload the texture data
			glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, source.size[0], source.size[1],
							0, GL_RGBA, GL_UNSIGNED_BYTE, im_buf)
		else:
			print("Unable to load the source:", source)
			
		# Store the source for later
		self.source = source
		self.source.capsize = int(self.size[0]), int(self.size[1])
		
	@property
	def size(self):
		return super().size
	
	@size.setter
	def size(self, value):
		Image.size.__set__(self, value)
		self.source.capsize = int(self.size[0]), int(self.size[1])
	
	def _cleanup(self):
		# Set self.source to None to force sourceFFmpeg() to be deleted and free
		# its source data.
		self.source = None
		Image._cleanup(self)

	def update_image(self, img):
		"""This does nothing on a source widget"""

		# This breaks the Liskov substitution principle, but I think the way to solve
		# that is to change the Image interface a bit to avoid the problem.

		Image.update_image(self, None)

	def _draw(self):
		"""Draws the source frame"""

		# Upload the next frame to the graphics
		im_buf = self.source.image

		if im_buf:
			glBindTexture(GL_TEXTURE_2D, self.tex_id)
			glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, self.source.size[0], self.source.size[1],
							0, GL_RGBA, GL_UNSIGNED_BYTE, im_buf)
					
		# Draw the textured quad
		Image._draw(self)

		# Invalidate the image
		self.source.refresh()
