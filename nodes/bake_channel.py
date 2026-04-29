import bpy
from .mixin import BakeNodeMixin, prop_update


class BakeNode_BakeChannel(BakeNodeMixin, bpy.types.Node):
    """输入网格信息，选择烘焙通道类型。所有通道统一输出 RGB 数据"""
    bl_idname = "BakeNode_BakeChannel"
    bl_label = "烘焙通道"
    bl_icon = 'SHADING_RENDERED'
    bl_width_default = 180

    bake_types = [
        ('NORMAL',     "法线",        "法线贴图（切线空间）"),
        ('DIFFUSE',    "漫反射",      "漫反射 / 基础色贴图"),
        ('AO',         "环境光遮蔽",  "Ambient Occlusion 贴图"),
        ('ROUGHNESS',  "粗糙度",      "粗糙度 / 光滑度贴图"),
        ('METALLIC',   "金属度",      "金属度贴图"),
        ('CURVATURE',  "曲率",        "曲率贴图"),
        ('HEIGHT',     "高度",        "高度 / 位移贴图"),
        ('EMISSION',   "自发光",      "自发光 / Emissive 贴图"),
    ]

    bake_type: bpy.props.EnumProperty(
        name="通道类型",
        items=bake_types,
        default='NORMAL',
        description="选择要烘焙的贴图通道",
        update=prop_update,
    )

    resolution: bpy.props.EnumProperty(
        name="分辨率",
        items=[
            ('512',   "512 × 512",   ""),
            ('1024',  "1024 × 1024", ""),
            ('2048',  "2048 × 2048", ""),
            ('4096',  "4096 × 4096", ""),
            ('8192',  "8192 × 8192", ""),
        ],
        default='2048',
        description="输出贴图的分辨率",
        update=prop_update,
    )

    cage_extrusion: bpy.props.FloatProperty(
        name="包裹挤出",
        default=0.1,
        min=0.0,
        max=10.0,
        precision=3,
        description="烘焙 Cage 的挤出距离",
        update=prop_update,
    )

    max_ray_distance: bpy.props.FloatProperty(
        name="最大射线距离",
        default=0.2,
        min=0.0,
        max=10.0,
        precision=3,
        description="烘焙投射的最大射线距离",
        update=prop_update,
    )

    def init(self, context):
        self.inputs.new("BakeSocket_Mesh", "高模")
        self.inputs.new("BakeSocket_Mesh", "低模")
        self.inputs.new("BakeSocket_Sample", "采样")
        self.outputs.new("BakeSocket_RGBA", "RGB")

    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        col.prop(self, "bake_type")
        col.prop(self, "resolution")
        col.separator()
        col.prop(self, "cage_extrusion")
        col.prop(self, "max_ray_distance")

    def draw_label(self):
        type_names = {t[0]: t[1] for t in self.bake_types}
        return f"烘焙: {type_names.get(self.bake_type, self.bake_type)} → RGB"

    def get_sample_settings(self):
        """获取连接的采样设置，未连接则返回 None"""
        node = self.get_connected_node("采样")
        if node and node.bl_idname == "BakeNode_SampleSettings":
            return node
        return None
