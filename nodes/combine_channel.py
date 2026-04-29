import bpy
from .mixin import BakeNodeMixin


def _mode_changed(self, context):
    """模式切换时重建输入 socket"""
    expected = 4 if self.mode == 'RGBA_SPLIT' else 2
    if len(self.inputs) == expected:
        return

    # 检查是否有已连接的 socket 将被销毁
    linked_sockets = [s for s in self.inputs if s.is_linked]
    if linked_sockets:
        names = ", ".join(f"'{s.name}'" for s in linked_sockets)
        print(f"[BakeWrangler] ⚠ 组合通道模式切换: 以下连接将被断开 → {names}")

    for s in list(self.inputs):
        self.inputs.remove(s)

    mode_label = "RGBA 分离" if self.mode == 'RGBA_SPLIT' else "RGB + Alpha"
    print(f"[BakeWrangler] 组合通道模式已切换为: {mode_label}")

    if self.mode == 'RGBA_SPLIT':
        self.inputs.new("BakeSocket_RGBA", "R")
        self.inputs.new("BakeSocket_RGBA", "G")
        self.inputs.new("BakeSocket_RGBA", "B")
        self.inputs.new("BakeSocket_RGBA", "A")
    else:
        self.inputs.new("BakeSocket_RGBA", "RGB")
        self.inputs.new("BakeSocket_RGBA", "A")


class BakeNode_CombineChannel(BakeNodeMixin, bpy.types.Node):
    """将多个通道组合为 RGBA 输出"""
    bl_idname = "BakeNode_CombineChannel"
    bl_label = "组合通道"
    bl_icon = 'MODIFIER'
    bl_width_default = 170

    mode: bpy.props.EnumProperty(
        name="模式",
        items=[
            ('RGBA_SPLIT', "RGBA 分离", "分别输入 R、G、B、A 四个灰度通道"),
            ('RGB_PLUS_A', "RGB + Alpha", "输入 RGB 和 Alpha 通道"),
        ],
        default='RGB_PLUS_A',
        description="选择通道组合方式",
        update=_mode_changed,
    )

    def init(self, context):
        if self.mode == 'RGBA_SPLIT':
            self.inputs.new("BakeSocket_RGBA", "R")
            self.inputs.new("BakeSocket_RGBA", "G")
            self.inputs.new("BakeSocket_RGBA", "B")
            self.inputs.new("BakeSocket_RGBA", "A")
        else:
            self.inputs.new("BakeSocket_RGBA", "RGB")
            self.inputs.new("BakeSocket_RGBA", "A")
        self.outputs.new("BakeSocket_RGBA", "RGBA")

    def draw_buttons(self, context, layout):
        layout.prop(self, "mode", expand=True)

    def draw_label(self):
        return "组合: RGBA" if self.mode == 'RGBA_SPLIT' else "组合: RGB + A"
