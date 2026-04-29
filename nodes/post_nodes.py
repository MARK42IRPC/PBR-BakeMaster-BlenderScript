import bpy
from .mixin import BakeNodeMixin, prop_update


class BakeNode_PostAntiAlias(BakeNodeMixin, bpy.types.Node):
    """对烘焙贴图进行抗锯齿处理"""
    bl_idname = "BakeNode_PostAntiAlias"
    bl_label = "后期抗锯齿"
    bl_icon = 'OUTLINER_OB_FONT'
    bl_width_default = 180

    algorithm: bpy.props.EnumProperty(
        name="算法",
        items=[
            ('FXAA', "FXAA", "快速近似抗锯齿"),
            ('BOX_3X3', "盒式模糊 3×3", "3×3 盒式模糊 (轻微柔化)"),
            ('BOX_5X5', "盒式模糊 5×5", "5×5 盒式模糊 (较强柔化)"),
            ('GAUSS_3X3', "高斯模糊 3×3", "3×3 高斯模糊"),
        ],
        default='FXAA',
        description="选择抗锯齿算法",
        update=prop_update,
    )

    def init(self, context):
        self.inputs.new("BakeSocket_RGBA", "RGBA")
        self.outputs.new("BakeSocket_RGBA", "RGBA")

    def draw_buttons(self, context, layout):
        layout.prop(self, "algorithm")

    def draw_label(self):
        algo_names = {'FXAA': "FXAA", 'BOX_3X3': "盒式 3×3", 'BOX_5X5': "盒式 5×5", 'GAUSS_3X3': "高斯 3×3"}
        return f"抗锯齿: {algo_names.get(self.algorithm, self.algorithm)}"


class BakeNode_PostScale(BakeNodeMixin, bpy.types.Node):
    """对烘焙贴图进行缩放"""
    bl_idname = "BakeNode_PostScale"
    bl_label = "后期缩放"
    bl_icon = 'FULLSCREEN_ENTER'
    bl_width_default = 180

    algorithm: bpy.props.EnumProperty(
        name="算法",
        items=[
            ('LANCZOS', "Lanczos", "Lanczos-3 (最锐利，细节保留最强)"),
            ('MITCHELL', "Mitchell", "Mitchell-Netravali (平衡锐度与平滑)"),
            ('BICUBIC', "双三次", "Catmull-Rom 双三次插值"),
            ('BILINEAR', "双线性", "双线性插值 (柔化)"),
            ('NEAREST', "最近邻", "最近邻采样 (像素风格)"),
        ],
        default='LANCZOS',
        description="选择缩放插值算法",
        update=prop_update,
    )

    target_resolution: bpy.props.EnumProperty(
        name="目标分辨率",
        items=[
            ('256', "256 × 256", ""),
            ('512', "512 × 512", ""),
            ('1024', "1024 × 1024", ""),
            ('2048', "2048 × 2048", ""),
            ('4096', "4096 × 4096", ""),
        ],
        default='1024',
        description="缩放后的目标分辨率",
        update=prop_update,
    )

    def init(self, context):
        self.inputs.new("BakeSocket_RGBA", "RGBA")
        self.outputs.new("BakeSocket_RGBA", "RGBA")

    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        col.prop(self, "algorithm")
        col.prop(self, "target_resolution")

    def draw_label(self):
        algo_names = {'LANCZOS': "Lanczos", 'MITCHELL': "Mitchell", 'BICUBIC': "双三次",
                      'BILINEAR': "双线性", 'NEAREST': "最近邻"}
        return f"缩放: {algo_names.get(self.algorithm, '?')} → {self.target_resolution}"


class BakeNode_PostMath(BakeNodeMixin, bpy.types.Node):
    """对贴图像素做数学运算（提取明度 → 运算 → 输出 RGBA）"""
    bl_idname = "BakeNode_PostMath"
    bl_label = "后期运算"
    bl_icon = 'CON_TRANSFORM'
    bl_width_default = 200

    operation: bpy.props.EnumProperty(
        name="运算",
        items=[
            ('NORMALIZE', "规格化", "自动将明度范围拉伸到 [0, 1]"),
            ('MULTIPLY', "乘", "明度 × 系数"),
            ('ADD', "加", "明度 + 系数"),
            ('SUBTRACT', "减", "明度 − 系数"),
            ('POWER', "幂", "明度 ^ 系数"),
            ('GREATER_THAN', "大于", "明度 > 阈值 ? 1 : 0"),
            ('LESS_THAN', "小于", "明度 < 阈值 ? 1 : 0"),
            ('CLAMP', "钳制", "将明度限制在 [最小值, 最大值] 范围"),
            ('MAP_RANGE', "范围映射", "将明度从 [min, max] 映射到 [0, 1]"),
            ('INVERT', "反转", "1 − 明度"),
        ],
        default='MULTIPLY',
        description="对明度执行的数学运算",
        update=prop_update,
    )

    factor: bpy.props.FloatProperty(
        name="系数",
        default=1.0, min=-100.0, max=100.0, precision=3,
        description="运算系数 (乘/加/减/幂 时使用)",
        update=prop_update,
    )

    threshold: bpy.props.FloatProperty(
        name="阈值",
        default=0.5, min=0.0, max=1.0, precision=3,
        description="阈值 (大于/小于 时使用)",
        update=prop_update,
    )

    clamp_min: bpy.props.FloatProperty(
        name="最小值",
        default=0.0, min=0.0, max=1.0, precision=3,
        description="钳制/映射的最小值",
        update=prop_update,
    )

    clamp_max: bpy.props.FloatProperty(
        name="最大值",
        default=1.0, min=0.0, max=1.0, precision=3,
        description="钳制/映射的最大值",
        update=prop_update,
    )

    def init(self, context):
        self.inputs.new("BakeSocket_RGBA", "RGBA")
        self.outputs.new("BakeSocket_RGBA", "RGBA")

    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        col.prop(self, "operation")
        op = self.operation
        if op in ('MULTIPLY', 'ADD', 'SUBTRACT', 'POWER'):
            col.prop(self, "factor")
        elif op in ('GREATER_THAN', 'LESS_THAN'):
            col.prop(self, "threshold")
        elif op == 'CLAMP':
            col.prop(self, "clamp_min")
            col.prop(self, "clamp_max")
        elif op == 'MAP_RANGE':
            col.prop(self, "clamp_min")
            col.prop(self, "clamp_max")
        # INVERT 无需参数

    def draw_label(self):
        op_names = {
            'NORMALIZE': "规格化",
            'MULTIPLY': f"乘 {self.factor:.2f}",
            'ADD': f"加 {self.factor:.2f}",
            'SUBTRACT': f"减 {self.factor:.2f}",
            'POWER': f"幂 {self.factor:.2f}",
            'GREATER_THAN': f"大于 {self.threshold:.2f}",
            'LESS_THAN': f"小于 {self.threshold:.2f}",
            'CLAMP': f"钳制 [{self.clamp_min:.2f}, {self.clamp_max:.2f}]",
            'MAP_RANGE': f"映射 [{self.clamp_min:.2f}, {self.clamp_max:.2f}]",
            'INVERT': "反转",
        }
        return f"运算: {op_names.get(self.operation, self.operation)}"


