import bpy
import numpy as np
import os

from .task import BakeTask, CompositeTask

# 模块级烘焙缓存：同一 BakeChannel 节点 + 分辨率只烘焙一次
_BAKE_CACHE = {}

import struct
import zlib


def _write_png_direct(pixels_float, width, height, filepath, depth_str):
    """直接写 PNG 文件，完全绕过 Blender 的 float→byte 转换管道。
    Blender 的 img.save() 会对 float_buffer 图像做 alpha 预乘/反预乘处理，
    导致低 Alpha 像素的 RGB 被破坏（除以 Alpha 后 clamp 到 1.0）。
    此函数直接将浮点数组写入 16/8-bit PNG，不做任何色彩/Aplha 变换。"""
    bit_depth = 16 if depth_str == '16' else 8
    max_val = 65535 if bit_depth == 16 else 255

    # 将 float [0,1] 转为整数，逐行写入（含 PNG filter byte）
    raw_rows = bytearray()
    for y in range(height):
        raw_rows.append(0)  # filter: None
        row_start = y * width * 4
        for x in range(width):
            i = row_start + x * 4
            for c in range(4):
                v = int(round(max(0.0, min(1.0, pixels_float[i + c])) * max_val))
                if bit_depth == 16:
                    raw_rows.extend(struct.pack('>H', v))
                else:
                    raw_rows.append(v)

    def _png_chunk(ct, data):
        chunk = ct + data
        return struct.pack('>I', len(data)) + chunk + struct.pack('>I', zlib.crc32(chunk) & 0xffffffff)

    ihdr = struct.pack('>IIBBBBB', width, height, bit_depth, 6, 0, 0, 0)  # color_type=6 RGBA
    png = b'\x89PNG\r\n\x1a\n' + _png_chunk(b'IHDR', ihdr)
    png += _png_chunk(b'IDAT', zlib.compress(bytes(raw_rows)))
    png += _png_chunk(b'IEND', b'')

    with open(filepath, 'wb') as f:
        f.write(png)  # cache_key → img (Blender Image)，img_node 在首次清理时已销毁

def clear_bake_cache():
    """清除所有缓存的烘焙图像（在所有任务完成后调用）"""
    global _BAKE_CACHE
    for cache_key, img in list(_BAKE_CACHE.items()):
        try:
            if img and img.name in bpy.data.images:
                bpy.data.images.remove(img)
        except Exception:
            pass
    _BAKE_CACHE.clear()
    print("[BakeWrangler] 烘焙缓存已清除")

# 烘焙通道类型 → bpy.ops.object.bake(type=...) 参数
# DIFFUSE 和 METALLIC 通过 Emission 通道烘焙（Blender 无原生通道或原生通道受光照/金属度影响）
_BAKE_TYPE_MAP = {
    'NORMAL':    'NORMAL',
    'DIFFUSE':   'EMIT',
    'AO':        'AO',
    'ROUGHNESS': 'ROUGHNESS',
    'EMISSION':  'EMIT',
    'METALLIC':  'EMIT',
    'CURVATURE': 'COMBINED',
    'HEIGHT':    'COMBINED',
}

# 需要 Non-Color 色彩空间的通道
_NON_COLOR_CHANNELS = {'NORMAL', 'AO', 'ROUGHNESS', 'METALLIC', 'CURVATURE', 'HEIGHT', 'EMISSION'}


def _img_to_numpy(img):
    """Blender Image → NumPy (H, W, 4) float32 数组"""
    pixels = np.empty(len(img.pixels), dtype=np.float32)
    img.pixels.foreach_get(pixels)
    return pixels.reshape(img.size[1], img.size[0], 4)


def _numpy_to_new_image(arr, name, ref_img=None):
    """NumPy 数组 → 新 Blender Image，可选继承 ref_img 的色彩空间"""
    import array
    h, w = arr.shape[0], arr.shape[1]
    img = bpy.data.images.new(name=name, width=w, height=h, alpha=True, float_buffer=True)
    if ref_img is not None:
        img.colorspace_settings.name = ref_img.colorspace_settings.name
    # 关键：设为 CHANNEL_PACKED 防止 Blender 保存时做 alpha 预乘/反预乘处理
    # 否则 float_buffer 图像保存为 8/16-bit PNG 时会将 RGB 除以 Alpha，导致低 Alpha 像素变白
    img.alpha_mode = 'CHANNEL_PACKED'
    flat = arr.ravel()
    # 使用 array.array('f') 替代 numpy 数组，避免 Blender foreach_set 兼容性问题
    img.pixels.foreach_set(array.array('f', flat))

    # 验证写入正确性
    verify = np.empty(len(img.pixels), dtype=np.float32)
    img.pixels.foreach_get(verify)
    max_dev = float(np.abs(verify - flat).max())
    if max_dev > 0.0001:
        print(f"[BakeWrangler]   ⚠ foreach_set 验证失败！max_dev={max_dev:.6f}")
    return img


def validate_tasks(tasks):
    errors = []
    for task in tasks:
        errors.extend(task.validation_errors())
    return errors


def execute_single_task(task, tree=None):
    if isinstance(task, CompositeTask):
        _execute_composite(task)
    else:
        _execute_single(task, tree)



def _execute_composite(composite):
    """纯内存合成流水线：各源直接烘焙到 float 图像 → 内存合成 → 一次保存。
    完全消除中间 8-bit PNG 临时文件往返，避免色彩空间/量化误差。"""
    print(f"\n[BakeWrangler] ====== 开始合成任务: {composite.channel_name} =====")
    print(f"[BakeWrangler] 合成模式: {composite.combine_mode}")
    print(f"[BakeWrangler] 输入源: {[(sn, t.channel_name, t.bake_type) for sn, t in composite.sources]}")

    # 1. 统一所有源的分辨率（取最大值）
    max_res = max(t.resolution for _, t in composite.sources)
    for _, task in composite.sources:
        if task.resolution != max_res and task.cache_key:
            # 分辨率变更 → 更新缓存键（变更后无法复用原分辨率的缓存，这是正确的行为）
            parts = task.cache_key.rsplit('/', 1)
            task.cache_key = f"{parts[0]}/{max_res}"
        task.resolution = max_res
    print(f"[BakeWrangler] 统一分辨率: {max_res}")

    source_images = []
    temp_nodes = []
    result_img = None

    try:
        # 2. 所有源烘焙到内存（float 图像，不写磁盘）
        for socket_name, task in composite.sources:
            task.channel_name = f"{composite.channel_name}/{socket_name}"
            print(f"[BakeWrangler]   烘焙源 '{socket_name}' ({task.bake_type}, res={task.resolution})")
            img, img_node = _bake_task_image(task)
            source_images.append((socket_name, img, task.bake_type))
            temp_nodes.append((img, img_node, task))

        # 3. 内存合成（直接操作 float 图像，无磁盘往返）
        print(f"[BakeWrangler] 开始像素合成（纯内存）...")
        if composite.combine_mode == 'RGB_PLUS_A':
            result_img, composite_bake_type = _composite_rgb_plus_a(composite, source_images)
        elif composite.combine_mode == 'RGBA_SPLIT':
            result_img, composite_bake_type = _composite_rgba_split(composite, source_images)
        else:
            raise RuntimeError(f"未知合成模式: {composite.combine_mode}")

        # 4. 应用后期效果（内存内处理）
        if composite.post_effects:
            result_img = _apply_post_effects_in_memory(result_img, composite.post_effects)
            print(f"[BakeWrangler] 合成后期处理后像素: {[round(p, 4) for p in list(result_img.pixels[:8])]}")
        _set_image_colorspace(result_img, composite_bake_type)

        # 5. 保存最终结果
        _save_composite_image(result_img, composite, composite_bake_type)

    finally:
        # 6. 清理源烘焙的临时 float 图像（缓存图像保留）
        for img, img_node, task in temp_nodes:
            is_cached = task.cache_key and task.cache_key in _BAKE_CACHE
            _cleanup_bake_node(img, img_node, task, keep_image=is_cached)
        if result_img is not None:
            bpy.data.images.remove(result_img)

    # 7. 刷新场景贴图
    _refresh_texture(composite.output_path, composite_bake_type)
    print(f"[BakeWrangler] ====== 结束合成任务: {composite.channel_name} ======\n")



