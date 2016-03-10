from collections import namedtuple
from collections.abc import Sized, Iterable, Container
from threading import Thread, Event, Lock
from queue import Queue, Empty as EmptyError
from uuid import uuid4
from weakref import WeakKeyDictionary

from network.annotations import get_annotation, set_annotation, AnnotatedMethodFinder
from ..enums import Enum

import socket
import re

_cmd_pat = "^(@(?P<tags>[^ ]*) )?(:(?P<prefix>[^ ]+) +)?(?P<command>[^ ]+)( *(?P<argument> .+))?"
_rfc_1459_command_regexp = re.compile(_cmd_pat)


class SetView(Sized, Iterable, Container):

    def __init__(self, set_):
        self._set = set_

    def __iter__(self):
        return iter(self._set)

    def __contains__(self, item):
        return item in self._set

    def __len__(self):
        return len(self._set)

    def __repr__(self):
        return "{}()".format(self.__class__.__name__, self._set)


class Commands(Enum):
    NICK = "NICK"
    KICK = "KICK"
    PING = "PING"
    NICK_IN_USE = "433"
    ERROR = "ERROR"
    REGISTRATION_SUCCESS = "001"
    PRIVMSG = "PRIVMSG"
    JOIN = "JOIN"
    PART = "PART"


Message = namedtuple("Message", "target sender message")
Response = namedtuple("Response", "tags prefix command params")


class DeferredCall:

    def __init__(self):
        self._calls = []

    def __call__(self, *args, **kwargs):
        self._calls.append((args, kwargs))

    def execute(self, function):
        for args, kwargs in self._calls:
            function(*args, **kwargs)


class DeferredCallableProxy:

    def __init__(self, *method_names):
        self._executors = {n: DeferredCall() for n in method_names}

    def execute(self, instance):
        for method_name, executor in self._executors.items():
            func = getattr(instance, method_name)
            executor.execute(func)

    def __getattr__(self, name):
        try:
            return self._executors[name]

        except KeyError:
            raise AttributeError(name)


class IRCChannel:

    def __init__(self, name):
        self._name = name
        self._client = self._get_call_proxy()
        self._is_joined = False

    @property
    def name(self):
        return self._name

    @property
    def is_joined(self):
        return self._is_joined

    @staticmethod
    def _get_call_proxy():
        return DeferredCallableProxy("say")

    def on_joined(self, client):
        self._client.execute(client)
        self._client = client
        self._is_joined = True

    def on_left(self):
        self._client = self._get_call_proxy()
        self._is_joined = False

    def say(self, message):
        self._client.say(self._name, message)

    def _on_kicked(self, instigator_nick):
        pass

    def _on_message_received(self, sender_nick, message):
        print("Message received in '{}' from '{}': '{}'".format(self._name, sender_nick, message))


_COMMAND_ANNOTATION_NAME = "command_type"
on_command = set_annotation(_COMMAND_ANNOTATION_NAME)
get_command = get_annotation(_COMMAND_ANNOTATION_NAME)

# TODO replace CommandDispatcher with decorator-scraped functions!


