import bpy


class BakeSocket_Sample(bpy.types.NodeSocket):
    """传递 Cycles 采样设置的 Socket"""
    bl_idname = "BakeSocket_Sample"
    bl_label = "采样"

    def draw(self, context, layout, node, text):
        layout.label(text=text)

    def draw_color(self, context, node):
        return (0.45, 0.55, 0.85, 1.0)