def _composite_rgb_plus_a(composite, source_images):
    """RGB_PLUS_A 模式: RGB 源的 RGB + A 源的明度 → 输出 RGBA（纯内存 NumPy 向量化）。
    source_images: [(socket_name, blender_image, bake_type), ...]"""
    rgb_img = None
    a_img = None
    rgb_bake_type = 'DIFFUSE'
    a_bake_type = 'AO'

    for socket_name, img, bake_type in source_images:
        if socket_name == 'RGB':
            rgb_img = img
            rgb_bake_type = bake_type
        elif socket_name == 'A':
            a_img = img
            a_bake_type = bake_type

    if rgb_img is None:
        raise RuntimeError("合成失败: 缺少 RGB 源")

    # 诊断：提取前检查色彩空间
    expected_cs = 'Non-Color' if rgb_bake_type in _NON_COLOR_CHANNELS else 'sRGB'
    cs_before = rgb_img.colorspace_settings.name
    print(f"[BakeWrangler]   RGB源色彩空间(提取前): '{cs_before}' (期望: '{expected_cs}')")
    cs_changed = _set_image_colorspace(rgb_img, rgb_bake_type)
    if not cs_changed and cs_before != expected_cs:
        print(f"[BakeWrangler]   ⚠⚠⚠ _set_image_colorspace 失败！色彩空间从 '{cs_before}' 变为 '{rgb_img.colorspace_settings.name}' - 像素可能已被重置！")
    w, h = rgb_img.size
    rgb_arr = _img_to_numpy(rgb_img)  # (H, W, 4)
    print(f"[BakeWrangler]   RGB 源: {w}×{h}, 前4像素={[round(v, 4) for v in rgb_arr[0, 0, :]]}")

    a_arr = None
    if a_img is not None:
        _set_image_colorspace(a_img, a_bake_type)
        aw, ah = a_img.size
        if aw == w and ah == h:
            a_arr = _img_to_numpy(a_img)  # (H, W, 4)
            print(f"[BakeWrangler]   A 源: {aw}×{ah}, 前4像素={[round(v, 4) for v in a_arr[0, 0, :]]}")
        else:
            print(f"[BakeWrangler]   ⚠ A 源尺寸与 RGB 源不同！将跳过 A 合成")

    # 向量化合成: RGB 直接复制，Alpha = A 源 BT.709 亮度 或 1.0
    out_rgb = rgb_arr[:, :, :3].copy()
    if a_arr is not None:
        out_a = 0.2126 * a_arr[:, :, 0] + 0.7152 * a_arr[:, :, 1] + 0.0722 * a_arr[:, :, 2]
    else:
        out_a = np.ones((h, w), dtype=np.float32)

    # 验证 RGB 通道未被 A 污染（向量化全图比对）
    max_rgb_diff = float(np.abs(out_rgb - rgb_arr[:, :, :3]).max())
    print(f"[BakeWrangler]   RGB 通道差异(最大值): {max_rgb_diff:.6f} (0=未被A污染)")

    # 构造输出 (H, W, 4)
    out_arr = np.dstack([out_rgb, out_a])

    result = _numpy_to_new_image(out_arr, f"_composite_{composite.channel_name}", rgb_img)
    _set_image_colorspace(result, rgb_bake_type)

    # 验证：读回 result 图像像素，与源 RGB 图像像素逐通道对比
    result_arr = _img_to_numpy(result)
    rgb_mismatch = float(np.abs(result_arr[:, :, :3] - rgb_arr[:, :, :3]).max())
    mismatched_pixels = int(np.sum(np.abs(result_arr[:, :, :3] - rgb_arr[:, :, :3]).max(axis=2) > 0.0001))
    total_pixels = h * w
    mid_y, mid_x = h // 2, w // 2
    print(f"[BakeWrangler]   合成结果前4像素(边角)={[round(v, 4) for v in out_arr[0, 0, :]]}")
    print(f"[BakeWrangler]   合成结果中心像素({mid_x},{mid_y})={[round(v, 4) for v in out_arr[mid_y, mid_x, :]]}")
    print(f"[BakeWrangler]   [验证] 合成后RGB vs 源RGB: max_diff={rgb_mismatch:.6f}, 不匹配像素={mismatched_pixels}/{total_pixels} ({100*mismatched_pixels/total_pixels:.2f}%)")
    if rgb_mismatch > 0.001:
        print(f"[BakeWrangler]   ⚠ 合成导致 RGB 通道改变！最大值差异={rgb_mismatch:.6f}")
    else:
        print(f"[BakeWrangler]   ✓ 合成后 RGB 通道完好无损")

    return result, rgb_bake_type



def _composite_rgba_split(composite, source_images):
    """RGBA_SPLIT 模式: 四个源的明度分别填入 R、G、B、A（纯内存 NumPy 向量化）。
    source_images: [(socket_name, blender_image, bake_type), ...]"""
    # 加载各源为 NumPy 数组并提取 BT.709 明度（全向量化）
    src_lum = {}
    w = h = 0
    for socket_name, img, bake_type in source_images:
        _set_image_colorspace(img, bake_type)
        arr = _img_to_numpy(img)  # (H, W, 4)
        lum = 0.2126 * arr[:, :, 0] + 0.7152 * arr[:, :, 1] + 0.0722 * arr[:, :, 2]
        src_lum[socket_name] = lum
        w, h = img.size

    if not src_lum:
        raise RuntimeError("合成失败: 没有输入源")

    # 色彩空间：任一源为 Non-Color 则结果为 Non-Color
    split_bake_type = 'DIFFUSE'
    for sn, t in composite.sources:
        split_bake_type = t.bake_type
        if t.bake_type in _NON_COLOR_CHANNELS:
            break

    # 向量化构建输出: 空缺通道补 0（A 通道补 1）
    out_r = src_lum.get('R', np.zeros((h, w), dtype=np.float32))
    out_g = src_lum.get('G', np.zeros((h, w), dtype=np.float32))
    out_b = src_lum.get('B', np.zeros((h, w), dtype=np.float32))
    out_a = src_lum.get('A', np.ones((h, w), dtype=np.float32))

    out_arr = np.stack([out_r, out_g, out_b, out_a], axis=-1)  # (H, W, 4)

    # 传入 ref_img 使色彩空间在像素写入前设置，避免 Blender 重置像素（参考 RGB+A 模式）
    ref_img = source_images[0][1]
    result = _numpy_to_new_image(out_arr, f"_composite_{composite.channel_name}", ref_img)
    _set_image_colorspace(result, split_bake_type)
    return result, split_bake_type



