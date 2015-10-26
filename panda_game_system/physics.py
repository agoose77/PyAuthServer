from panda3d.bullet import BulletWorld, BulletDebugNode
from panda3d.core import loadPrcFileData
loadPrcFileData('', 'bullet-enable-contact-events true')

from direct.showbase.DirectObject import DirectObject

from collections import defaultdict, namedtuple
from functools import partial

from network.utilities import LazyIterable


CollisionContact = namedtuple("CollisionContact", "position normal impulse")
loadPrcFileData('', 'bullet-enable-contact-events true')


class ContactResult:

    def __init__(self, world, body_a, body_b):
        self.world = world

        self.body_a = body_a
        self.body_b = body_b

        self.contacts_a = LazyIterable(partial(self.create_contacts, for_a=True))
        self.contacts_b = LazyIterable(partial(self.create_contacts, for_a=False))

    @property
    def contact_result(self):
        try:
            result = self._contact_result

        except AttributeError:
            self._contact_result = result = self.world.contact_test_pair(self.body_a, self.body_b)

        return result

    def create_contacts(self, for_a):
        """Return collision contacts between two nodes"""
        contacts = []

        if for_a:
            requesting_node = self.body_a

        else:
            requesting_node = self.body_b

        for contact in self.contact_result.get_contacts():
            if contact.get_node0() == requesting_node:
                manifold = contact.get_manifold_point()

                position = manifold.get_position_world_on_a()
                normal = -manifold.get_normal_world_on_b()

            elif contact.get_node1() == requesting_node:
                manifold = contact.get_manifold_point()

                position = manifold.get_position_world_on_b()
                normal = manifold.get_normal_world_on_b()

            impulse = manifold.get_applied_impulse()
            contact_ = CollisionContact(position, normal, impulse)
            contacts.append(contact_)

        return contacts


class PhysicsManager:

    def __init__(self, root_nodepath, world):
        self.world = BulletWorld()
        self.world.setGravity((0, 0, -9.81))

        self._timestep = 1 / world.tick_rate

        # # Seems that this does not function
        # on_contact_added = PythonCallbackObject(self._on_contact_added)
        # self.world.set_contact_added_callback(on_contact_added)
        # on_filter = PythonCallbackObject(self._filter_collision)
        # self.world.set_filter_callback(on_filter)

        self.listener = DirectObject()
        self.listener.accept('bullet-contact-added', self._on_contact_added)
        self.listener.accept('bullet-contact-destroyed', self._on_contact_removed)

        self.tracked_contacts = defaultdict(int)
        self.existing_collisions = set()

        # Debugging info
        debug_node = BulletDebugNode('Debug')
        debug_node.showWireframe(True)
        debug_node.showConstraints(True)
        debug_node.showBoundingBoxes(False)
        debug_node.showNormals(False)

        # Add to world
        self.debug_nodepath = root_nodepath.attachNewNode(debug_node)
        self.world.set_debug_node(debug_node)
        self.debug_nodepath.show()

    def _on_contact_removed(self, node_a, node_b):
        self.tracked_contacts[(node_a, node_b)] -= 1

    def _on_contact_added(self, node_a, node_b):
        self.tracked_contacts[(node_a, node_b)] += 1

    def dispatch_collisions(self):
        # Dispatch collisions
        existing_collisions = self.existing_collisions

        for pair, contact_count in self.tracked_contacts.items():
            # If is new collision
            if contact_count > 0 and pair not in existing_collisions:
                existing_collisions.add(pair)

                # Dispatch collision
                node_a, node_b = pair

                entity_a = node_a.get_python_tag("entity")
                entity_b = node_b.get_python_tag("entity")

                if not (entity_a and entity_b):
                    continue

                contact_result = ContactResult(self.world, node_a, node_b)
                entity_a.messenger.send("collision_started", entity=entity_b, contacts=contact_result.contacts_a)
                entity_b.messenger.send("collision_started", entity=entity_a, contacts=contact_result.contacts_b)

            # Ended collision
            elif contact_count == 0 and pair in existing_collisions:
                existing_collisions.remove(pair)

                # Dispatch collision
                node_a, node_b = pair

                entity_a = node_a.get_python_tag("entity")
                entity_b = node_b.get_python_tag("entity")

                if not (entity_a and entity_b):
                    continue

                entity_a.messenger.send_message("collision_stopped", entity_b)
                entity_b.messenger.send_message("collision_stopped", entity_a)

    def add_entity(self, entity, component):
        body = component.body
        self.world.attach_rigid_body(body)
        body.set_python_tag("entity", entity)

    def remove_entity(self, entity, component):
        body = component.body
        self.world.remove_rigid_body(body)
        body.clear_python_tag("entity")

    def tick(self):
        self.world.do_physics(self._timestep)
        self.dispatch_collisions()