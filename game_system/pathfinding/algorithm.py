from collections import namedtuple

from game_system.utilities import BidirectionalIterator, PriorityQueue
from ..geometry.utilities import quad_area
from ..coordinates import Vector
from network.utilities import look_ahead

__all__ = "Funnel", "PathNotFoundException", "AStarAlgorithm", "FunnelAlgorithm", "NavmeshAStarAlgorithm"


forward_vector = Vector((0, 1, 0))
EndPortal = namedtuple("EndPortal", ["left", "right"])


class Funnel:
    __slots__ = "left", "right", "_apex", "_apex_callback"

    def __init__(self, apex, left, right, on_apex_changed):
        self.left = left
        self.right = right
        self._apex = apex
        self._apex_callback = on_apex_changed

    @property
    def apex(self):
        return self._apex

    @apex.setter
    def apex(self, value):
        self._apex = value
        self._apex_callback(value)

    def update(self, portals):
        portals = BidirectionalIterator(portals)
        left_index = right_index = portals.index

        # Increment index and then return entry at index
        for portal in portals:
            # Check if left is inside of left margin
            if quad_area(self.apex, self.left, portal.left) >= 0.0:
                # Check if left is inside of right margin or
                # we haven't got a proper funnel
                if self.apex == self.left or (quad_area(self.apex, self.right, portal.left) < 0.0):
                    # Narrow funnel
                    self.left = portal.left
                    left_index = portals.index

                else:
                    # Otherwise add apex to path
                    self.left = self.apex = self.right
                    # Set portal to consider from the corner we pivoted around
                    # This index is incremented by the for loop
                    portals.index = right_index
                    continue

            # Check if right is inside of right margin
            if quad_area(self.apex, self.right, portal.right) <= 0.0:
                # Check if right is inside of left margin or
                # we haven't got a proper funnel
                if self.apex == self.right or (quad_area(self.apex, self.left, portal.right) > 0.0):
                    # Narrow funnel
                    self.right = portal.right
                    right_index = portals.index

                else:
                    # Otherwise add apex to path
                    self.right = self.apex = self.left
                    # Set portal to consider from the corner we pivoted around
                    # This index is incremented by the for loop
                    portals.index = left_index
                    continue


class PathNotFoundException(Exception):
    pass


class AStarAlgorithm:

    def __init__(self):
        self.is_admissible = True

    def is_finished(self, goal, current, path):
        return current is goal

    @staticmethod
    def reconstruct_path(node, path, reverse_path=True):
        """Reconstruct path from parent tree

        :param node: final node
        :param goal: goal node
        """
        result = []

        try:
            while True:
                result.append(node)
                node = path[node]

        except KeyError:
            pass

        if reverse_path:
            result.reverse()

        return result

    def find_path(self, goal, start=None):
        if start is None:
            start = goal

        if self.is_admissible:
            return self.admissible_find_path(start, goal)

        return self.inadmissible_find_path(start, goal)

    def get_neighbours(self, node):
        raise NotImplementedError

    def get_g_score(self, node, neighbour):
        raise NotImplementedError

    def get_h_score(self, node, goal):
        raise NotImplementedError

    def admissible_find_path(self, start, goal):
        open_set = PriorityQueue()
        open_set.add(start, 0)

        closed_set = set()

        is_complete = self.is_finished

        get_g_score = self.get_g_score
        get_h_score = self.get_h_score

        f_scores = {start: 0}
        g_scores = {start: 0}
        path = {}

        while open_set:
            current = open_set.pop()
            closed_set.add(current)

            if is_complete(current, goal, path):
                reverse_path = start is not goal
                return self.reconstruct_path(current, path, reverse_path)

            for neighbour in self.get_neighbours(current):
                if neighbour in closed_set:
                    continue

                tentative_g_score = g_scores[current] + get_g_score(current, neighbour)

                in_open_set = neighbour in open_set
                if in_open_set and tentative_g_score < g_scores[neighbour]:
                    open_set.remove(neighbour)
                    in_open_set = False

                if not in_open_set:
                    path[neighbour] = current

                    f_score = tentative_g_score + get_h_score(neighbour, goal)

                    g_scores[neighbour] = tentative_g_score
                    f_scores[neighbour] = f_score

                    open_set.add(neighbour, f_score)

        raise PathNotFoundException("Couldn't find path for given nodes")

    def inadmissible_find_path(self, start, goal):
        open_set = PriorityQueue()
        open_set.add(start, 0)

        closed_set = set()

        is_complete = self.is_finished

        get_g_score = self.get_g_score
        get_h_score = self.get_h_score

        f_scores = {start: 0}
        g_scores = {start: 0}
        path = {}

        while open_set:
            current = open_set.pop()
            closed_set.add(current)

            if is_complete(current, goal):
                reverse_path = start is not goal
                return self.reconstruct_path(current, path, reverse_path)

            for neighbour in self.get_neighbours(current):
                tentative_g_score = g_scores[current] + get_g_score(current, neighbour)

                if neighbour in g_scores and tentative_g_score < g_scores[neighbour]:
                    if neighbour in open_set:
                        open_set.remove(neighbour)

                    if neighbour in closed_set:
                        closed_set.remove(neighbour)

                if not (neighbour in closed_set or neighbour in open_set):
                    path[neighbour] = current

                    f_score = tentative_g_score + get_h_score(neighbour, goal)

                    g_scores[neighbour] = tentative_g_score
                    f_scores[neighbour] = f_score

                    open_set.add(neighbour, f_score)

        raise PathNotFoundException("Couldn't find path for given nodes")


class NavmeshAStarAlgorithm(AStarAlgorithm):

    def get_neighbours(self, node):
        return node.neighbours

    def get_g_score(self, node, neighbour):
        return (neighbour.position - node.position).length

    def get_h_score(self, node, goal):
        return (goal.position - node.position).length


class FunnelAlgorithm:

    def find_path(self, source, destination, nodes):
        path = [source]

        # Account for main path
        portals = [source.get_portal_to(destination) for source, destination in look_ahead(nodes)]
        portals.append(EndPortal(destination, destination))

        funnel = Funnel(source, source, source, path.append)
        funnel.update(portals)

        # Account for last destination point
        if funnel is None:
            return []

        path.append(destination)
        return path


class NavigationPath:

    __slots__ = "points", "nodes"

    def __init__(self, points, nodes):
        self.points = points
        self.nodes = nodes