def _save_composite_image(img, composite, bake_type=None):
    """保存合成结果，与 _save_image 类似的逻辑"""
    scene = bpy.context.scene
    orig_format = scene.render.image_settings.file_format
    orig_color_mode = scene.render.image_settings.color_mode
    orig_color_depth = scene.render.image_settings.color_depth
    orig_compression = scene.render.image_settings.compression

    settings = scene.render.image_settings
    settings.file_format = composite.file_format
    settings.color_mode = 'RGBA'
    depth_map = {'8': '8', '16': '16', '32': '32'}
    settings.color_depth = depth_map.get(composite.color_depth, '8')

    # 提取压缩参数
    compress_params = None
    for effect in composite.post_effects:
        if effect.effect_type == 'COMPRESS':
            compress_params = effect.params
            break

    if composite.file_format == 'PNG':
        settings.compression = int(compress_params.get('compression', '15')) if compress_params else 15
    elif composite.file_format == 'EXR':
        settings.color_depth = '32'

    # 保存前验证并修正色彩空间
    if bake_type is not None:
        expected_cs = 'Non-Color' if bake_type in _NON_COLOR_CHANNELS else 'sRGB'
        if img.colorspace_settings.name != expected_cs:
            print(f"[BakeWrangler] ⚠ 合成保存前色彩空间不匹配：期望 '{expected_cs}'，实际 '{img.colorspace_settings.name}'，强制修正")
            try:
                img.colorspace_settings.name = expected_cs
            except TypeError:
                pass

    # 应用色彩量化（COMPRESS 效果）
    if compress_params and compress_params.get('quantization', 'NONE') != 'NONE':
        q_levels = {'256_COLORS': 8, '64_COLORS': 4, '16_COLORS': 2}
        levels = q_levels.get(compress_params['quantization'], 256)
        px = list(img.pixels)
        for i in range(0, len(px), 4):
            for c in range(3):
                px[i + c] = round(px[i + c] * (levels - 1)) / max(levels - 1, 1)
        img.pixels = px

    # 保存前记录完整像素用于诊断对比
    pre_save_all = list(img.pixels)
    pre_pixels = pre_save_all[:8]
    print(f"[BakeWrangler]   保存前像素: {[round(p, 4) for p in pre_pixels]}")
    print(f"[BakeWrangler]   图像属性: alpha_mode='{img.alpha_mode}', is_float={img.is_float}, colorspace='{img.colorspace_settings.name}'")

    if composite.file_format == 'PNG':
        # 直接写 PNG，绕过 Blender 的 float→byte 转换（会做 alpha 预乘/反预乘）
        _write_png_direct(pre_save_all, img.size[0], img.size[1], composite.output_path, composite.color_depth)
    else:
        img.save(filepath=composite.output_path)
    print(f"[BakeWrangler] 合成图像已保存到: {composite.output_path}")

    settings.file_format = orig_format
    settings.color_mode = orig_color_mode
    settings.color_depth = orig_color_depth
    settings.compression = orig_compression

    # 立即加载验证，并对比保存前后的浮点差异
    expected_cs = 'Non-Color' if (bake_type and bake_type in _NON_COLOR_CHANNELS) else 'sRGB'
    try:
        verify_img = bpy.data.images.load(composite.output_path)
        print(f"[BakeWrangler]   加载后图像属性: alpha_mode='{verify_img.alpha_mode}', is_float={verify_img.is_float}, colorspace='{verify_img.colorspace_settings.name}'")
        if bake_type:
            _set_image_colorspace(verify_img, bake_type)
        else:
            _set_image_colorspace(verify_img, 'DIFFUSE')
        print(f"[BakeWrangler]   色彩空间修正后: colorspace='{verify_img.colorspace_settings.name}', alpha_mode='{verify_img.alpha_mode}'")
        verify_all = list(verify_img.pixels)
        verify_pixels = verify_all[:8]
        print(f"[BakeWrangler]   加载验证像素: {[round(p, 4) for p in verify_pixels]}")

        # 诊断：逐像素对比保存前后的浮点差异
        if len(pre_save_all) == len(verify_all):
            max_fdiff = 0.0
            max_fdiff_idx = 0
            diff_count = 0
            w_img = img.size[0]
            for i in range(len(pre_save_all)):
                d = abs(pre_save_all[i] - verify_all[i])
                if d > max_fdiff:
                    max_fdiff = d
                    max_fdiff_idx = i
                if d > 0.0001:
                    diff_count += 1
            total = len(pre_save_all)
            total_px = total // 4
            print(f"[BakeWrangler]   [诊断] 保存往返差异: max={max_fdiff:.6f}, 差异浮点值={diff_count}/{total} ({100*diff_count/total:.2f}%)")
            if max_fdiff > 0.001:
                # 定位差异最大的像素
                px_idx = max_fdiff_idx // 4
                px_x = px_idx % w_img
                px_y = px_idx // w_img
                ch = max_fdiff_idx % 4
                ch_names = ['R', 'G', 'B', 'A']
                pre_px = pre_save_all[px_idx*4:px_idx*4+4]
                post_px = verify_all[px_idx*4:px_idx*4+4]
                print(f"[BakeWrangler]   [诊断] ⚠ 最大差异位置: 像素({px_x},{px_y}) {ch_names[ch]}通道")
                print(f"[BakeWrangler]   [诊断]    保存前: {[round(v,6) for v in pre_px]}")
                print(f"[BakeWrangler]   [诊断]    加载后: {[round(v,6) for v in post_px]}")
                # 再找10个差异最大的像素
                pixel_diffs = []
                for pi in range(total_px):
                    base = pi * 4
                    pd = max(abs(pre_save_all[base+c] - verify_all[base+c]) for c in range(4))
                    pixel_diffs.append((pd, pi))
                pixel_diffs.sort(reverse=True)
                print(f"[BakeWrangler]   [诊断] 差异最大的10个像素 (保存前 → 加载后):")
                for pd, pi in pixel_diffs[:10]:
                    x, y = pi % w_img, pi // w_img
                    pre = [round(v,4) for v in pre_save_all[pi*4:pi*4+4]]
                    post = [round(v,4) for v in verify_all[pi*4:pi*4+4]]
                    print(f"[BakeWrangler]     ({x:4d},{y:4d}) {pre} → {post} diff={pd:.4f}")
            else:
                print(f"[BakeWrangler]   [诊断] ✓ 保存往返精度正常 (max_diff <= 0.001)")
        bpy.data.images.remove(verify_img)
    except Exception as e:
        print(f"[BakeWrangler]   加载验证失败: {e}")

    # 检查文件
    try:
        import os
        file_size = os.path.getsize(composite.output_path)
        with open(composite.output_path, 'rb') as f:
            header = f.read(8)
        print(f"[BakeWrangler]   文件大小: {file_size} bytes, 文件头(hex): {header.hex()}")
    except Exception as e:
        print(f"[BakeWrangler]   文件检查失败: {e}")


