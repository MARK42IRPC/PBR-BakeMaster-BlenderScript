import bpy
from ..core import walk_tasks, validate_tasks, execute_single_task, cancel_bake, clear_bake_cache


class BAKE_OT_execute(bpy.types.Operator):
    """遍历节点图生成任务列表并逐通道烘焙。每帧处理一个任务，任务间刷新 UI"""
    bl_idname = "bake.execute"
    bl_label = "开始烘焙"
    bl_description = "根据节点图生成烘焙任务并开始逐通道执行"

    _timer = None
    _tasks: list = []
    _current_index: int = 0
    _tree_name: str = ""

    @classmethod
    def poll(cls, context):
        tree = getattr(context.space_data, 'node_tree', None)
        return tree is not None and tree.bl_idname == 'BakeNodeTree'

    def invoke(self, context, event):
        tree = context.space_data.node_tree
        if tree.bake_state == 'RUNNING':
            self.report({'WARNING'}, "烘焙已在运行中")
            return {'CANCELLED'}

        tasks = walk_tasks(tree)
        if not tasks:
            self.report({'ERROR'}, "未找到可执行的烘焙任务，请检查节点连接")
            return {'CANCELLED'}

        errors = validate_tasks(tasks)
        if errors:
            for err in errors:
                self.report({'ERROR'}, err)
            return {'CANCELLED'}

        self._tasks = tasks
        self._current_index = 0
        self._tree_name = tree.name

        tree.bake_state = 'RUNNING'
        tree.bake_progress = 0.0

        self._timer = context.window_manager.event_timer_add(0.5, window=context.window)
        context.window_manager.modal_handler_add(self)
        self.report({'INFO'}, f"开始烘焙 {len(tasks)} 个通道")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        tree = bpy.data.node_groups.get(self._tree_name)
        if tree is None:
            self._finish(context)
            return {'CANCELLED'}

        if tree.bake_state == 'CANCELLED':
            self._finish(context)
            self.report({'INFO'}, "烘焙已取消")
            return {'CANCELLED'}

        total = len(self._tasks)

        if self._current_index >= total:
            tree.bake_state = 'DONE'
            tree.bake_progress = 1.0
            self._finish(context)
            self.report({'INFO'}, f"烘焙完成: {total} 个通道")
            return {'FINISHED'}

        task = self._tasks[self._current_index]

        try:
            execute_single_task(task, tree)
        except Exception as e:
            tree.bake_state = 'ERROR'
            self.report({'ERROR'}, f"[{task.channel_name}] 失败: {e}")
            self._finish(context)
            return {'CANCELLED'}

        self._current_index += 1
        tree.bake_progress = self._current_index / total
        self.report({'INFO'}, f"[{self._current_index}/{total}] {task.channel_name} 完成")

        for area in context.screen.areas:
            if area.type == 'NODE_EDITOR':
                area.tag_redraw()

        return {'PASS_THROUGH'}

    def _finish(self, context):
        clear_bake_cache()
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
