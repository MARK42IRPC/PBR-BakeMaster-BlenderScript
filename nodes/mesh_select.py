import bpy
from .mixin import BakeNodeMixin, prop_update


class BakeNode_MeshSelect(BakeNodeMixin, bpy.types.Node):
    """选择高模和低模网格物体，输出网格信息"""
    bl_idname = "BakeNode_MeshSelect"
    bl_label = "选择网格"
    bl_icon = 'MESH_DATA'
    bl_width_default = 200

    high_poly_object: bpy.props.PointerProperty(
        name="高模",
        type=bpy.types.Object,
        description="高精度模型（用于投射细节）",
        update=prop_update,
    )

    low_poly_object: bpy.props.PointerProperty(
        name="低模",
        type=bpy.types.Object,
        description="低精度模型（烘焙目标）",
        update=prop_update,
    )

    def init(self, context):
        self.outputs.new("BakeSocket_Mesh", "高模")
        self.outputs.new("BakeSocket_Mesh", "低模")

    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        col.prop(self, "high_poly_object")
        col.prop(self, "low_poly_object")

    def draw_label(self):
        hp = self.high_poly_object
        lp = self.low_poly_object
        if hp and lp:
            return f"选择网格: {hp.name} → {lp.name}"
        elif hp:
            return f"选择网格: {hp.name} → ?"
        return self.bl_label
