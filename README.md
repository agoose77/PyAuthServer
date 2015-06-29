PyAuthServer
============

Introduction
--------------
There is no substantial authoritative networking library in Python that allows any kind of multiplayer game project to be realised without writing the underlying network mechanism itself.
Faced with such a challenge, most developers would choose to use another engine (with built-in multiplayer), or remove the feature from the design document. 

This project intends to provide a useful Python framework which eliminates the headache in writing and maintaining a networked game. It is designed to be supported by different game engines, with an abstract game layer for gameplay code. Anything in the network library is pure python, and the `XXX_game_system` is for engine-specific bindings code. There should not be any engine-specific code in `game_system`.

User Documentation is currently in development, (see the [ReadTheDocs page](http://pyauthserver.readthedocs.org/en/latest/) for code-specific documentation, or the WIKI for higher level concepts and user guides).

Existing features
--------------

Based upon the Unreal Architecture, this library is statically typed and offers reliable and unreliable (all unordered) transmission of UDP packets. The Serialiser is based upon struct; everything is fixed type that is sent across the network. (In the event that this is undesirable, you could use JSON with a string variable, but this would be inefficient).

  1. Automatic "replication" of network attributes from client to server
  2. Primitive support for game rules which determine the higher lever game logic.
  3. Automatic "replication" of RPC calls (Function replication for Unreal)
  4. Broadcasting attribute callbacks (RepNotify for Unreal)
