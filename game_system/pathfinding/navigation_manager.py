from .algorithm import PathNotFoundException

from ..entities import Actor


class NavigationQuery:
    """Navigation query to destination"""

    def __init__(self, manager, pawn):
        self.manager = manager
        self.pawn = pawn
        self.navmesh = None

        self.replan_if_invalid = False

        self._path = None

        self.replan()

    @property
    def needs_replan(self):
        """Whether path needs replanning"""
        return self._path is None

    @property
    def path(self):
        """Current planned path"""
        return self._path

    def check_plan_is_valid(self):
        """Check if current path is valid"""
        raise NotImplementedError

    def replan(self):
        """Re-plan current path"""
        raise NotImplementedError

    def update(self):
        """Verify or replan existing path"""
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

        return True

    def replan(self):
        """Re-plan current path"""
        source = self.pawn.transform.world_position
        source_node = self.manager.current_node

        destination = self._target

        try:
            self._path = self.navmesh.navmesh.find_path(source, destination, from_node=source_node)

        except PathNotFoundException:
            self._path = None


class ActorNavigationQuery(NavigationQuery):

    def __init__(self, manager, pawn, target):
        self._target = target

        super().__init__(manager, pawn)

        self.replan()

    @property
    def needs_replan(self):
        """Whether current path needs replanning"""
        return self._path is None and self.target_is_valid

    @property
    def target_is_valid(self):
        """Whether target actor is valid (registered)"""
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
        if destination != end_point:
            return False

        return False

    def replan(self):
        """Re-plan current path"""
        path = None

        if self.target_is_valid:
            source = self.pawn.transform.world_position
            destination = self._target.transform.world_position

            source_node = self.manager.current_node

            # Update navmesh
            navmesh = self.navmesh
            if navmesh is None:
                navmesh = self.navmesh = self.pawn.current_navmesh

            # Check that this succeeded
            if navmesh is not None:
                try:
                    path = navmesh.navmesh.find_path(source, destination, from_node=source_node)

                except PathNotFoundException:
                    pass

        self._path = path


class NavigationManager:
    """Handles updating of navigation queries"""

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
        """Update navigation queries"""
        pawn = self.controller.pawn

        if pawn is None:
            self._queries.clear()
            return

        self._update_current_node(pawn)

        for query in self._queries:
            query.update()