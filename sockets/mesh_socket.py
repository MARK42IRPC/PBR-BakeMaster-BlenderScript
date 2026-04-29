import bpy


class BakeSocket_Mesh(bpy.types.NodeSocket):
    """传递网格物体引用的 Socket"""
    bl_idname = "BakeSocket_Mesh"
    bl_label = "网格"

    def draw(self, context, layout, node, text):
        layout.label(text=text)

    def draw_color(self, context, node):
        return (0.78, 0.45, 0.15, 1.0)
