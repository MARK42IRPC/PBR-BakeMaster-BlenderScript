import bpy
from .new_tree import NODE_OT_new_bake_tree
from .add_channel import NODE_OT_add_save_channel
from .remove_channel import NODE_OT_remove_save_channel
from .bake_execute import BAKE_OT_execute
from .bake_cancel import BAKE_OT_cancel

classes = [
    NODE_OT_new_bake_tree,
    NODE_OT_add_save_channel,
    NODE_OT_remove_save_channel,
    BAKE_OT_execute,
    BAKE_OT_cancel,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
