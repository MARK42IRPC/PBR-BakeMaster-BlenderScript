import bpy
from ..core import cancel_bake


class BAKE_OT_cancel(bpy.types.Operator):
    """取消正在执行的烘焙任务"""
    bl_idname = "bake.cancel"
    bl_label = "取消烘焙"
    bl_description = "取消当前烘焙任务"

    @classmethod
    def poll(cls, context):
        tree = getattr(context.space_data, 'node_tree', None)
        return tree is not None and tree.bake_state == 'RUNNING'

    def execute(self, context):
        tree = context.space_data.node_tree
        cancel_bake(tree)
        self.report({'INFO'}, "烘焙已取消")
        return {'FINISHED'}
