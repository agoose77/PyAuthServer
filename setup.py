from setuptools import setup

setup(name='network',
      version='1.0.1',
      description="Network package",
      long_description="",
      author='Angus Hollands',
      author_email='goosey15@gmail.com',
      license='MIT',
      packages=['network', 'network.serialiser', 'network.metaclasses', 'network.metaclasses.mapping',
                'network.metaclasses.register', 'network.streams', 'network.signals'],
      zip_safe=False,
      install_requires=[
          # 'Sphinx',
          # ^^^ Not sure if this is needed on readthedocs.org
          # 'something else?',
          ],
      )
setup(name='bge_game_system',
      version='1.0.1',
      description="BGE network package",
      long_description="",
      author='Angus Hollands',
      author_email='goosey15@gmail.com',
      license='MIT',
      packages=['bge_game_system', 'bge_game_system.geometry', 'bge_game_system.geometry.mesh'],
      zip_safe=False,
      install_requires=[
          # 'Sphinx',
          # ^^^ Not sure if this is needed on readthedocs.org
          # 'something else?',
          ],
      )
setup(name='panda_game_system',
      version='1.0.1',
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
      version='1.0.1',
      description="Game System package",
      long_description="",
      author='Angus Hollands',
      author_email='goosey15@gmail.com',
      license='TODO',
      packages=['game_system', 'game_system.chat', 'game_system.ai', 'game_system.ai.behaviour', 'game_system.geometry',
                'game_system.ai.planning', 'game_system.ai.state_machine', 'game_system.latency_compensation',
                'game_system.pathfinding'],
      zip_safe=False,
      install_requires=[
          # 'Sphinx',
          # ^^^ Not sure if this is needed on readthedocs.org
          # 'something else?',
          ],
      )
setup(name='demos',
      version='1.0.1',
      description="Demo package",
      long_description="",
      author='Angus Hollands',
      author_email='goosey15@gmail.com',
      license='TODO',
      packages=['demos', 'demos.example_utilities', 'demos.example_utilities.remote_debugging'],
      zip_safe=False,
      install_requires=[
          # 'Sphinx',
          # ^^^ Not sure if this is needed on readthedocs.org
          # 'something else?',
          ],
      )