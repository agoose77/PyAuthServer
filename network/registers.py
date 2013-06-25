class InstanceRegister(TypeRegister):
    
    def __new__(meta, name, parents, attrs):       
        
        parents += (InstanceMixins,) 
        cls = super().__new__(meta, name, parents, attrs)
        
        if not hasattr(cls, "_instances"):
            cls._instances = {}
            cls._to_register = set()
            cls._to_unregister = set()
                        
        return cls
    
    def __iter__(self):
        return iter(self._instances.values())
    
class PermissionRegister(InstanceRegister):
    def __new__(cls, cls_name, bases, attrs):
        # If this isn't the base class
        if bases:
            # Get all the member methods
            for name, value in attrs.items():
                # Check it's not in parents (will have been checked)
                if cls.in_parents_of(bases, name):
                    continue
                # Wrap them with permission
                if isinstance(value, FunctionType) or isinstance(value, classmethod) or isinstance(value, staticmethod):
                    attrs[name] = cls.permission_wrapper(value)
        
        return super().__new__(cls, cls_name, bases, attrs)
    
    def in_parents_of(bases, name):
        for parent in bases:
            if name in dir(parent):
                return True
    
    def permission_wrapper(func):
        simulated_proxy = Roles.simulated_proxy
        attribute_type = Attribute
        func_is_simulated = is_simulated(func)
        
        @wraps(func)
        def func_wrapper(*args, **kwargs):
            if args:
                assumed_instance = args[0]
                # Check that the assumed instance/class has a role method
                if hasattr(assumed_instance, "roles"):
                    arg_roles = assumed_instance.roles
                    # Check that the roles are of an instance
                    try:
                        local_role = arg_roles.local
                    except AttributeError:
                        return
                    
                    # Permission checks
                    if (local_role > simulated_proxy or(func_is_simulated and local_role >= simulated_proxy)):
                        return func(*args, **kwargs)
                    
                    elif getattr(assumed_instance, "verbose_execution", False):
                        print("Error executing '{}': Function does not have permission:\n{}".format(func.__qualname__, arg_roles))
                        
                elif getattr(assumed_instance, "verbose_execution", False):
                    print("Error executing {}: Function does not have permission roles")
            
            # Static method needs no permission
            return func(*args, **kwargs)
        
        return func_wrapper
    
