import bpy
from .mesh_select import BakeNode_MeshSelect
from .bake_channel import BakeNode_BakeChannel
from .combine_channel import BakeNode_CombineChannel
from .save_image import BakeNode_SaveImage
from .sample_settings import BakeNode_SampleSettings
from .post_nodes import (
    BakeNode_PostAntiAlias,
    BakeNode_PostScale,
    BakeNode_PostMath,
    BakeNode_PostCompress,
    BakeNode_PostDenoise,
)

classes = [
    BakeNode_MeshSelect,
    BakeNode_BakeChannel,
    BakeNode_CombineChannel,
    BakeNode_SaveImage,
    BakeNode_SampleSettings,
    BakeNode_PostAntiAlias,
    BakeNode_PostScale,
    BakeNode_PostMath,
    BakeNode_PostCompress,
    BakeNode_PostDenoise,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
