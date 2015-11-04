from collections import namedtuple
from functools import partial
from operator import itemgetter

from .sorted_collection import SortedCollection


class SortedList(SortedCollection):

    append = SortedCollection.insert

    def pop(self):
        first = self[0]
        self.remove(first)
        return first


Node = namedtuple("Node", ("position", "left_child", "right_child", "split_axis"))
FirstSorted = partial(SortedList, key=itemgetter(0))


class RangedKDNeighbours:

    def __init__(self, distance, neighbour_type=FirstSorted):
        self.range_squared = distance ** 2
        self.nearest = self.range_squared, None
        self.neighbours = neighbour_type()

    def add_point(self, distance, node):
        if distance <= self.range_squared:
            self.neighbours.append((distance, node))


class KDNeighbours:
    def __init__(self, requested):
        self.requested = requested
        self.nearest = float("inf"), None
        # If we have KNN we should sort by heap
        self.neighbours = FirstSorted() if requested > 1 else None

    def add_point(self, distance, node):
        if self.requested > 1:
            self.neighbours.append((distance, node))

            if len(self.neighbours) >= self.requested:
                self.nearest = self.neighbours[self.requested - 1]
            return

        if distance < self.nearest[0]:
            self.nearest = distance, node


class KDTree:

    def __init__(self, points, dimensions):
        self.points = points
        self.dimensions = dimensions
        self.root = self.get_root_node(points, dimensions)

    @classmethod
    def get_root_node(cls, points, dimensions, depth=0):
        axis = depth % dimensions

        if not points:
            return

        points.sort(key=itemgetter(axis))
        median = len(points) // 2

        next_depth = depth + 1

        return Node(position=points[median],
                    left_child=cls.get_root_node(points[:median], dimensions, next_depth),
                    right_child=cls.get_root_node(points[median + 1:], dimensions, next_depth),
                    split_axis=axis)

    def __nn_search(self, node, point, results, depth=0):
        results.add_point((point - node.position).length_squared, node)
        if not (node.left_child or node.right_child):
            return

        else:
            axis = node.split_axis
            axis_distance = node.position[axis] - point[axis]

            node_closer, node_farther = (node.left_child, node.right_child) if axis_distance > 0 else (node.right_child, node.left_child)

            if node_closer:
                self.__nn_search(node_closer, point, results, depth + 1)

            if not node_farther:
                return

            if axis_distance ** 2 < results.nearest[0]:
                self.__nn_search(node_farther, point, results, depth + 1)

    def nn_search(self, point, requested=1):
        neighbours = KDNeighbours(requested)
        self.__nn_search(self.root, point, neighbours)
        if neighbours.neighbours is None:
            return neighbours.nearest

        return neighbours.neighbours[:requested]

    def nn_range_search(self, point, distance):
        neighbours = RangedKDNeighbours(distance)
        self.__nn_search(self.root, point, neighbours)
        return neighbours.neighbours