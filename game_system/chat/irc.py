from threading import Thread
from queue import Queue, Empty as EmptyError
from uuid import uuid4
import socket


class IRCChannel:

    def __init__(self, irc_client, name):
        self.irc_client = irc_client
        self.name = name

        self.on_message = None

    def join(self):
        self.irc_client.enqueue_command("JOIN {}".format(self.name))

    def leave(self):
        self.irc_client.enqueue_command("PART {}".format(self.name))

    def say(self, message):
        self.irc_client.enqueue_command("PRIVMSG %s :%s" % (self.name, message))

    def _on_message(self, message, sender):
        if callable(self.on_message):
            self.on_message(message, sender)


class IRCClient(Thread):
    connected = False

    def __init__(self):
        super().__init__()

        self.command_queue = Queue()
        self.response_queue = Queue()

        self.realname = "IRCClient"
        self._nickname = None
        self._is_registered = False
        self.daemon = True

        self.socket = socket.socket()
        self.socket.connect(('irc.freenode.net', 6667))
        self.socket.setblocking(False)

        self.channels = {}

        self.on_message = None
        self.on_private_message = None
        self.on_reply = None
        self.on_quit = None
        self.on_nickname_in_use = None
        self.on_registered = None

        self.when_registered = []

    @property
    def is_registered(self):
        return self._is_registered

    @property
    def nickname(self):
        return self._nickname

    @nickname.setter
    def nickname(self, nickname):
        self.enqueue_command("NICK {}".format(nickname), requires_registered=False)
        self._nickname = nickname

    # Thread-side interface
    def _send_command(self, msg):
        self.socket.send((msg+"\r\n").encode())

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

    def run(self):
        self._send_command("USER {0} {0} {0} :{0}".format(self.realname))

        message_str_buffer = ""

        while True:
            # Send all buffered commands
            while True:
                try:
                    command = self.command_queue.get_nowait()

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

                prefix, command, params = self.split_message(data)

                response = dict(prefix=prefix, command=command, params=params)
                self.response_queue.put(response)

    # Client-side interface
    def enqueue_command(self, command, requires_registered=True):
        if requires_registered and not self.is_registered:
            self.when_registered.append(command)

        else:
            self.command_queue.put_nowait(command)

    def join_channel(self, name):
        channel = self.channels[name] = IRCChannel(self, name)
        channel.join()
        return channel

    def quit(self):
        self.enqueue_command("QUIT")

    def receive_messages(self):
        while True:
            try:
                response = self.response_queue.get_nowait()

            except EmptyError:
                return

            prefix = response['prefix']
            command = response['command']
            params = response['params']

            if prefix is None:
                sender_nick = None

            else:
                sender_nick = prefix.split("!")[0]

            # server ping/pong?
            if command == "PING":
                self.enqueue_command('PONG :{}'.format(params[0]))

                if not self.connected:
                    self.enqueue_command("PRIVMSG R : Login <> MODE {} +x".format(self.nickname))
                    self.connected = True

            elif command == 'PRIVMSG':
                target, message = params

                if target in self.channels:
                    channel = self.channels[target]

                    channel._on_message(message, sender_nick)

                if target == self.nickname:
                    self._on_private_message(message, sender_nick)

                elif self.nickname in message:
                    self._on_reply(message, sender_nick)

                else:
                    self._on_message(message, sender_nick)

            elif command == "ERROR":
                self._on_quit()

            elif command == "433":
                self._on_nickname_in_use()

            elif command == "001":
                self._on_registered()

            else:
                print(response)

    def say(self, message, target):
        self.enqueue_command("PRIVMSG %s :%s" % (target, message))

    def _on_registered(self):
        # Send pending commands
        for command in self.when_registered:
            self._send_command(command)
        self.when_registered.clear()

        self._is_registered = True

        if callable(self.on_registered):
            self.on_registered()

    def _on_quit(self):
        self.channels.clear()
        self.connected = False

        if callable(self.on_quit):
            self.on_quit()

    def _on_reply(self, message, sender):
        if callable(self.on_reply):
            self.on_reply(message, sender)

    def _on_private_message(self, message, sender):
        if callable(self.on_private_message):
            self.on_private_message(message, sender)

    def _on_message(self, message, sender):
        if callable(self.on_message):
            self.on_message(message, sender)

    def _on_nickname_in_use(self):
        self._nickname = None

        if callable(self.on_nickname_in_use):
            self.on_nickname_in_use()

        else:
            random_nickname = "user" + str(uuid4())[:7]
            self.nickname = random_nickname

# TODO support users lookup etc, reconnect