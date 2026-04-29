import bpy


class NODE_PT_bake_overview(bpy.types.Panel):
    """烘焙编辑器侧边栏面板"""
    bl_label = "烘焙流程"
    bl_idname = "NODE_PT_bake_overview"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Bake"

    @classmethod
    def poll(cls, context):
        return context.space_data.tree_type == 'BakeNodeTree'

    def draw(self, context):
        layout = self.layout
        space = context.space_data
        tree = space.node_tree

        if tree is None:
            layout.label(text="尚未创建节点树", icon='ERROR')
            layout.operator("node.new_bake_tree", text="新建烘焙节点树", icon='FILE_NEW')
            return

        layout.label(text=f"节点树: {tree.name}", icon='NODETREE')

        nodes = tree.nodes
        stats = {
            "网格选择": "BakeNode_MeshSelect",
            "烘焙采样": "BakeNode_SampleSettings",
            "烘焙通道": "BakeNode_BakeChannel",
            "组合通道": "BakeNode_CombineChannel",
            "保存图像": "BakeNode_SaveImage",
        }

        col = layout.column(align=True)
        for label, bl_id in stats.items():
            count = len([n for n in nodes if n.bl_idname == bl_id])
            col.label(text=f"{label}: {count}")

        if context.selected_nodes:
            layout.separator()
            node = context.selected_nodes[0]
            box = layout.box()
            box.label(text=f"选中: {node.bl_label}", icon=node.bl_icon)
