from direct.showbase import ShowBase

from panda3d.bullet import BulletRigidBodyNode, BulletBoxShape
from panda3d.core import NodePath, Filename


bam_path = Filename.fromOsSpecific("D:\\PycharmProjects\\PyAuthServer\\demos\\test_panda\\data\\TestActor\\Cube.bam")
base = ShowBase.ShowBase()


def save():
    model = loader.loadModel(Filename.fromOsSpecific("D:/PycharmProjects/PyAuthServer/demos/test_panda/data/TestActor/Cube.egg"))

    bullet_node = BulletRigidBodyNode("BulletCube")
    bullet_nodepath = NodePath(bullet_node)

    shape = BulletBoxShape((1, 1, 1))
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