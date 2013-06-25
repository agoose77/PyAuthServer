class AttatchmentSocket:
    def __init__(self, parent, position):
        self.position = position
        self.parent = parent
        self.attatchment = None
        
    def attach(self, obj, align=False):
        obj.physics.position = self.parent.position + (self.parent.physics.orientation.to_matrix() * self.position)
        
        if align:
            obj.align_from(self.parent)
            
        self.attatchment = obj
        
        obj.setParent(self.parent)
        obj.owner = self.parent
        
    def detach(self):
        self.attatchment.removeParent()
        self.attatchment = None