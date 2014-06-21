from network.replicable import Replicable
from network.enums import Netmodes
from network.decorators import requires_netmode
from network.descriptors import TypeFlag
from network.world_info import WorldInfo
from network.logger import Logger
from network.structures import factory_dict

from collections import OrderedDict

TICK_FLAG = TypeFlag(int, max_value=WorldInfo._MAXIMUM_TICK)


__all__ = ["NetworkLocksMixin"]


class NetworkLocksMixin(Replicable):
    """Network Interface for managed variables"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.locks = set()
        self.buffered_locks = factory_dict(dict, dict_type=OrderedDict, provide_key=False)

    @requires_netmode(Netmodes.server)
    def is_locked(self, name):
        """Determine if a server lock exists with a given name

        :param name: name of lock to test for
        :rtype: bool
        """
        return name in self.locks

    def server_add_buffered_lock(self, move_id: TICK_FLAG, name: TypeFlag(str)) -> Netmodes.server:
        """Add a named lock on the server with respect for the artificial latency

        :param move_id: move ID that corresponds with the command creation time
        :param name: name of lock to set
        """
        self.buffered_locks[move_id][name] = True

    def server_add_lock(self, name: TypeFlag(str)) -> Netmodes.server:
        """Add a named lock on the server

        :param name: name of lock to set
        """
        self.locks.add(name)

    def server_remove_buffered_lock(self, move_id: TICK_FLAG, name: TypeFlag(str)) -> Netmodes.server:
        """Remove a named lock on the server with respect for the artificial latency

        :param move_id: move ID that corresponds with the command creation time
        :param name: name of lock to unset
        """
        self.buffered_locks[move_id][name] = False

    def server_remove_lock(self, name: TypeFlag(str)) -> Netmodes.server:
        """Remove a named lock on the server

        :param name: name of lock to unset
        """
        try:
            self.locks.remove(name)

        except KeyError as err:
            Logger.exception("{} was not locked".format(name))

    def update_buffered_locks(self, move_id):
        """Apply server lock changes according to their creation time

        :param move_id: ID of move to process locks for
        """
        removed_keys = []
        for lock_origin_id, locks in self.buffered_locks.items():
            if lock_origin_id > move_id:
                break

            for lock_name, add_lock in locks.items():
                if add_lock:
                    self.server_add_lock(lock_name)

                else:
                    self.server_remove_lock(lock_name)

            removed_keys.append(lock_origin_id)

        for key in removed_keys:
            self.buffered_locks.pop(key)

