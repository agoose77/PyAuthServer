PyAuthServer
============

Introduction
There is no substantial networking engine in Blender that allows any kind of multiplayer game project to be realised without writing the underlying network mechanism itself.
Faced with such a challenge, most users would prefer to use another own engine, or remove the feature from the design document. 

This project intends to provide a useful framework for creating multiplayer games which eliminates the headache in writing and maintaining a networked game.

Based upon the Unreal Architecture, this library is statically typed and offers reliable and unreliable (all unordered) transmission of UDP packets. The Serialiser is based upon struct; everything is fixed type that is sent across the network. (In the event that this is undesirable, you could use JSON with a string variable, but this would be inefficient).

User Documentation is currently in development, (see the RTD page for code-specific documentation, or the WIKI for higher level concepts and user guides).

Existing features
--------------
  1. Automatic "replication" of network attributes from client to server
  2. Primitive support for game rules which determine the higher lever game logic.
  3. Automatic "replication" of RPC calls (Function replication for Unreal)
  4. Broadcasting attribute callbacks ("RepNotify" for Unreal)
