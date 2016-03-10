from functools import lru_cache

from .conditions import is_annotatable, has_annotation


class AnnotatedMethodFinder:
    """Find bound methods with named annotation"""

    @classmethod
    @lru_cache()
    def _find_unbound_methods_matching(cls, annotation):
        methods = {}

        is_match = has_annotation(annotation)
        for name, value in cls.__dict__.items():
            if not is_annotatable(value):
                continue

            if is_match(value):
                methods[name] = value

        return methods

    def find_annotated_methods(self, annotation):
        return {name: value.__get__(self) for name, value in self._find_unbound_methods_matching(annotation).items()}