def _apply_post_effects_in_memory(img, post_effects):
    """对内存中的 float_buffer 图像依次应用后期效果，返回处理后图像。
    注意：会移除传入的 img 并返回新图像（与各 _post_* 函数的行为一致）。"""
    if not post_effects:
        return img

    print(f"[BakeWrangler] 应用 {len(post_effects)} 个后期效果（内存内处理）...")

    for i, effect in enumerate(post_effects):
        print(f"[BakeWrangler]   [{i+1}] {effect.effect_type} {effect.params}")
        if effect.effect_type == 'ANTIALIAS':
            img = _post_antialias(img, effect.params)
        elif effect.effect_type == 'SCALE':
            img = _post_scale(img, effect.params)
        elif effect.effect_type == 'MATH':
            img = _post_math(img, effect.params)
        elif effect.effect_type == 'DENOISE':
            img = _post_denoise(img, effect.params)
        elif effect.effect_type == 'COMPRESS':
            pass  # 压缩在保存时处理

    print(f"[BakeWrangler] 后期效果应用完成")
    return img


def _post_antialias(img, params):
    algorithm = params.get('algorithm', 'FXAA')
    arr = _img_to_numpy(img)
    rgb = arr[:, :, :3].copy()
    alpha = arr[:, :, 3].copy()

    if algorithm == 'FXAA':
        # 亮度计算（向量化）
        lum = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
        # 邻域亮度（使用 np.roll 进行环形边界，但我们需要 clamp 边界）
        # 使用 pad + slice 实现 clamp 边界
        lum_pad = np.pad(lum, 1, mode='edge')
        lum_n = lum_pad[:-2, 1:-1]  # 北
        lum_s = lum_pad[2:, 1:-1]   # 南
        lum_e = lum_pad[1:-1, 2:]   # 东
        lum_w = lum_pad[1:-1, :-2]  # 西
        edge_h = np.abs(lum_n - lum_s)
        edge_v = np.abs(lum_e - lum_w)
        blend = np.minimum(0.5, np.maximum(edge_h, edge_v) * 2.0)

        # 5 像素平均（clamp 边界）
        rgb_pad = np.pad(rgb, ((1, 1), (1, 1), (0, 0)), mode='edge')
        rgb_avg = (rgb_pad[:-2, 1:-1, :] + rgb_pad[2:, 1:-1, :] +
                   rgb_pad[1:-1, 2:, :] + rgb_pad[1:-1, :-2, :] +
                   rgb) / 5.0

        # 混合：仅在 blend > 0.05 时混合
        mask = blend[:, :, np.newaxis] > 0.05
        blend3 = blend[:, :, np.newaxis]
        rgb = np.where(mask, rgb + (rgb_avg - rgb) * blend3, rgb)

    elif 'GAUSS' in algorithm:
        sigma = 0.7 if '3X3' in algorithm else 1.2
        size = 3 if '3X3' in algorithm else 5
        kernel = _make_gaussian_kernel_2d(size, sigma)
        for c in range(3):
            rgb[:, :, c] = _convolve2d_clamp(rgb[:, :, c], kernel)
    else:
        # Box blur
        size = 3 if '3X3' in algorithm else 5
        kernel = np.ones((size, size), dtype=np.float32) / (size * size)
        for c in range(3):
            rgb[:, :, c] = _convolve2d_clamp(rgb[:, :, c], kernel)

    arr[:, :, :3] = rgb
    arr[:, :, 3] = alpha
    out = _numpy_to_new_image(arr, "_post_aa", img)
    bpy.data.images.remove(img)
    return out


