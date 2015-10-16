from operator import attrgetter


class WMFact:
    __slots__ = 'type', 'data', '_uncertainty_accumulator', 'confidence_period'

    def __init__(self, fact_type):
        self._uncertainty_accumulator = 0.0
        self.confidence_period = 1.0
        self.data = None
        self.type = fact_type

    @property
    def confidence(self):
        confidence = 1 - self._uncertainty_accumulator / self.confidence_period
        return confidence if confidence > 0 else 0

    def __repr__(self):
        return "WMFact<{}>(confidence: {}, data: {})".format(self.type, self.confidence, self.data)


class WorkingMemory:

    def __init__(self):
        self.facts = {}
        self._key = attrgetter("confidence")

    def add_fact(self, fact):
        try:
            facts = self.facts[fact.type]

        except KeyError:
            facts = self.facts[fact.type] = set()

        facts.add(fact)

    def find_single_fact(self, fact_type):
        facts = self.facts[fact_type]
        return max(facts, key=self._key)

    def remove_fact(self, fact):
        facts = self.facts[fact.type]
        facts.remove(fact)

        if not facts:
            del self.facts[fact.type]

    def update(self, delta_time):
        to_remove = []

        for fact_type, facts in self.facts.items():
            for fact in facts:
                # Update confidence of fact
                fact._uncertainty_accumulator += delta_time
                if fact._uncertainty_accumulator > fact.confidence_period:
                    to_remove.append(fact)

        for fact in to_remove:
            self.remove_fact(fact)