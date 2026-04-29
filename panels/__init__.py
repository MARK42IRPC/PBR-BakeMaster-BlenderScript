import bpy
from .overview import NODE_PT_bake_overview

classes = [
    NODE_PT_bake_overview,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