class IRCClient(AnnotatedMethodFinder, Thread):
    channel_class = IRCChannel

    def __init__(self):
        super().__init__()

        self._command_queue = Queue()
        self.messages = Queue()

        self.daemon = True

        self.socket = socket.socket()
        self.socket.connect(('irc.freenode.net', 6667))
        self.socket.setblocking(False)

        self._channels = {}
        self._joined_channels = set()

        self._on_registered = []

        self.real_name = "IRCClient"
        self._nickname = None
        self._is_connected = False
        self._is_registered = False

        methods = self.find_annotated_methods(_COMMAND_ANNOTATION_NAME)
        self._handlers = {get_command(f): f for f in methods.values()}


    @property
    def is_registered(self):
        return self._is_registered

    @property
    def is_connected(self):
        return self._is_connected

    @property
    def joined_channels(self):
        return SetView(self._joined_channels)

    @property
    def nickname(self):
        return self._nickname

    @nickname.setter
    def nickname(self, nickname):
        self._enqueue_command("NICK {}".format(nickname), requires_registered=False)

    @staticmethod
    def split_message(data):
        if data.startswith(":"):
            prefix_end_index = data.find(" ")
            prefix = data[1: prefix_end_index]

        else:
            prefix_end_index = -1
            prefix = None

        trailing_start_index = data.find(" :")
        if trailing_start_index != -1:
            trailing = data[trailing_start_index + 2:]

        else:
            trailing = None
            trailing_start_index = len(data)

        command, *params = data[prefix_end_index + 1: trailing_start_index].split(" ")

        if trailing:
            params.append(trailing)

        return prefix, command, params

    # Thread-side interface
    def _send_command(self, msg):
        self.socket.send((msg+"\r\n").encode())

    def run(self):
        self._send_command("USER {0} {0} {0} :{0}".format(self.real_name))

        message_str_buffer = ""

        while True:

            # Send all buffered commands
            while True:
                try:
                    command = self._command_queue.get_nowait()

                except EmptyError:
                    break

                self._send_command(command)

            # Receive all commands
            try:
                message_str_buffer += self.socket.recv(4096).decode()

            except OSError:
                pass

            end_index = message_str_buffer.rfind("\r\n")
            lines = message_str_buffer[:end_index].split("\r\n")
            message_str_buffer = message_str_buffer[end_index:]

            # Receive messages
            for data in lines:
                data = data.strip()

                if not data:
                    continue

                group = _rfc_1459_command_regexp.match(data).group

                tags = group("tags")
                prefix = group("prefix")
                command = group("command")
                argument = group("argument")

                response = Response(tags, prefix, command, argument)
                print(response)

                try:
                    handler = self._handlers[response.command]

                except KeyError:
                    handler = self._default_handler

                handler(response)

    # Client-side interface
    def _enqueue_command(self, command, requires_registered=True):
        if requires_registered and not self.is_registered:
            self._on_registered.append(command)

        else:
            self._command_queue.put_nowait(command)

    def join_channel(self, name):
        if name in self._channels:
            raise ValueError()

        self._enqueue_command("JOIN {}".format(name))

        self._channels[name] = channel = self.__class__.channel_class(name)
        return channel

    def get_channel(self, name):
        return self._channels[name]

    def leave_channel(self, name):
        self._enqueue_command("PART {}".format(name))

    def say(self, channel, message):
        self._enqueue_command("PRIVMSG {} :{}".format(channel, message))

    def quit(self):
        self._enqueue_command("QUIT")

    @on_command(Commands.KICK)
    def _on_kick(self, response):
        data, reason = response.params.split(":", 1)
        channel_name, kicked_nick = data.strip().split()
        sender_nick, sender_info = response.prefix.split("!", 1)

        try:
            channel = self._channels[channel_name]

        except KeyError:
            pass

        self._on_private_message_received(sender_nick, message)

    @on_command(Commands.PING)
    def _on_ping(self, response):
        self._enqueue_command('PONG :{}'.format(response.params))

        if not self._is_connected:
            self._enqueue_command("PRIVMSG R : Login <> MODE {} +x".format(self._nickname))
            self._is_connected = True

    @on_command(Commands.JOIN)
    def _on_join(self, response):
        sender_nick, sender_info = response.prefix.split("!", 1)
        if sender_nick != self._nickname:
            return

        name = response.params.strip()
        channel = self._channels[name]
        channel.on_joined(self)

    @on_command(Commands.PART)
    def _on_part(self, response):
        sender_nick, sender_info = response.prefix.split("!", 1)
        if sender_nick != self._nickname:
            return

        name = response.params.strip()
        channel = self._channels.pop(name)
        channel.on_left()

    @on_command(Commands.PRIVMSG)
    def _on_priv_msg(self, response):
        _channel, message = response.params.split(":", 1)
        channel_name = _channel.strip()

        sender_nick, sender_info = response.prefix.split("!", 1)

        try:
            channel = self._channels[channel_name]

        except KeyError:
            self._on_private_message_received(sender_nick, message)

        else:
            channel._on_message_received(sender_nick, message)

    @on_command(Commands.NICK)
    def _on_set_nick(self, response):
        sender_nick, sender_info = response.prefix.split("!", 1)
        _, new_nick = response.params.rsplit(":", 1)

        if sender_nick == self._nickname:
            self._nickname = new_nick

    @on_command(Commands.NICK_IN_USE)
    def _on_nick_in_use(self, response):
        self.nickname = self._get_random_nickname()

    @on_command(Commands.REGISTRATION_SUCCESS)
    def _on_registered(self, response):
        # SET NICK from params
        _nickname, message = response.params.split(":", 1)
        self._nickname = _nickname.strip()

        # Send pending commands
        for command in self._on_registered:
            self._send_command(command)

        self._on_registered.clear()
        self._is_registered = True

    def _default_handler(self, response):
        pass

    def _get_random_nickname(self):
        return "user" + str(uuid4())[:7]

    def _on_private_message_received(self, sender_nick, message):
        print("Private Message received from '{}': '{}'".format(sender_nick, message))
