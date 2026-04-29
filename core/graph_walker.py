from .task import BakeTask, CompositeTask, PostEffect


def walk_tasks(node_tree):
    """遍历节点树，从保存图像节点逆序追溯，生成烘焙任务列表"""
    tasks = []
    save_nodes = [
        n for n in node_tree.nodes
        if n.bl_idname == "BakeNode_SaveImage"
    ]

    print(f"[BakeWrangler] walk_tasks: 找到 {len(save_nodes)} 个保存图像节点")

    for save_node in save_nodes:
        directory = save_node.directory_path
        prefix = save_node.filename_prefix or "Bake_"
        fmt = save_node.file_format
        depth = save_node.color_depth

        print(f"[BakeWrangler]   保存节点: dir={directory!r}, prefix={prefix!r}, fmt={fmt}, depth={depth}")
        print(f"[BakeWrangler]   输入 socket 数: {len(save_node.inputs)}")

        for socket in save_node.inputs:
            print(f"[BakeWrangler]     socket '{socket.name}' linked={socket.is_linked}")
            if not socket.is_linked:
                continue
            source_node = socket.links[0].from_node
            channel_name = socket.name
            output_path = _build_output_path(directory, prefix, channel_name, fmt)
            print(f"[BakeWrangler]     -> 追溯源节点: {source_node.bl_idname} '{source_node.name}'")
            _trace_source(source_node, channel_name, output_path, fmt, depth, [], set(), tasks)

    print(f"[BakeWrangler] walk_tasks: 共生成 {len(tasks)} 个任务")
    return tasks


def _build_output_path(directory, prefix, channel_name, fmt):
    import os
    ext = fmt.lower()
    filename = f"{prefix}{channel_name}.{ext}"
    if directory:
        return os.path.join(directory, filename)
    return filename


def _trace_source(node, channel_name, output_path, fmt, depth, post_effects, visited, tasks):
    """递归追溯上游节点，收集后期效果链直到找到烘焙通道"""
    if node in visited:
        print(f"[BakeWrangler]       ⚠ 检测到节点循环: '{node.name}'，停止追溯")
        return
    visited.add(node)

    # 检查是否是后期节点
    post = _extract_post_effect(node)
    if post is not None:
        print(f"[BakeWrangler]       后期节点: '{node.name}' type={post.effect_type}")
        # 将效果添加到链中，继续追溯上游
        effects = post_effects + [post]
        for socket in node.inputs:
            if socket.is_linked:
                _trace_source(socket.links[0].from_node, channel_name, output_path,
                              fmt, depth, effects, visited, tasks)
                return
        print(f"[BakeWrangler]       ⚠ 后期节点 '{node.name}' 没有上游连接")
        return

    if node.bl_idname == "BakeNode_BakeChannel":
        print(f"[BakeWrangler]       找到烘焙通道节点: '{node.name}', bake_type={node.bake_type}")
        task = _make_task_from_channel(node, channel_name, output_path, fmt, depth)
        task.post_effects = list(post_effects)
        if post_effects:
            print(f"[BakeWrangler]       附加 {len(post_effects)} 个后期效果")
        tasks.append(task)

    elif node.bl_idname == "BakeNode_CombineChannel":
        print(f"[BakeWrangler]       经过组合通道节点: '{node.name}', mode={node.mode}")
        sources = []
        for socket in node.inputs:
            if socket.is_linked:
                src_node = socket.links[0].from_node
                print(f"[BakeWrangler]         socket '{socket.name}' -> {src_node.bl_idname} '{src_node.name}'")
                if src_node.bl_idname == "BakeNode_BakeChannel":
                    src_task = _make_task_from_channel(src_node, socket.name, output_path, fmt, depth)
                    sources.append((socket.name, src_task))
                else:
                    # 尝试穿透后期节点链找到烘焙通道
                    channel_node, per_channel_effects = _resolve_source_for_composite(src_node)
                    if channel_node is not None:
                        src_task = _make_task_from_channel(channel_node, socket.name, output_path, fmt, depth)
                        src_task.post_effects = per_channel_effects
                        sources.append((socket.name, src_task))
                        print(f"[BakeWrangler]         -> 穿透 {len(per_channel_effects)} 个后期节点到达 {channel_node.name}")
                    else:
                        print(f"[BakeWrangler]         ⚠ 组合通道输入无法解析到烘焙通道: {src_node.bl_idname}")

        if sources:
            composite = CompositeTask(
                combine_mode=node.mode,
                sources=sources,
                output_path=output_path,
                channel_name=channel_name,
                file_format=fmt,
                color_depth=depth,
                post_effects=list(post_effects),
            )
            if post_effects:
                print(f"[BakeWrangler]       附加 {len(post_effects)} 个后期效果")
            print(f"[BakeWrangler]       生成合成任务: {composite}")
            tasks.append(composite)
        else:
            print(f"[BakeWrangler]       ⚠ 组合通道没有有效的输入源")


