import bge


class Context:
    @property
    def scene(self):
        return bge.logic.getCurrentScene()

    @property
    def object(self):
        return self.controller.owner

    @property
    def controller(self):
        return bge.logic.getCurrentController()


def logic_add_object(name, hook=None, life=0):
    if hook is None:
        hook = bge.context.object

    return bge.context.scene.addObject(name, hook, life)

bge.context = Context()
bge.logic.addObject = logic_add_object
