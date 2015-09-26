1. Replace DelegateByNetmode with factory functions
2. Avoid complex mixins with meta classes

# Scenes
* Every scene has the existing "channels"
* Each scene has a unique network ID
* Send scene name at first sync, from server


Connection (management)

Network:
    {Connections}
        {SceneChannels}
            {ReplicableChannels}
            
    {Scenes}
        {Replicables}
        

Make WorldInfo.netmode read only, from network instance
Pass netmode down to each layer
Remove on_initialised


# NEW API
Dispatcher.set_listener(protocol, listener)

Update streams before sending, explicitly


Scene manager registered for new scenes and deleted scenes
For each valid scene (TODO) replicate scene channel
    TODO - difference between channel and manager?
    
    FOr each scene channel/manager:
        Set context from networkscene
        Replicate as existing system does
        NEED DEFAULT SCENE!?