class BakeNode_PostCompress(BakeNodeMixin, bpy.types.Node):
    """对 RGBA 图像进行有损压缩优化"""
    bl_idname = "BakeNode_PostCompress"
    bl_label = "后期压缩"
    bl_icon = 'FILE_ARCHIVE'
    bl_width_default = 180

    compression: bpy.props.EnumProperty(
        name="压缩级别",
        items=[
            ('15', "最高 (15)", "PNG 压缩级别 15 (最小文件)"),
            ('10', "高 (10)", "PNG 压缩级别 10"),
            ('5', "中 (5)", "PNG 压缩级别 5"),
            ('1', "低 (1)", "PNG 压缩级别 1 (最快)"),
            ('0', "无 (0)", "不压缩"),
        ],
        default='15',
        description="PNG 压缩级别",
        update=prop_update,
    )

    quantization: bpy.props.EnumProperty(
        name="色彩量化",
        items=[
            ('NONE', "不量化", "保持原始色彩精度"),
            ('256_COLORS', "256 色", "量化到 256 色调色板"),
            ('64_COLORS', "64 色", "量化到 64 色调色板"),
            ('16_COLORS', "16 色", "量化到 16 色调色板"),
        ],
        default='NONE',
        description="色彩量化级别 (有损)",
        update=prop_update,
    )

    def init(self, context):
        self.inputs.new("BakeSocket_RGBA", "RGBA")
        self.outputs.new("BakeSocket_RGBA", "RGBA")

    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        col.prop(self, "compression")
        col.prop(self, "quantization")

    def draw_label(self):
        q = {'NONE': "无损", '256_COLORS': "256色", '64_COLORS': "64色", '16_COLORS': "16色"}
        return f"压缩: lv{self.compression} {q.get(self.quantization, '?')}"


class BakeNode_PostDenoise(BakeNodeMixin, bpy.types.Node):
    """对烘焙贴图进行降噪处理"""
    bl_idname = "BakeNode_PostDenoise"
    bl_label = "后期降噪"
    bl_icon = 'MOD_PARTICLES'
    bl_width_default = 180

    algorithm: bpy.props.EnumProperty(
        name="算法",
        items=[
            ('MEDIAN_3X3', "中值滤波 3×3", "3×3 中值滤波 (去除孤立噪点)"),
            ('MEDIAN_5X5', "中值滤波 5×5", "5×5 中值滤波 (更强去噪)"),
            ('BILATERAL_3X3', "双边滤波 3×3", "3×3 双边滤波 (保边平滑)"),
            ('BILATERAL_5X5', "双边滤波 5×5", "5×5 双边滤波 (保边强平滑)"),
            ('GAUSSIAN_3X3', "高斯模糊 3×3", "3×3 高斯模糊 (柔和降噪)"),
            ('GAUSSIAN_5X5', "高斯模糊 5×5", "5×5 高斯模糊 (较强降噪)"),
        ],
        default='BILATERAL_3X3',
        description="选择降噪算法",
        update=prop_update,
    )

    def init(self, context):
        self.inputs.new("BakeSocket_RGBA", "RGBA")
        self.outputs.new("BakeSocket_RGBA", "RGBA")

    def draw_buttons(self, context, layout):
        layout.prop(self, "algorithm")

    def draw_label(self):
        algo_names = {
            'MEDIAN_3X3': "中值 3×3", 'MEDIAN_5X5': "中值 5×5",
            'BILATERAL_3X3': "双边 3×3", 'BILATERAL_5X5': "双边 5×5",
            'GAUSSIAN_3X3': "高斯 3×3", 'GAUSSIAN_5X5': "高斯 5×5",
        }
        return f"降噪: {algo_names.get(self.algorithm, self.algorithm)}"
