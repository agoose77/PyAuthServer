PyAuthServer
============

Introduction
--------------
There is no substantial networking engine in Python for Blender that allows any kind of multiplayer game project to be realised without writing the underlying network mechanism itself.
Faced with such a challenge, most users would prefer to use another own engine, or remove the feature from the design document. 

This project intends to provide a useful Python framework for creating multiplayer games which eliminates the headache in writing and maintaining a networked game. It does not require the Blender Game Engine, but certain parts of the system must be realised by writing a new engine interface. Anything in the network library is pure python, and the `bge_game_system` is for BGE code. With the exception of mathutils (which is used in game_system, but aliased in the coordinates module for easy replacement), there should not be any BGE specific code in `game_system`.
The `example_game` module should only make use of BGE interfaces from `bge_game_system`.

Based upon the Unreal Architecture, this library is statically typed and offers reliable and unreliable (all unordered) transmission of UDP packets. The Serialiser is based upon struct; everything is fixed type that is sent across the network. (In the event that this is undesirable, you could use JSON with a string variable, but this would be inefficient).

User Documentation is currently in development, (see the RTD page for code-specific documentation, or the WIKI for higher level concepts and user guides).

Existing features
--------------
  1. Automatic "replication" of network attributes from client to server
  2. Primitive support for game rules which determine the higher lever game logic.
  3. Automatic "replication" of RPC calls (Function replication for Unreal)
  4. Broadcasting attribute callbacks ("RepNotify" for Unreal)
