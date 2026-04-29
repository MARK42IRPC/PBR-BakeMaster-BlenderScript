import bpy


class NODE_OT_new_bake_tree(bpy.types.Operator):
    """创建一个新的烘焙节点树并切换到烘焙编辑器"""
    bl_idname = "node.new_bake_tree"
    bl_label = "新建烘焙节点树"
    bl_description = "创建新的烘焙流程节点树"

    def execute(self, context):
        tree = bpy.data.node_groups.new("烘焙流程", "BakeNodeTree")
        context.space_data.node_tree = tree
        self.report({'INFO'}, "已创建新的烘焙节点树")
        return {'FINISHED'}
