import bpy
from .mixin import BakeNodeMixin, prop_update


class BakeNode_SaveImage(BakeNodeMixin, bpy.types.Node):
    """输入 RGBA 数据，按指定路径保存为图像文件。每个输入 socket 名称作为通道名拼接到文件名中"""
    bl_idname = "BakeNode_SaveImage"
    bl_label = "保存图像"
    bl_icon = 'EXPORT'
    bl_width_default = 240

    directory_path: bpy.props.StringProperty(
        name="保存路径",
        subtype='DIR_PATH',
        description="图像文件保存的目录路径",
        update=prop_update,
    )

    filename_prefix: bpy.props.StringProperty(
        name="文件名头",
        default="Bake_",
        description="文件名前缀，最终文件名为 {前缀}{通道名}.{扩展名}",
        update=prop_update,
    )

    file_format: bpy.props.EnumProperty(
        name="文件格式",
        items=[
            ('PNG',  "PNG",  "PNG 格式，支持透明通道"),
            ('EXR',  "EXR",  "OpenEXR 格式，支持 HDR"),
            ('TGA',  "TGA",  "Targa 格式"),
            ('TIFF', "TIFF", "TIFF 格式"),
        ],
        default='PNG',
        description="输出图像的文件格式",
        update=prop_update,
    )

    color_depth: bpy.props.EnumProperty(
        name="色彩深度",
        items=[
            ('8',  "8 bit",  "8 位每通道"),
            ('16', "16 bit", "16 位每通道"),
            ('32', "32 bit", "32 位浮点（仅 EXR 支持）"),
        ],
        default='8',
        description="输出图像的色彩深度",
        update=prop_update,
    )

    def init(self, context):
        self.inputs.new("BakeSocket_RGBA", "RGBA")

    def draw_buttons(self, context, layout):
        tree = self.id_data

        # ── 烘焙控制 ──
        box = layout.box()
        state = tree.bake_state if tree else 'IDLE'

        if state == 'RUNNING':
            row = box.row()
            row.operator("bake.cancel", text="取消烘焙", icon='X')
            box.prop(tree, "bake_progress", text="进度", slider=True)
        else:
            row = box.row()
            row.operator("bake.execute", text="开始烘焙", icon='RENDER_STILL')

        layout.separator()

        # ── 保存设置 ──
        col = layout.column(align=True)
        col.prop(self, "directory_path")
        col.prop(self, "filename_prefix")
        col.separator()
        row = layout.row(align=True)
        row.prop(self, "file_format", expand=True)
        col.prop(self, "color_depth")

        # ── 通道管理 ──
        layout.separator()
        box = layout.box()
        row = box.row()
        row.label(text="输出通道:", icon='IMAGE_DATA')
        row.operator("bake.add_save_channel", text="", icon='ADD')

        for i, socket in enumerate(self.inputs):
            row = box.row(align=True)
            row.label(text=socket.name, icon='DOT')
            op = row.operator("bake.remove_save_channel", text="", icon='X')
            op.channel_index = i

    def draw_label(self):
        count = len(self.inputs)
        prefix = self.filename_prefix or "Bake_"
        return f"保存: {prefix}... ({count}通道)"

    def get_output_filename(self, channel_name=""):
        """根据前缀和通道名生成完整文件名"""
        prefix = self.filename_prefix or "Bake_"
        ext = self.file_format.lower()
        if channel_name:
            return f"{prefix}{channel_name}.{ext}"
        return f"{prefix}output.{ext}"
