from setuptools import setup

for name in "network", "game_system", "bge_game_system", "demos":
      setup(name=name,
            version='1.0.1',
            description="{} package".format(name.title()),
            long_description="",
            author='Angus Hollands',
            author_email='goosey15@gmail.com',
            license='MIT',
            packages=[name],
            zip_safe=False,
            install_requires=[]
      )