import bpy

# 已自动填充过的节点树 ID 集合（避免重复填充）
_populated_trees = set()


def _ensure_init(node):
    """确保节点的 init() 已被调用（兼容各 Blender 版本）"""
    if len(node.inputs) == 0 and len(node.outputs) == 0:
        node.init(None)


def _build_default_nodes(tree):
    """在给定的节点树中创建一个默认管线：
    选择网格 → 采样 → 烘焙通道(漫反射) → 降噪 → 压缩 → 输出
    """
    nodes = tree.nodes
    links = tree.links

    mesh_node = nodes.new("BakeNode_MeshSelect")
    _ensure_init(mesh_node)
    mesh_node.location = (0, 100)

    sample_node = nodes.new("BakeNode_SampleSettings")
    _ensure_init(sample_node)
    sample_node.location = (0, -250)

    bake_node = nodes.new("BakeNode_BakeChannel")
    _ensure_init(bake_node)
    bake_node.location = (320, -75)
    bake_node.bake_type = 'DIFFUSE'

    denoise_node = nodes.new("BakeNode_PostDenoise")
    _ensure_init(denoise_node)
    denoise_node.location = (640, -75)

    compress_node = nodes.new("BakeNode_PostCompress")
    _ensure_init(compress_node)
    compress_node.location = (960, -75)

    save_node = nodes.new("BakeNode_SaveImage")
    _ensure_init(save_node)
    save_node.location = (1280, -75)

    links.new(mesh_node.outputs["高模"], bake_node.inputs["高模"])
    links.new(mesh_node.outputs["低模"], bake_node.inputs["低模"])
    links.new(sample_node.outputs["采样"], bake_node.inputs["采样"])
    links.new(bake_node.outputs["RGB"], denoise_node.inputs["RGBA"])
    links.new(denoise_node.outputs["RGBA"], compress_node.inputs["RGBA"])
    links.new(compress_node.outputs["RGBA"], save_node.inputs["RGBA"])


def _auto_populate_handler(scene, depsgraph):
    """depsgraph 更新时检测空的 BakeNodeTree 并自动填充"""
    for tree in bpy.data.node_groups:
        ptr = tree.as_pointer()
        if tree.bl_idname == 'BakeNodeTree' and len(tree.nodes) == 0 and ptr not in _populated_trees:
            _populated_trees.add(ptr)
            _build_default_nodes(tree)


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

    _validating_links: bool = False

    def update(self):
        """节点树变更时检测并移除类型不匹配的连接"""
        if BakeNodeTree._validating_links:
            return
        BakeNodeTree._validating_links = True
        try:
            for link in list(self.links):
                if link.from_socket.bl_idname != link.to_socket.bl_idname:
                    print(f"[BakeWrangler] ⚠ 类型不匹配: "
                          f"'{link.from_socket.bl_label}' → '{link.to_socket.bl_label}'，连接已移除")
                    self.links.remove(link)
        finally:
            BakeNodeTree._validating_links = False

    @classmethod
    def poll(cls, context):
        return True
