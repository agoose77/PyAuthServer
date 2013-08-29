from bge_network import ClientLoop

from actors import ExampleController

class Client(ClientLoop):
    
    def create_network(self):
        network = super().create_network()
        
        network.connect_to(("localhost", 1200))
        return network