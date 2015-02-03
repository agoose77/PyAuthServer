.. PyAuthServer documentation master file, created by
   sphinx-quickstart on Mon Feb  2 15:19:23 2015.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to PyAuthServer's documentation!
========================================
  "There is no substantial networking engine in Python for Blender that allows any kind of multiplayer game project to be realised without writing the underlying network mechanism itself. Faced with such a challenge, most users would prefer to use another own engine, or remove the feature from the design document.
  
  This project intends to provide a useful Python framework for creating multiplayer games which eliminates the headache in writing and maintaining a networked game. It does not require the Blender Game Engine, but certain parts of the system must be realised by writing a new engine interface. Anything in the network library is pure python, and the bge_game_system is for BGE code."
  -- From the GitHub readme

The :py:mod:`network` module abstracts the details of UDP sockets under a multi-layered replication system. :py:class:`Connection` objects handle connections between peers, whilst a static-type :py:module:`serialisation layer <network.serialiser>` handles the interface between Python objects and the required bytes strings used by the socket layer. A :py:class:`network object<Replicable>` class is responsible for providing a user-friendly API for server-client data replication, inluding contextual role-based replication of function calls and attributes.
The game_system module

Networking Documentation
------------------------

.. toctree::
    :maxdepth: 2

    network

Game System Documentation
-------------------------

.. toctree::
    :maxdepth: 2

    game_system
    bge_game_system


Indices and tables
==================

* :ref:`modindex`
* :ref:`genindex`

