'''
Created by agoose77.
Modified by DonFlymor.
'''
from setuptools import setup

setup(name='network',
      version='2.0.0',
      description="Network package",
      long_description="",
      author='Angus Hollands',
      author_email='goosey15@gmail.com',
      license='MIT',
      packages=['network', 'network.streams', 'network.streams.replication', 'network.serialiser', 'network.annotations', 'network.replication',
       'network.type_serialisers', 'network.utilities'],
      zip_safe=False,
      install_requires=[
          # 'Sphinx',
          # ^^^ Not sure if this is needed on readthedocs.org
          # 'something else?',
          ],
      )
setup(name='bge_game_system',
      version='2.0.0',
      description="BGE network package",
      long_description="",
      author='Angus Hollands',
      author_email='goosey15@gmail.com',
      license='MIT',
      packages=['bge_game_system', 'bge_game_system.entity'],
      zip_safe=False,
      install_requires=[
          # 'Sphinx',
          # ^^^ Not sure if this is needed on readthedocs.org
          # 'something else?',
          ],
      )
setup(name='panda_game_system',
      version='2.0.0',
      description="Panda3D network package",
      long_description="",
      author='Angus Hollands',
      author_email='goosey15@gmail.com',
      license='MIT',
      packages=['panda_game_system'],
      zip_safe=False,
      install_requires=[
          # 'Sphinx',
          # ^^^ Not sure if this is needed on readthedocs.org
          # 'something else?',
          ],
      )
setup(name='game_system',
      version='2.0.0',
      description="Game System package",
      long_description="",
      author='Angus Hollands',
      author_email='goosey15@gmail.com',
      license='TODO',
      packages=['game_system', 'game_system.ai', 'game_system.ai.behaviour', 'game_system.ai.planning', 'game_system.ai.state_machine', 'game_system.chat', 'game_system.chat', 'game_system.entity','game_system.geometry',
                'game_system.latency_compensation', 'game_system.pathfinding', 'game_system.utilities'],
      zip_safe=False,
      install_requires=[
          # 'Sphinx',
          # ^^^ Not sure if this is needed on readthedocs.org
          # 'something else?',
          ],
      )
setup(name='tools',
      version='2.0.0',
      description="Tools package",
      long_description="",
      author='Angus Hollands',
      author_email='goosey15@gmail.com',
      license='TODO',
      packages=['tools'],
      zip_safe=False,
      install_requires=[
          # 'Sphinx',
          # ^^^ Not sure if this is needed on readthedocs.org
          # 'something else?',
          ],
      )
