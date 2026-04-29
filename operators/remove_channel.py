import bpy


class NODE_OT_remove_save_channel(bpy.types.Operator):
    """从保存图像节点移除一个输出通道"""
    bl_idname = "bake.remove_save_channel"
    bl_label = "移除通道"
    bl_description = "移除该 RGBA 输入通道"

    channel_index: bpy.props.IntProperty(options={'HIDDEN'})

    node_name: bpy.props.StringProperty(options={'HIDDEN'})
    tree_name: bpy.props.StringProperty(options={'HIDDEN'})

    def invoke(self, context, event):
        node = context.node
        if node is None:
            return {'CANCELLED'}
        if self.channel_index < 0 or self.channel_index >= len(node.inputs):
            return {'CANCELLED'}
        socket = node.inputs[self.channel_index]
        if socket.is_linked:
            self.report({'WARNING'}, f"通道 '{socket.name}' 有活动连接，移除将断开连接")
        self.node_name = node.name
        self.tree_name = node.id_data.name
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        tree = bpy.data.node_groups.get(self.tree_name)
        if tree is None:
            return {'CANCELLED'}
        node = tree.nodes.get(self.node_name)
        if node is None:
            return {'CANCELLED'}

        if self.channel_index < 0 or self.channel_index >= len(node.inputs):
            return {'CANCELLED'}

        socket = node.inputs[self.channel_index]
        node.inputs.remove(socket)
        return {'FINISHED'}
