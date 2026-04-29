import bpy
from ..tree import _build_default_nodes, _populated_trees


class NODE_OT_new_bake_tree(bpy.types.Operator):
    """创建一个新的烘焙节点树并切换到烘焙编辑器"""
    bl_idname = "node.new_bake_tree"
    bl_label = "新建烘焙节点树"
    bl_description = "创建新的烘焙流程节点树，包含默认管线"

    def execute(self, context):
        tree = bpy.data.node_groups.new("烘焙流程", "BakeNodeTree")
        _populated_trees.add(tree.as_pointer())
        _build_default_nodes(tree)
        context.space_data.node_tree = tree
        self.report({'INFO'}, "已创建新的烘焙节点树（默认管线）")
        return {'FINISHED'}
