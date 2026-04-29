import bpy


class BakeNodeTree(bpy.types.NodeTree):
    """烘焙流程节点树 - 在节点编辑器中选择"烘焙编辑器"类型使用"""
    bl_idname = "BakeNodeTree"
    bl_label = "烘焙编辑器"
    bl_icon = 'RENDER_STILL'

    bake_state: bpy.props.EnumProperty(
        name="烘焙状态",
        items=[
            ('IDLE',       "空闲",   ""),
            ('VALIDATING', "校验中", ""),
            ('RUNNING',    "烘焙中", ""),
            ('DONE',       "完成",   ""),
            ('ERROR',      "错误",   ""),
            ('CANCELLED',  "已取消", ""),
        ],
        default='IDLE',
        options={'HIDDEN'},
    )

    bake_progress: bpy.props.FloatProperty(
        name="进度",
        default=0.0,
        min=0.0,
        max=1.0,
        subtype='FACTOR',
        options={'HIDDEN'},
    )

    bake_message: bpy.props.StringProperty(
        name="消息",
        default="",
        options={'HIDDEN'},
    )

    @classmethod
    def poll(cls, context):
        return True