def _make_gaussian_kernel_2d(size, sigma):
    """生成 2D 高斯核"""
    ax = np.arange(-(size // 2), size // 2 + 1, dtype=np.float32)
    gx = np.exp(-0.5 * (ax / sigma) ** 2)
    kernel = np.outer(gx, gx)
    return kernel / kernel.sum()


def _convolve2d_clamp(arr, kernel):
    """2D 卷积，clamp 边界处理。使用 sliding_window_view 避免 Python 循环。"""
    kh, kw = kernel.shape
    half_h, half_w = kh // 2, kw // 2
    padded = np.pad(arr, ((half_h, half_h), (half_w, half_w)), mode='edge')
    windows = np.lib.stride_tricks.sliding_window_view(padded, (kh, kw))
    return np.tensordot(windows, kernel, axes=([2, 3], [0, 1]))


def _median_filter_clamp(arr, size):
    """中值滤波，clamp 边界处理。使用 sliding_window_view 避免 Python 循环。"""
    half = size // 2
    padded = np.pad(arr, half, mode='edge')
    windows = np.lib.stride_tricks.sliding_window_view(padded, (size, size))
    h, w = arr.shape
    return np.median(windows.reshape(h, w, size * size), axis=2)


def _post_scale(img, params):
    algorithm = params.get('algorithm', 'BILINEAR')
    target_res = params.get('target_resolution', 1024)
    src_arr = _img_to_numpy(img)
    w, h = img.size
    t = target_res

    # 源坐标网格
    fx = np.arange(t, dtype=np.float32) * w / t
    fy = np.arange(t, dtype=np.float32) * h / t
    fx_grid, fy_grid = np.meshgrid(fx, fy, indexing='ij')

    if algorithm == 'NEAREST':
        sx = np.clip(np.round(fx_grid).astype(np.int32), 0, w - 1)
        sy = np.clip(np.round(fy_grid).astype(np.int32), 0, h - 1)
        out_arr = src_arr[sy, sx, :]

    elif algorithm == 'BILINEAR':
        x0 = np.clip(np.floor(fx_grid).astype(np.int32), 0, w - 1)
        y0 = np.clip(np.floor(fy_grid).astype(np.int32), 0, h - 1)
        x1 = np.clip(x0 + 1, 0, w - 1)
        y1 = np.clip(y0 + 1, 0, h - 1)
        dx = fx_grid - x0
        dy = fy_grid - y0
        dx = dx[:, :, np.newaxis]
        dy = dy[:, :, np.newaxis]
        v00 = src_arr[y0, x0, :]
        v10 = src_arr[y0, x1, :]
        v01 = src_arr[y1, x0, :]
        v11 = src_arr[y1, x1, :]
        out_arr = (v00 * (1 - dx) + v10 * dx) * (1 - dy) + (v01 * (1 - dx) + v11 * dx) * dy

    elif algorithm in ('BICUBIC', 'MITCHELL', 'LANCZOS'):
        # 确定滤波器参数
        if algorithm == 'BICUBIC':
            weight_fn = _cubic_weight
            radius = 2
        elif algorithm == 'MITCHELL':
            weight_fn = _mitchell_weight
            radius = 2
        else:  # LANCZOS
            weight_fn = _lanczos_weight
            radius = 3

        xi = np.floor(fx_grid).astype(np.int32)
        yi = np.floor(fy_grid).astype(np.int32)
        dx = fx_grid - xi
        dy = fy_grid - yi
        out_arr = np.zeros((t, t, 4), dtype=np.float32)

        for m in range(-radius + 1, radius + 1):
            for n in range(-radius + 1, radius + 1):
                sx = np.clip(xi + m, 0, w - 1)
                sy = np.clip(yi + n, 0, h - 1)
                wx = weight_fn(m - dx)
                wy = weight_fn(n - dy)
                w = wx * wy
                out_arr += src_arr[sy, sx, :] * w[:, :, np.newaxis]

        out_arr = np.clip(out_arr, 0.0, 1.0)

    out = _numpy_to_new_image(out_arr, "_post_scale", img)
    bpy.data.images.remove(img)
    return out


def _cubic_weight(t):
    """Catmull-Rom 双三次权重 — 兼容标量和 NumPy 数组"""
    t = np.abs(t)
    w = np.zeros_like(t)
    mask1 = t < 1.0
    mask2 = (t >= 1.0) & (t < 2.0)
    w[mask1] = 1.5 * t[mask1] ** 3 - 2.5 * t[mask1] ** 2 + 1.0
    w[mask2] = -0.5 * t[mask2] ** 3 + 2.5 * t[mask2] ** 2 - 4.0 * t[mask2] + 2.0
    return w


def _lanczos_weight(t, a=3):
    """Lanczos 窗函数权重 (默认 a=3) — 兼容标量和 NumPy 数组"""
    t = np.abs(t)
    w = np.zeros_like(t)
    mask_center = t < 0.0001
    mask_valid = (t >= 0.0001) & (t < a)
    w[mask_center] = 1.0
    pi_t = np.pi * t[mask_valid]
    pi_ta = pi_t / a
    w[mask_valid] = (np.sin(pi_t) / pi_t) * (np.sin(pi_ta) / pi_ta)
    return w


def _mitchell_weight(t):
    """Mitchell-Netravali 权重 (B=1/3, C=1/3) — 兼容标量和 NumPy 数组"""
    t = np.abs(t)
    w = np.zeros_like(t)
    tt = t * t
    mask1 = t < 1.0
    mask2 = (t >= 1.0) & (t < 2.0)
    w[mask1] = (7.0 * tt[mask1] * t[mask1] - 12.0 * tt[mask1] + 16.0 / 3.0) / 6.0
    w[mask2] = (-7.0 / 3.0 * tt[mask2] * t[mask2] + 12.0 * tt[mask2] - 20.0 * t[mask2] + 32.0 / 3.0) / 6.0
    return w


def _post_math(img, params):
    operation = params.get('operation', 'MULTIPLY')
    arr = _img_to_numpy(img)

    # BT.709 线性亮度 — 像素数据为 float_buffer 存储的线性值，无需色彩空间转换
    lum = 0.2126 * arr[:, :, 0] + 0.7152 * arr[:, :, 1] + 0.0722 * arr[:, :, 2]

    if operation == 'NORMALIZE':
        lmin, lmax = lum.min(), lum.max()
        rng = lmax - lmin
        if rng < 0.0001:
            lum.fill(0.5)
        else:
            np.subtract(lum, lmin, out=lum)
            np.divide(lum, rng, out=lum)
    elif operation == 'MULTIPLY':
        lum *= params.get('factor', 1.0)
    elif operation == 'ADD':
        lum += params.get('factor', 0.0)
    elif operation == 'SUBTRACT':
        lum -= params.get('factor', 0.0)
    elif operation == 'POWER':
        np.power(lum, params.get('factor', 1.0), out=lum)
    elif operation == 'GREATER_THAN':
        lum[:] = lum > params.get('threshold', 0.5)
    elif operation == 'LESS_THAN':
        lum[:] = lum < params.get('threshold', 0.5)
    elif operation == 'CLAMP':
        lo = params.get('clamp_min', 0.0)
        hi = params.get('clamp_max', 1.0)
        np.clip(lum, min(lo, hi), max(lo, hi), out=lum)
    elif operation == 'MAP_RANGE':
        src_min = params.get('clamp_min', 0.0)
        src_max = params.get('clamp_max', 1.0)
        rng = src_max - src_min
        if abs(rng) < 0.0001:
            lum.fill(0.0)
        else:
            np.subtract(lum, src_min, out=lum)
            np.divide(lum, rng, out=lum)
    elif operation == 'INVERT':
        np.subtract(1.0, lum, out=lum)

    np.clip(lum, 0.0, 1.0, out=lum)
    arr[:, :, 0] = lum
    arr[:, :, 1] = lum
    arr[:, :, 2] = lum

    out = _numpy_to_new_image(arr, "_post_math", img)
    bpy.data.images.remove(img)
    return out


def _post_denoise(img, params):
    algorithm = params.get('algorithm', 'BILATERAL_3X3')
    arr = _img_to_numpy(img)
    rgb = arr[:, :, :3].copy()
    alpha = arr[:, :, 3].copy()
    h, w = arr.shape[0], arr.shape[1]

    if 'MEDIAN' in algorithm:
        size = 3 if '3X3' in algorithm else 5
        for c in range(3):
            rgb[:, :, c] = _median_filter_clamp(rgb[:, :, c], size)

    elif 'BILATERAL' in algorithm:
        size = 3 if '3X3' in algorithm else 5
        half = size // 2
        sigma_r = 0.1
        sigma_s = float(half) / 2.0
        two_sr2 = 2.0 * sigma_r * sigma_r
        two_ss2 = 2.0 * sigma_s * sigma_s

        # 预计算空间权重
        dy_arr, dx_arr = np.mgrid[-half:half + 1, -half:half + 1]
        spatial_dist = (dx_arr * dx_arr + dy_arr * dy_arr) / two_ss2
        spatial_weight = np.exp(-spatial_dist).astype(np.float32)  # (size, size)

        # 对 RGB 三通道分别处理
        for c in range(3):
            channel = rgb[:, :, c]  # (H, W)

            # 使用 np.pad 处理边界 (clamp/edge mode)
            padded = np.pad(channel, half, mode='edge')  # (H+2*half, W+2*half)

            sum_val = np.zeros_like(channel)
            sum_w = np.zeros_like(channel)

            for dy in range(size):
                for dx in range(size):
                    # 提取偏移后的邻域
                    neighbor = padded[dy:dy + h, dx:dx + w]
                    # 颜色距离
                    color_dist = np.square(channel - neighbor) / two_sr2
                    weight = spatial_weight[dy, dx] * np.exp(-color_dist)
                    sum_val += neighbor * weight
                    sum_w += weight

            rgb[:, :, c] = np.where(sum_w > 0, sum_val / sum_w, channel)

    elif 'GAUSSIAN' in algorithm:
        sigma = 0.7 if '3X3' in algorithm else 1.2
        size = 3 if '3X3' in algorithm else 5
        kernel = _make_gaussian_kernel_2d(size, sigma)
        for c in range(3):
            rgb[:, :, c] = _convolve2d_clamp(rgb[:, :, c], kernel)

    arr[:, :, :3] = rgb
    arr[:, :, 3] = alpha
    out = _numpy_to_new_image(arr, "_post_denoise", img)
    bpy.data.images.remove(img)
    return out


def _get_bake_kwargs(task, bake_type):
    kwargs = {
        'type': bake_type,
        'use_selected_to_active': True,
        'cage_extrusion': task.cage_extrusion,
        'max_ray_distance': task.max_ray_distance,
        'margin': task.margin,
        'use_clear': True,
        'target': 'IMAGE_TEXTURES',
    }
    if bake_type == 'NORMAL':
        kwargs['normal_space'] = 'TANGENT'
    if bake_type == 'COMBINED':
        # 不设置 pass_filter，让 Blender 使用默认的全通道组合
        # 否则会报错"需要启用自发光，或启用直接/间接光贡献的通道"
        kwargs['pass_filter'] = {'COLOR', 'DIRECT', 'INDIRECT', 'EMIT'}
    return kwargs


def _pre_bake_check(task):
    lp = task.low_poly
    if lp.type == 'MESH' and lp.data.uv_layers:
        uv = lp.data.uv_layers.active
        if uv:
            print(f"[BakeWrangler]   UV 贴图: '{uv.name}', 需要确保 UV 无重叠")
        else:
            print(f"[BakeWrangler]   ⚠ 低模无活跃 UV 贴图！")
    else:
        print(f"[BakeWrangler]   ⚠ 低模没有 UV 数据！烘焙需要 UV 贴图")
    hp_bb = task.high_poly.bound_box
    lp_bb = task.low_poly.bound_box
    print(f"[BakeWrangler]   hp bounding_box: {[[round(v, 4) for v in c] for c in hp_bb]}")
    print(f"[BakeWrangler]   lp bounding_box: {[[round(v, 4) for v in c] for c in lp_bb]}")


def _bake_task_image(task):
    """纯内存烘焙：执行 Cycles bake 并返回 float 图像（不写磁盘）。
    返回 (img, img_node)，调用者负责清理 img_node 和 img。
    相同 cache_key 的任务只烘焙一次，后续直接复用。"""
    # 检查缓存
    if task.cache_key and task.cache_key in _BAKE_CACHE:
        cached_img = _BAKE_CACHE[task.cache_key]
        if cached_img and cached_img.name in bpy.data.images:
            print(f"\n[BakeWrangler] ====== 复用缓存烘焙: {task.channel_name} (key={task.cache_key}) =====")
            print(f"[BakeWrangler]   缓存图像: name={cached_img.name}, size={cached_img.size[0]}x{cached_img.size[1]}")
            return cached_img, None  # img_node 已在首次清理时销毁，无需再清理
        else:
            del _BAKE_CACHE[task.cache_key]
            print(f"[BakeWrangler] 缓存失效，重新烘焙: {task.cache_key}")

    scene = bpy.context.scene
    bake_type = _BAKE_TYPE_MAP.get(task.bake_type, 'COMBINED')

    print(f"\n[BakeWrangler] ====== 开始烘焙任务: {task.channel_name} =====")
    print(f"[BakeWrangler] task 详情: {task}")
    print(f"[BakeWrangler] bake_type 参数: {bake_type}")

    # ── 1. 渲染引擎 ──
    print(f"[BakeWrangler] 切换渲染引擎 -> CYCLES (当前: {scene.render.engine})")
    scene.render.engine = 'CYCLES'
    scene.cycles.device = task.device
    print(f"[BakeWrangler] Cycles device 设置为: {scene.cycles.device}")

    # ── 2. 采样设置 ──
    scene.cycles.samples = task.samples
    scene.cycles.use_denoising = task.use_denoising
    scene.cycles.use_adaptive_sampling = task.use_adaptive_sampling
    if task.use_adaptive_sampling:
        scene.cycles.adaptive_threshold = task.noise_threshold

    # ── 3. 准备烘焙目标 ──
    print(f"[BakeWrangler] 准备 bake target...")
    img, img_node = _prepare_bake_target(task)
    print(f"[BakeWrangler] 临时图像: name={img.name}, size={img.size[0]}x{img.size[1]}, float={img.is_float}")
    print(f"[BakeWrangler] 图像节点: {img_node.name}, 材质: {img_node.id_data.name}")

    # ── 4. 选物体 ──
    print(f"[BakeWrangler] 选择物体: hp={task.high_poly.name}, lp={task.low_poly.name}")
    print(f"[BakeWrangler]   hp type={task.high_poly.type}, lp type={task.low_poly.type}")
    print(f"[BakeWrangler]   hp visible={not task.high_poly.hide_viewport}, lp visible={not task.low_poly.hide_viewport}")
    bpy.ops.object.select_all(action='DESELECT')
    task.high_poly.select_set(True)
    task.low_poly.select_set(True)
    bpy.context.view_layer.objects.active = task.low_poly
    print(f"[BakeWrangler]   选中物体数: {len(bpy.context.selected_objects)}, active={bpy.context.view_layer.objects.active.name}")
    print(f"[BakeWrangler]   selected: {[o.name for o in bpy.context.selected_objects]}")

    # ── 5. 执行前校验 ──
    _pre_bake_check(task)

    # ── 6. 材质覆写：将 PBR 通道值路由到 Emission 再烘焙（避免光照/金属度干扰）──
    restore_material = None
    if task.bake_type in ('METALLIC', 'DIFFUSE'):
        print(f"[BakeWrangler] {task.bake_type} 烘焙: 修改高模材质...")
        restore_material = _override_material_emit(task.high_poly, task.bake_type)

    try:
        # ── 7. 执行烘焙 ──
        kwargs = _get_bake_kwargs(task, bake_type)
        print(f"[BakeWrangler] 调用 bpy.ops.object.bake({ {k: v for k, v in kwargs.items()} })")
        bpy.ops.object.bake(**kwargs)
        print(f"[BakeWrangler] bake() 返回成功")

        # ── 8. 刷新图像 ──
        img.update()

        # ── 9. 检查烘焙后图像像素 ──
        _check_image_pixels(img)

        # ── 10. 应用后期效果（内存内处理，避免 PNG 往返导致色彩空间失真）──
        if task.post_effects:
            img = _apply_post_effects_in_memory(img, task.post_effects)
            _set_image_colorspace(img, task.bake_type)
            print(f"[BakeWrangler] 后期处理后像素: {[round(p, 4) for p in list(img.pixels[:8])]}")

        # 诊断：确认烘焙后图像色彩空间
        expected_cs = 'Non-Color' if task.bake_type in _NON_COLOR_CHANNELS else 'sRGB'
        actual_cs = img.colorspace_settings.name
        print(f"[BakeWrangler] 烘焙后色彩空间: '{actual_cs}' (期望: '{expected_cs}')")
        if actual_cs != expected_cs:
            print(f"[BakeWrangler] ⚠⚠⚠ 色彩空间不匹配！像素数据可能在后续 _set_image_colorspace 调用中被 Blender 重置！")

        # 存入缓存，供后续任务复用（只存 img，img_node 会在 cleanup 时被销毁）
        if task.cache_key:
            _BAKE_CACHE[task.cache_key] = img
            print(f"[BakeWrangler] 已缓存烘焙结果: key={task.cache_key}")

        return img, img_node

    finally:
        # 恢复高模材质
        if restore_material:
            restore_material()


def _cleanup_bake_node(img, img_node, task, keep_image=False):
    """清除烘焙过程中创建的临时材质节点和图像。
    keep_image=True 时只移除材质节点，保留图像（用于缓存复用）。
    img_node 可以为 None（从缓存复用时节点已被销毁）。"""
    if img_node is not None and task.low_poly.data.materials:
        mat = task.low_poly.data.materials[0]
        if mat and mat.use_nodes:
            nodes = mat.node_tree.nodes
            if img_node.name in nodes:
                nodes.remove(img_node)
    if not keep_image:
        if img.name in bpy.data.images:
            bpy.data.images.remove(img)


def _execute_single(task, tree=None):
    """完整烘焙流程：烘焙 → 保存 → 刷新 → 清理"""
    img, img_node = _bake_task_image(task)

    # ── 保存 ──
    print(f"[BakeWrangler] 色彩空间: {img.colorspace_settings.name}")
    _save_image(img, task)
    print(f"[BakeWrangler] 图像已保存到: {task.output_path}")

    # ── 刷新场景贴图 ──
    _refresh_texture(task.output_path, task.bake_type)

    # ── 清理 ──
    is_cached = task.cache_key and task.cache_key in _BAKE_CACHE
    _cleanup_bake_node(img, img_node, task, keep_image=is_cached)
    if is_cached:
        print(f"[BakeWrangler]   图像保留在缓存中，供后续任务复用")
    print(f"[BakeWrangler] ====== 结束烘焙任务: {task.channel_name} ======\n")



def _check_image_pixels(img):
    """检查图像是否有非零像素数据"""
    print(f"[BakeWrangler] 检查烘焙结果像素...")
    try:
        # 获取像素数据（flatten 的浮点列表，每个像素 4 个值 RGBA）
        pixels = list(img.pixels[:16])  # 取前 4 个像素
        has_data = any(abs(p) > 0.0001 for p in pixels)
        if has_data:
            # 找到有数据的样本像素
            nonzero = [p for p in pixels if abs(p) > 0.0001]
            print(f"[BakeWrangler]   ✓ 图像包含数据！前4像素={pixels[:8]}... (非零值={len(nonzero)}个)")
        else:
            # 检查更多像素
            all_pixels = list(img.pixels)
            max_val = max(all_pixels) if all_pixels else 0
            min_val = min(all_pixels) if all_pixels else 0
            nonzero_total = sum(1 for p in all_pixels if abs(p) > 0.0001)
            total = len(all_pixels)
            print(f"[BakeWrangler]   ✗ 图像可能为纯黑！total_pixels={total}, nonzero={nonzero_total}, min={min_val:.6f}, max={max_val:.6f}")
    except Exception as e:
        print(f"[BakeWrangler]   像素检查异常: {e}")


def _set_image_colorspace(img, bake_type):
    """设置图像色彩空间并验证。失败时记录警告。
    注意：在已有像素数据的 float_buffer 图像上重复设置色彩空间（即使是相同值）
    会触发 Blender 内部像素缓冲区重置，必须跳过已匹配的情况。"""
    cs = 'Non-Color' if bake_type in _NON_COLOR_CHANNELS else 'sRGB'
    if img.colorspace_settings.name == cs:
        return True  # 已是目标色彩空间，跳过以避免像素数据被重置
    # 诊断：记录变更前的状态
    old_cs = img.colorspace_settings.name
    img_size = img.size[0] * img.size[1]
    has_data = False
    if img_size > 0:
        try:
            px_sample = list(img.pixels[:4])
            has_data = any(abs(v) > 0.0001 for v in px_sample)
        except Exception:
            pass
    if has_data and img.is_float:
        print(f"[BakeWrangler] ⚠⚠⚠ 即将在已有像素数据的 float 图像上变更色彩空间: '{old_cs}' -> '{cs}'")
        print(f"[BakeWrangler] ⚠⚠⚠ 像素数据可能被 Blender 内部重置！图像: '{img.name}', size={img.size[0]}x{img.size[1]}")
    try:
        img.colorspace_settings.name = cs
        if has_data and img.is_float:
            # 验证像素是否被重置
            px_after = list(img.pixels[:4])
            still_has_data = any(abs(v) > 0.0001 for v in px_after)
            if not still_has_data:
                print(f"[BakeWrangler] ⚠⚠⚠ 确认：像素数据已被重置！变更前={px_sample[:4]}, 变更后={px_after[:4]}")
    except TypeError:
        print(f"[BakeWrangler] ⚠ 无法设置色彩空间为 '{cs}'，当前 OCIO 配置可能不支持该名称")
        return False
    if img.colorspace_settings.name != cs:
        print(f"[BakeWrangler] ⚠ 色彩空间设置不匹配：期望 '{cs}'，实际 '{img.colorspace_settings.name}'")
        return False
    return True


def _save_image(img, task):
    scene = bpy.context.scene
    orig_format = scene.render.image_settings.file_format
    orig_color_mode = scene.render.image_settings.color_mode
    orig_color_depth = scene.render.image_settings.color_depth
    orig_compression = scene.render.image_settings.compression

    # 保存前验证像素
    pre_pixels = list(img.pixels[:8])
    print(f"[BakeWrangler]   保存前像素: {[round(p, 4) for p in pre_pixels]}")

    settings = scene.render.image_settings
    settings.file_format = task.file_format
    settings.color_mode = 'RGBA'
    depth_map = {'8': '8', '16': '16', '32': '32'}
    settings.color_depth = depth_map.get(task.color_depth, '8')

    # 提取压缩参数
    compress_params = None
    for effect in task.post_effects:
        if effect.effect_type == 'COMPRESS':
            compress_params = effect.params
            break

    if task.file_format == 'PNG':
        settings.compression = int(compress_params.get('compression', '15')) if compress_params else 15
    elif task.file_format == 'EXR':
        settings.color_depth = '32'

    # 保存前验证并修正色彩空间
    expected_cs = 'Non-Color' if task.bake_type in _NON_COLOR_CHANNELS else 'sRGB'
    if img.colorspace_settings.name != expected_cs:
        print(f"[BakeWrangler] ⚠ 保存前色彩空间不匹配：期望 '{expected_cs}'，实际 '{img.colorspace_settings.name}'，强制修正")
        try:
            img.colorspace_settings.name = expected_cs
        except TypeError:
            pass

    # 应用色彩量化（COMPRESS 效果）
    if compress_params and compress_params.get('quantization', 'NONE') != 'NONE':
        q_levels = {'256_COLORS': 8, '64_COLORS': 4, '16_COLORS': 2}
        levels = q_levels.get(compress_params['quantization'], 256)
        px = list(img.pixels)
        for i in range(0, len(px), 4):
            for c in range(3):
                px[i + c] = round(px[i + c] * (levels - 1)) / max(levels - 1, 1)
        img.pixels = px

    img.save(filepath=task.output_path)

    # 恢复原始设置
    settings.file_format = orig_format
    settings.color_mode = orig_color_mode
    settings.color_depth = orig_color_depth
    settings.compression = orig_compression

    # 立即加载验证
    import os
    try:
        verify_img = bpy.data.images.load(task.output_path)
        _set_image_colorspace(verify_img, task.bake_type)
        verify_pixels = list(verify_img.pixels[:8])
        print(f"[BakeWrangler]   加载验证像素: {[round(p, 4) for p in verify_pixels]}")
        bpy.data.images.remove(verify_img)
    except Exception as e:
        print(f"[BakeWrangler]   加载验证失败: {e}")

    # 同时用 raw 方式读取文件前几个字节
    try:
        file_size = os.path.getsize(task.output_path)
        with open(task.output_path, 'rb') as f:
            header = f.read(8)
        print(f"[BakeWrangler]   文件大小: {file_size} bytes, 文件头(hex): {header.hex()}")
    except Exception as e:
        print(f"[BakeWrangler]   文件检查失败: {e}")


def _refresh_texture(filepath, bake_type):
    import os
    # 统一为正斜杠，兼容 Blender 内部路径表示和 Windows 反斜杠
    filepath = os.path.normpath(filepath).replace('\\', '/')

    existing = None
    for img in bpy.data.images:
        if img.filepath:
            img_path = os.path.normpath(bpy.path.abspath(img.filepath)).replace('\\', '/')
            if img_path == filepath:
                existing = img
                break

    if existing:
        existing.reload()
        _set_image_colorspace(existing, bake_type)
        print(f"[BakeWrangler]   刷新已有贴图: '{existing.name}', size={existing.size[0]}x{existing.size[1]}")
    else:
        try:
            new_img = bpy.data.images.load(filepath)
            print(f"[BakeWrangler]   加载新贴图: '{new_img.name}', size={new_img.size[0]}x{new_img.size[1]}")
            _set_image_colorspace(new_img, bake_type)
        except RuntimeError as e:
            print(f"[BakeWrangler]   ⚠ 贴图加载失败: {e}")


def _prepare_bake_target(task):
    low_poly = task.low_poly
    if low_poly.type != 'MESH':
        raise RuntimeError(f"低模 '{low_poly.name}' 不是网格物体")

    mesh = low_poly.data
    if len(mesh.materials) == 0:
        mat = bpy.data.materials.new(name=f"BakeMat_{low_poly.name}")
        mesh.materials.append(mat)
    else:
        mat = mesh.materials[0]

    if not mat.use_nodes:
        mat.use_nodes = True

    nodes = mat.node_tree.nodes

    is_float = True  # 始终使用 float 缓冲，避免 8-bit 色彩空间过早编码
    img = bpy.data.images.new(
        name=f"_bake_temp_{task.channel_name}",
        width=task.resolution,
        height=task.resolution,
        alpha=True,
        float_buffer=is_float,
    )
    img.alpha_mode = 'CHANNEL_PACKED'  # 防止保存时 alpha 预乘/反预乘破坏数据
    _set_image_colorspace(img, task.bake_type)

    img_node = nodes.new(type='ShaderNodeTexImage')
    img_node.image = img
    img_node.select = True
    nodes.active = img_node

    return img, img_node


def _override_material_emit(hp_obj, bake_type):
    """修改高模材质：将指定 PBR 通道路由到 Emission，返回恢复回调。
    METALLIC: 将 Metallic 值路由到 Emission Color
    DIFFUSE:  将 Base Color 路由到 Emission Color
    Blender 无原生 Metallic 通道，且 DIFFUSE 通道受金属度和光照影响会产生错误结果。"""
    # 需要覆写的通道 → Principled BSDF 输入 socket 名称
    _OVERRIDE_SOCKET = {
        'METALLIC': 'Metallic',
        'DIFFUSE':  'Base Color',
    }

    socket_name = _OVERRIDE_SOCKET.get(bake_type)
    if socket_name is None:
        return lambda: None

    restore_ops = []
    node_label = f'_BW_Emit_{bake_type}'

    if hp_obj.type != 'MESH':
        return lambda: None

    for slot_idx, mat_slot in enumerate(hp_obj.material_slots):
        mat = mat_slot.material
        if mat is None or not mat.use_nodes:
            continue

        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        output_node = None
        principled = None
        for node in nodes:
            if node.type == 'OUTPUT_MATERIAL':
                output_node = node
            if node.type == 'BSDF_PRINCIPLED':
                principled = node

        if output_node is None or principled is None:
            continue

        # 保存 Surface 接口的原始连接
        surface_input = output_node.inputs.get('Surface')
        orig_from_socket = None
        orig_from_node = None
        if surface_input and surface_input.is_linked:
            orig_link = surface_input.links[0]
            orig_from_socket = orig_link.from_socket
            orig_from_node = orig_link.from_node
            links.remove(orig_link)

        # 创建 Emission 节点
        emit_node = nodes.new(type='ShaderNodeEmission')
        emit_node.name = node_label
        emit_node.label = node_label

        # 获取 PBR 输入源
        pbr_input = principled.inputs.get(socket_name)
        if pbr_input and pbr_input.is_linked:
            from_socket = pbr_input.links[0].from_socket
            links.new(from_socket, emit_node.inputs['Color'])
            print(f"[BakeWrangler]   {bake_type} 烘焙: 连接 '{from_socket.name}' → Emission Color")
        elif pbr_input:
            # Metallic 是 float，需广播到 RGB；Base Color 是 RGBA 直接使用
            val = pbr_input.default_value
            if hasattr(val, '__len__') and len(val) >= 3:
                color = (val[0], val[1], val[2], 1.0)
            else:
                color = (float(val), float(val), float(val), 1.0)
            emit_node.inputs['Color'].default_value = color
            print(f"[BakeWrangler]   {bake_type} 烘焙: 使用默认值 {color}")
        else:
            emit_node.inputs['Color'].default_value = (0, 0, 0, 1.0)
            print(f"[BakeWrangler]   ⚠ {bake_type} 烘焙: 找不到 '{socket_name}' 输入，使用 0")

        # Emission → Material Output Surface
        links.new(emit_node.outputs['Emission'], output_node.inputs['Surface'])

        # 保存恢复操作
        restore_ops.append((mat, output_node, orig_from_socket, orig_from_node, emit_node))

    def restore():
        for mat, output_node, orig_from_socket, orig_from_node, emit_node in restore_ops:
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            for link in list(links):
                if link.from_node == emit_node or link.to_node == emit_node:
                    links.remove(link)
            if emit_node.name in nodes:
                nodes.remove(emit_node)
            if orig_from_socket and orig_from_node:
                try:
                    links.new(orig_from_socket, output_node.inputs['Surface'])
                except RuntimeError:
                    pass
            print(f"[BakeWrangler]   材质覆写: 材质 '{mat.name}' 已恢复")

    return restore


def cancel_bake(tree):
    tree.bake_state = 'CANCELLED'
