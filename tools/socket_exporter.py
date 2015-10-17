"""Export armature sockets from Blender"""

import io

import bpy
from _game_system.configobj import ConfigObj


def get_sockets(obj):
    bones = obj.pose.bones

    sockets = {}

    for child in obj.children:
        if child.parent_type != 'BONE':
            continue
        
        bone_name = child.parent_bone
        
        bone = bones[bone_name]
        bone_matrix = obj.matrix_world * bone.matrix
        
        child_matrix = child.matrix_world
        
        transform_difference = bone_matrix.inverted() * child_matrix
        sockets[child.name] = bone_name, transform_difference
    return sockets


def write_sockets(config, sockets):
    config['sockets'] = {n: {'bone': b, 'transform': mat_to_list(t)} for n, (b, t) in sockets.items()}
    

def mat_to_list(t):
    return [e for col in t.col for e in col]


class SocketExportOperator(bpy.types.Operator):
    """Tooltip"""
    bl_idname = "object.export_sockets"
    bl_label = "Socket Export Operator"

    depth = bpy.props.IntProperty(name="depth", default=1)

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    def execute(self, context):
        sockets = get_sockets(context.active_object)
        
        config = ConfigObj()
        config.depth = self.depth
        
        write_sockets(config, sockets)
        
        fp = io.BytesIO()
        config.write(fp)
        
        fp.seek(0)
        result = fp.read().decode()
        
        context.window_manager.clipboard = result
        
        return {'FINISHED'}


def register():
    bpy.utils.register_class(SocketExportOperator)


def unregister():
    bpy.utils.unregister_class(SocketExportOperator)


if __name__ == "__main__":
    register()
