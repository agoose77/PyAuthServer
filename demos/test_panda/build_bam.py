from direct.showbase import ShowBase

from panda3d.bullet import BulletRigidBodyNode, BulletBoxShape, BulletPlaneShape
from panda3d.core import NodePath, Filename


fp = "D:/Users/Angus/Documents/PyCharmProjects/PyAuthServer/demos/test_panda/data/TestActor"
from os import path

bam_path = Filename.fromOsSpecific(path.join(fp, "Cube.bam"))
base = ShowBase.ShowBase()


def save():
    f = Filename.fromOsSpecific(path.join(fp, "Cube.egg"))
    model = loader.loadModel(f)

    bullet_node = BulletRigidBodyNode("BulletPlane")
    bullet_nodepath = NodePath(bullet_node)

    shape = BulletRigidBodyNode((1, 1, 1), 0)
    bullet_node.addShape(shape)
    bullet_node.setMass(1.0)

    model.reparentTo(bullet_nodepath)
    bullet_nodepath.writeBamFile(bam_path)
    bullet_nodepath.ls()


def find_bullet_parent(node):
    while node.getParent():
        node = node.getParent()
        if isinstance(node.node(), BulletRigidBodyNode):
            return node


def load():
    print("LOAD")
    model = loader.loadModel(bam_path)
    model.ls()

op = input("w")
if op == "s":
    save()
elif op == "l":
    load()

base.run()