bl_info = {
    "name": "PBR-BakeMaster",
    "author": "MARK42IRPC",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "Node Editor > PBR BakeMaster",
    "description": "PBR 纹理烘焙节点编辑器 — 可视化烘焙流程，支持法线/漫反射/AO/粗糙度/金属度/曲率/高度/自发光通道烘焙与 RGBA 合成",
    "category": "Render",
}

from . import sockets
from . import tree
from . import nodes
from . import operators
from . import panels
from . import categories
import bpy


def register():
    sockets.register()
    bpy.utils.register_class(tree.BakeNodeTree)
    nodes.register()
    operators.register()
    panels.register()
    categories.register()


def unregister():
    categories.unregister()
    panels.unregister()
    operators.unregister()
    nodes.unregister()
    bpy.utils.unregister_class(tree.BakeNodeTree)
    sockets.unregister()


if __name__ == "__main__":
    register()
