import sys #used to get commandline arguments
import re #used for regular expressions

__all__  = ["exists"]


def exists(hostname):
    """ str -> bool
    The exists function opens the host file and checks to see if the hostname requested exists in the host file.
    It opens the host file, reads the lines, and then a for loop checks each line to see if the hostname is in it.
    If it is, True is returned. If not, False is returned.
    :param hostname:
    :return:
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