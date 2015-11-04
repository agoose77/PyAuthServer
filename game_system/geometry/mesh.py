__all__ = ["IVertex", "IMesh", "IPolygon"]


class IVertex:

    @property
    def polygons(self):
        raise NotImplementedError()

    @property
    def position(self):
        raise NotImplementedError()

    @position.setter
    def position(self, value):
        raise NotImplementedError()

    @property
    def normal(self):
        raise NotImplementedError()

    @normal.setter
    def normal(self, value):
        raise NotImplementedError()

    @property
    def colour(self):
        raise NotImplementedError()

    @colour.setter
    def colour(self, value):
        raise NotImplementedError()

    @property
    def uv(self):
        raise NotImplementedError()

    @uv.setter
    def uv(self, value):
        raise NotImplementedError()


class IPolygon:

    @property
    def area(self):
        raise NotImplemented()

    def get_neighbours(self, shared_vertices):
        raise NotImplementedError()

    @property
    def vertices(self):
        raise NotImplementedError()

    @property
    def normal(self):
        raise NotImplementedError()

    @property
    def position(self):
        raise NotImplementedError()

    @position.setter
    def position(self, value):
        raise NotImplementedError()


class IMesh:

    @property
    def vertices(self):
        raise NotImplementedError()

    @property
    def polygons(self):
        raise NotImplementedError()
