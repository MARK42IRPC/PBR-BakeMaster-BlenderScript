import bpy
from .mixin import BakeNodeMixin, prop_update


class BakeNode_SampleSettings(BakeNodeMixin, bpy.types.Node):
    """输出 Cycles 采样设置，连接到烘焙通道的采样输入"""
    bl_idname = "BakeNode_SampleSettings"
    bl_label = "烘焙采样"
    bl_icon = 'RENDER_RESULT'
    bl_width_default = 190

    device: bpy.props.EnumProperty(
        name="渲染设备",
        items=[
            ('CPU', "CPU", "使用 CPU 渲染"),
            ('GPU', "GPU", "使用 GPU 渲染"),
        ],
        default='GPU',
        description="选择渲染设备",
        update=prop_update,
    )

    samples: bpy.props.IntProperty(
        name="采样数",
        default=128,
        min=1,
        max=4096,
        description="每像素采样数，越高画质越好但越慢",
        update=prop_update,
    )

    use_denoising: bpy.props.BoolProperty(
        name="降噪",
        default=True,
        description="烘焙后自动降噪",
        update=prop_update,
    )

    use_adaptive_sampling: bpy.props.BoolProperty(
        name="自适应采样",
        default=False,
        description="根据噪声阈值自动停止采样",
        update=prop_update,
    )

    noise_threshold: bpy.props.FloatProperty(
        name="噪声阈值",
        default=0.01,
        min=0.0,
        max=1.0,
        precision=3,
        description="自适应采样的噪声阈值（值越低画质越高）",
        update=prop_update,
    )

    margin: bpy.props.IntProperty(
        name="边距",
        default=16,
        min=0,
        max=64,
        subtype='PIXEL',
        description="UV 边缘扩展像素数",
        update=prop_update,
    )

    def init(self, context):
        self.outputs.new("BakeSocket_Sample", "采样")

    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        col.prop(self, "device")
        col.prop(self, "samples")
        col.separator()
        col.prop(self, "use_denoising")
        col.prop(self, "use_adaptive_sampling")
        if self.use_adaptive_sampling:
            col.prop(self, "noise_threshold")
        col.separator()
        col.prop(self, "margin")

    def draw_label(self):
        return f"采样: {self.device} {self.samples}spp"