def _extract_post_effect(node):
    """从后期节点提取 PostEffect，非后期节点返回 None"""
    bl_id = node.bl_idname

    if bl_id == "BakeNode_PostAntiAlias":
        return PostEffect(effect_type='ANTIALIAS', params={'algorithm': node.algorithm})

    elif bl_id == "BakeNode_PostScale":
        return PostEffect(effect_type='SCALE', params={
            'algorithm': node.algorithm,
            'target_resolution': int(node.target_resolution),
        })

    elif bl_id == "BakeNode_PostMath":
        return PostEffect(effect_type='MATH', params={
            'operation': node.operation,
            'factor': node.factor,
            'threshold': node.threshold,
            'clamp_min': node.clamp_min,
            'clamp_max': node.clamp_max,
        })

    elif bl_id == "BakeNode_PostCompress":
        return PostEffect(effect_type='COMPRESS', params={
            'compression': node.compression,
            'quantization': node.quantization,
        })

    elif bl_id == "BakeNode_PostDenoise":
        return PostEffect(effect_type='DENOISE', params={'algorithm': node.algorithm})

    return None


def _resolve_source_for_composite(start_node):
    """从组合通道输入追溯，穿透后期节点链找到烘焙通道节点，返回 (BakeChannel节点, 后期效果列表)。
    未找到烘焙通道时返回 (None, [])。"""
    post_effects = []
    current = start_node
    visited = set()
    while current is not None:
        if current in visited:
            print(f"[BakeWrangler]       ⚠ 检测到节点循环: '{current.name}'，停止追溯")
            return None, []
        visited.add(current)
        if current.bl_idname == "BakeNode_BakeChannel":
            return current, post_effects
        post = _extract_post_effect(current)
        if post is not None:
            post_effects.append(post)
            next_node = None
            for sock in current.inputs:
                if sock.is_linked:
                    next_node = sock.links[0].from_node
                    break
            if next_node is None:
                print(f"[BakeWrangler]       ⚠ 后期节点 '{current.name}' 没有上游连接")
                return None, []
            current = next_node
        else:
            return None, []
    return None, []


def _make_task_from_channel(node, channel_name, output_path, fmt, depth):
    """从烘焙通道节点构建 BakeTask，优先使用连接的采样设置"""
    hp = node.get_mesh_from_input("高模") if hasattr(node, 'get_mesh_from_input') else None
    lp = node.get_mesh_from_input("低模") if hasattr(node, 'get_mesh_from_input') else None

    print(f"[BakeWrangler]         高模: {hp.name if hp else 'None'}  (类型: {type(hp).__name__ if hp else 'N/A'})")
    print(f"[BakeWrangler]         低模: {lp.name if lp else 'None'}  (类型: {type(lp).__name__ if lp else 'N/A'})")

    try:
        resolution = int(node.resolution)
    except (ValueError, TypeError):
        resolution = 2048
    print(f"[BakeWrangler]         resolution={resolution}, bake_type={node.bake_type}")

    for name in ("高模", "低模"):
        sock = node.inputs.get(name)
        if sock:
            linked_node = node.get_connected_node(name)
            print(f"[BakeWrangler]         '{name}' input socket: linked={sock.is_linked}, from_node={linked_node.bl_idname if linked_node else 'None'}")

    sample_node = node.get_sample_settings() if hasattr(node, 'get_sample_settings') else None
    if sample_node:
        device = sample_node.device
        samples = sample_node.samples
        use_denoising = sample_node.use_denoising
        use_adaptive_sampling = sample_node.use_adaptive_sampling
        noise_threshold = sample_node.noise_threshold
        margin = sample_node.margin
        print(f"[BakeWrangler]         采样节点: device={device}, samples={samples}, margin={margin}")
    else:
        device = "GPU"
        samples = 128
        use_denoising = True
        use_adaptive_sampling = False
        noise_threshold = 0.01
        margin = 16
        print(f"[BakeWrangler]         采样节点: (未连接，使用默认值)")

    tree_name = node.id_data.name if hasattr(node, 'id_data') and node.id_data else ""
    task = BakeTask(
        high_poly=hp,
        low_poly=lp,
        bake_type=node.bake_type,
        resolution=resolution,
        cage_extrusion=getattr(node, 'cage_extrusion', 0.1),
        max_ray_distance=getattr(node, 'max_ray_distance', 0.2),
        output_path=output_path,
        file_format=fmt,
        color_depth=depth,
        channel_name=channel_name,
        device=device,
        samples=samples,
        use_denoising=use_denoising,
        use_adaptive_sampling=use_adaptive_sampling,
        noise_threshold=noise_threshold,
        margin=margin,
        cache_key=f"{tree_name}/{node.name}/{resolution}" if tree_name else f"{node.name}/{resolution}",
    )
    print(f"[BakeWrangler]         生成任务: {task}")
    return task
