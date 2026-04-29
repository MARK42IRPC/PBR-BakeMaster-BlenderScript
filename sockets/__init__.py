import bpy
from .mesh_socket import BakeSocket_Mesh
from .rgba_socket import BakeSocket_RGBA
from .sample_socket import BakeSocket_Sample

classes = [
    BakeSocket_Mesh,
    BakeSocket_RGBA,
    BakeSocket_Sample,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
