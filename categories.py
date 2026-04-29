import nodeitems_utils
from nodeitems_utils import NodeCategory, NodeItem


class BakeNodeCategory(NodeCategory):
    @classmethod
    def poll(cls, context):
        return context.space_data.tree_type == 'BakeNodeTree'


_categories = [
    BakeNodeCategory(
        "BAKE_INPUT",
        "输入",
        items=[
            NodeItem("BakeNode_MeshSelect"),
            NodeItem("BakeNode_SampleSettings"),
        ],
    ),
    BakeNodeCategory(
        "BAKE_OPERATION",
        "烘焙",
        items=[
            NodeItem("BakeNode_BakeChannel"),
            NodeItem("BakeNode_CombineChannel"),
        ],
    ),
    BakeNodeCategory(
        "BAKE_OUTPUT",
        "输出",
        items=[NodeItem("BakeNode_SaveImage")],
    ),
    BakeNodeCategory(
        "BAKE_POST",
        "后期",
        items=[
            NodeItem("BakeNode_PostAntiAlias"),
            NodeItem("BakeNode_PostScale"),
            NodeItem("BakeNode_PostMath"),
            NodeItem("BakeNode_PostCompress"),
            NodeItem("BakeNode_PostDenoise"),
        ],
    ),
]


def register():
    nodeitems_utils.register_node_categories("BAKE_NODES", _categories)


def unregister():
    nodeitems_utils.unregister_node_categories("BAKE_NODES")
