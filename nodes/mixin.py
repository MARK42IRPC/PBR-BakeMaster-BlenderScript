def prop_update(self, context):
    """节点属性变更时标记需要更新"""
    if hasattr(self, 'update_tag'):
        self.update_tag()


class BakeNodeMixin:
    """烘焙节点的公共方法"""

    @classmethod
    def poll(cls, ntree):
        return ntree.bl_idname == 'BakeNodeTree'

    def get_connected_node(self, socket_name):
        """获取连接到指定输入 socket 的上游节点"""
        socket = self.inputs.get(socket_name)
        if socket and socket.is_linked and len(socket.links) > 0:
            return socket.links[0].from_node
        return None

    def get_mesh_from_input(self, socket_name):
        """从输入 socket 追溯上游节点，获取网格物体引用"""
        node = self.get_connected_node(socket_name)
        if node is None:
            return None
        if socket_name == "高模":
            return getattr(node, "high_poly_object", None)
        elif socket_name == "低模":
            return getattr(node, "low_poly_object", None)
        return None
