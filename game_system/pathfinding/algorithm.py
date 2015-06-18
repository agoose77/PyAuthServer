from collections import namedtuple
from operator import attrgetter

from ..geometry.utilities import quad_area
from ..coordinates import Vector
from ..iterators import BidirectionalIterator

from .priority_queue import PriorityQueue

from network.iterators import look_ahead

__all__ = "Funnel", "PathNotFoundException", "AlgorithmNotImplementedException", "AStarAlgorithm", "FunnelAlgorithm", \
          "PathfinderAlgorithm"


forward_vector = Vector((0, 1, 0))
EndPortal = namedtuple("EndPortal", ["left", "right"])
BoundVector = type("BoundVector", (Vector,), {"__slots__": "data"})


def manhattan_distance_heuristic(a, b):
    return (b.position - a.position).length_squared


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


class AlgorithmNotImplementedException(Exception):
    pass


class AStarNode:

    g_score = 0
    f_score = 0

    parent = None

    def get_g_score_from(self, other):
        raise NotImplementedError

    def get_h_score_from(self, other):
        raise NotImplementedError


class AStarAlgorithm:

    def __init__(self):
        self.is_admissible = True

    def is_finished(self, goal, current):
        return current is goal

    @staticmethod
    def reconstruct_path(node, goal):
        result = []
        while node:
            result.append(node)
            node = node.parent

        result.reverse()
        return result

    def find_path(self, goal, start=None):
        if start is None:
            start = goal

        if self.is_admissible:
            return self.admissible_find_path(start, goal)

        return self.inadmissible_find_path(start, goal)

    def admissible_find_path(self, start, goal):
        open_set = PriorityQueue(start, key=attrgetter("f_score"))
        closed_set = set()

        is_complete = self.is_finished
        get_heuristic = goal.get_h_score_from
        while open_set:
            current = open_set.pop()
            closed_set.add(current)

            if is_complete(current, goal):
                return self.reconstruct_path(current, goal)

            for neighbor in current.neighbours:
                tentative_g_score = current.g_score + neighbor.get_g_score_from(current)

                tentative_is_better = tentative_g_score < neighbor.g_score
                in_open = neighbor in open_set
                in_closed = neighbor in closed_set

                if in_open and tentative_is_better:
                    open_set.remove(neighbor)

                if not in_open and not in_closed:
                    neighbor.parent = current
                    neighbor.g_score = tentative_g_score
                    neighbor.f_score = tentative_g_score + get_heuristic(neighbor)

                    open_set.add(neighbor)

    def inadmissible_find_path(self, start, goal):
        open_set = PriorityQueue(start, key=attrgetter("f_score"))
        closed_set = set()

        is_complete = self.is_finished
        get_heuristic = goal.get_h_score_from
        while open_set:
            current = open_set.pop()
            closed_set.add(current)

            if is_complete(current, goal):
                return self.reconstruct_path(current, goal)

            for neighbor in current.neighbours:
                tentative_g_score = current.g_score + neighbor.get_g_score_from(current)

                tentative_is_better = tentative_g_score < neighbor.g_score
                in_open = neighbor in open_set
                in_closed = neighbor in closed_set

                if in_open and tentative_is_better:
                    open_set.remove(neighbor)

                if in_closed and tentative_is_better:
                    closed_set.remove(neighbor)

                if not in_open and not in_closed:
                    neighbor.parent = current
                    neighbor.g_score = tentative_g_score
                    neighbor.f_score = tentative_g_score + get_heuristic(neighbor)

                    open_set.add(neighbor)

        raise PathNotFoundException("Couldn't find path for given nodes")


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


class PathfinderAlgorithm:

    def __init__(self, low_fidelity, high_fidelity, spatial_lookup):
        self.low_resolution = low_fidelity
        self.high_resolution = high_fidelity
        self.spatial_lookup = spatial_lookup

    def find_path(self, source, destination, low_resolution=False):
        source_node = self.spatial_lookup(source)
        destination_node = self.spatial_lookup(destination)

        try:
            path_finder = self.low_resolution.find_path

        except AttributeError:
            raise AlgorithmNotImplementedException("Couldn't find low resolution finder algorithm")

        low_resolution_path = path_finder(start=source_node, goal=destination_node)
        if low_resolution:
            return low_resolution_path

        try:
            path_finder = self.high_resolution.find_path

        except AttributeError:
            raise AlgorithmNotImplementedException("Couldn't find high resolution finder algorithm")

        high_resolution_path = path_finder(source, destination, low_resolution_path)
        return high_resolution_path