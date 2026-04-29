import bpy


class NODE_OT_add_save_channel(bpy.types.Operator):
    """为保存图像节点添加一个输出通道"""
    bl_idname = "bake.add_save_channel"
    bl_label = "添加通道"
    bl_description = "添加一个命名 RGBA 输入通道"

    channel_name: bpy.props.StringProperty(
        name="通道名",
        default="RGBA",
        description="通道名称，将作为文件名的一部分"
    )

    node_name: bpy.props.StringProperty(options={'HIDDEN'})
    tree_name: bpy.props.StringProperty(options={'HIDDEN'})

    def invoke(self, context, event):
        node = context.node
        if node is None or node.bl_idname != "BakeNode_SaveImage":
            self.report({'ERROR'}, "请在保存图像节点上操作")
            return {'CANCELLED'}
        self.node_name = node.name
        self.tree_name = node.id_data.name
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        tree = bpy.data.node_groups.get(self.tree_name)
        if tree is None:
            return {'CANCELLED'}
        node = tree.nodes.get(self.node_name)
        if node is None:
            return {'CANCELLED'}
        node.inputs.new("BakeSocket_RGBA", self.channel_name)
        return {'FINISHED'}
