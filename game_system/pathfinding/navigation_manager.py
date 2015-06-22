from .algorithm import PathNotFoundException

from ..entities import Actor


class NavigationQuery:
    """Navigation query to destination"""

    def __init__(self, manager, pawn):
        self.manager = manager
        self.pawn = pawn

        self.replan_if_invalid = False

        self._path = None

        self.replan()

    @property
    def needs_replan(self):
        return self._path is None

    @property
    def path(self):
        return self._path

    def check_plan_is_valid(self):
        """Check if current path is valid"""
        raise NotImplementedError

    def replan(self):
        """Re-plan current path"""
        raise NotImplementedError

    def update(self):
        # Update path state
        if not self.check_plan_is_valid():
            self._path = None

        if self.needs_replan and self.replan_if_invalid:
            self.replan()


class PointNavigationQuery(NavigationQuery):

    def __init__(self, manager, pawn, target):
        self._target = target

        super().__init__(manager, pawn)

        self.replan()

    def check_plan_is_valid(self):
        """Return integrity of current plan"""
        path = self._path

        # If we have no path
        if path is None:
            return False

        # Get current navmesh
        navmesh = self.pawn.current_navmesh
        if navmesh is not None:
            return True

        return False

    def replan(self):
        """Re-plan current path"""
        path = None

        source = self.pawn.transform.world_position
        source_node = self.manager.current_node

        destination = self._target

        navmesh = self.pawn.current_navmesh
        if navmesh is not None:
            try:
                path = navmesh.navmesh.find_path(source, destination, from_node=source_node)

            except PathNotFoundException:
                pass

        self._path = path


class ActorNavigationQuery(NavigationQuery):

    def __init__(self, manager, pawn, target):
        self._target = target

        super().__init__(manager, pawn)

        self.replan()

    @property
    def needs_replan(self):
        return self._path is None and self.target_is_valid

    @property
    def target_is_valid(self):
        return self._target.registered

    def check_plan_is_valid(self):
        """Return integrity of current plan"""
        path = self.path

        # If we have no path
        if path is None:
            return False

        # Get targe position
        if not self.target_is_valid:
            return False

        destination = self._target.transform.world_position

        # If target hasn't moved
        end_point = path.points[-1]
        if destination == end_point:
            return True

        # Get current navmesh
        navmesh = self.pawn.current_navmesh
        if navmesh is None:
            return False

        # If the target is in the same final node
        end_node = path.nodes[-1]
        if navmesh.navmesh.find_nearest_node(destination) is end_node:
            return True

        return False

    def replan(self):
        """Re-plan current path"""
        path = None

        if self.target_is_valid:
            source = self.pawn.transform.world_position
            source_node = self.manager.current_node

            destination = self._target.transform.world_position

            navmesh = self.pawn.current_navmesh
            if navmesh is not None:
                try:
                    path = navmesh.navmesh.find_path(source, destination, from_node=source_node)

                except PathNotFoundException:
                    pass

        self._path = path


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

        if isinstance(destination, Actor):
            query = ActorNavigationQuery(self, pawn, destination)

        else:
            query = PointNavigationQuery(self, pawn, destination)

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