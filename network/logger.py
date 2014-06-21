from logging import Formatter, getLogger, INFO, DEBUG, StreamHandler

__all__ = ['Logger']


Logger = getLogger("network")

Logger.info("Initialised logger")

_handler = StreamHandler()
_handler.setLevel(INFO)
# create formatter and add it to the handlers
formatter = Formatter('%(levelname)s - [%(asctime)s - %(name)s] {%(message)s\}')
_handler.setFormatter(formatter)

Logger.addHandler(_handler)