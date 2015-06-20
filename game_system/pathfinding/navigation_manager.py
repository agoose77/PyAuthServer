from .algorithm import PathNotFoundException

from ..entities import Actor


class NavigationQuery:
    """Navigation query to destination"""

    def __init__(self, manager, pawn, destination):
        self.manager = manager
        self.pawn = pawn

        self._destination = destination
        self._is_actor = isinstance(destination, Actor)
        self._is_valid = False

        self.replan_if_invalid = False
        self.path = self._find_path()

    @property
    def origin(self):
        return self.pawn.transform.world_position

    @property
    def destination(self):
        """Return destination point"""
        if self._is_actor:
            return self._destination.transform.world_position

        return self._destination

    @property
    def is_valid(self):
        """Return path state"""
        return self._is_valid

    def _find_path(self):
        """Find new path from pawn position to destination"""
        source = self.origin
        source_node = self.manager.current_node

        destination = self.destination

        navmesh = self.pawn.current_navmesh
        if navmesh is None:
            return None

        try:
            return navmesh.navmesh.find_path(source, destination, from_node=source_node)

        except PathNotFoundException:
            return None

    def _get_is_valid(self):
        """Check if current path is valid"""
        path = self.path

        # If we have no path
        if path is None:
            return False

        destination = self.destination

        # If target hasn't moved
        *_, end_point = path.points
        if destination == end_point:
            return True

        # Get current navmesh
        navmesh = self.pawn.current_navmesh
        if navmesh is None:
            return False

        # If the target is in the same final node
        *_, end_node = path.nodes
        if navmesh.navmesh.find_nearest_node(destination) is end_node:
            return True

        return False

    def replan(self):
        """Re-plan current path"""
        self.path = self._find_path()

        if self.path:
            self._is_valid = True

    def update(self):
        # Update path state
        self._is_valid = self._get_is_valid()

        if not self._is_valid and self.replan_if_invalid:
            self.replan()


class NavigationManager:

    def __init__(self, controller):
        self.controller = controller
        self.current_node = None

        self._queries = set()

    def create_query(self, destination):
        """Create navigation plan query

        :param destination: destination actor / point
        """
        pawn = self.controller.pawn
        if not pawn:
            raise ValueError("{} does not have valid pawn")

        query = NavigationQuery(self, pawn, destination)
        self._queries.add(query)

        return query

    def remove_query(self, query):
        self._queries.remove(query)

    def _update_current_node(self, pawn):
        """Update current tracked node of pawn.

        More efficient than simply searching all nodes

        :param pawn: controller pawn
        """
        navmesh = pawn.current_navmesh
        if navmesh is None:
            return

        current_node = self.current_node
        pawn_position = pawn.transform.world_position

        if current_node:
            # If the node is now invalid
            if pawn_position not in current_node:
                for node in current_node.neighbours:
                    if pawn_position in node:
                        self.current_node = node
                        return

            else:
                return

        self.current_node = navmesh.navmesh.find_nearest_node(pawn_position)

    def update(self):
        pawn = self.controller.pawn

        if pawn is None:
            self._queries.clear()
            return

        self._update_current_node(pawn)

        for query in self._queries:
            query.update()