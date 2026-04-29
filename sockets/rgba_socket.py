import bpy


class BakeSocket_RGBA(bpy.types.NodeSocket):
    """传递 RGBA 颜色/图像数据的 Socket"""
    bl_idname = "BakeSocket_RGBA"
    bl_label = "RGBA"

    def draw(self, context, layout, node, text):
        layout.label(text=text)

    def draw_color(self, context, node):
        return (0.9, 0.7, 0.2, 1.0)
