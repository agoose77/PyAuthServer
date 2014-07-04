import sys #used to get commandline arguments
import re #used for regular expressions

__all__ = ["exists"]


def exists(hostname):
    """Open the host file and check to see if the hostname requested exists in the host file.

    :param hostname: name of host
    """
    if 'linux' in sys.platform:
        filename = '/etc/hosts'

    else:
        filename = 'c:\windows\system32\drivers\etc\hosts'

    with open(filename, 'r') as hosts:
        for item in hosts:

            if hostname in item:
                return True

    return False