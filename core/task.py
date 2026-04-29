from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PostEffect:
    """后期处理效果描述"""
    effect_type: str = ""       # 'ANTIALIAS' | 'SCALE' | 'MATH' | 'COMPRESS'
    params: dict = field(default_factory=dict)


@dataclass
class BakeTask:
    """单个烘焙任务的完整配置"""
    high_poly: Optional["bpy.types.Object"] = None
    low_poly: Optional["bpy.types.Object"] = None
    bake_type: str = "NORMAL"
    resolution: int = 2048
    cage_extrusion: float = 0.1
    max_ray_distance: float = 0.2
    output_path: str = ""
    file_format: str = "PNG"
    color_depth: str = "8"
    channel_name: str = ""
    device: str = "GPU"
    samples: int = 128
    use_denoising: bool = True
    use_adaptive_sampling: bool = False
    noise_threshold: float = 0.01
    margin: int = 16
    cache_key: str = ""  # 烘焙缓存键，同一 BakeChannel 节点同分辨率只烘焙一次，后续复用
    post_effects: list = field(default_factory=list)  # list of PostEffect

    def is_valid(self):
        return all([
            self.high_poly is not None,
            self.low_poly is not None,
            self.output_path,
            self.channel_name,
        ])

    def validation_errors(self):
        errors = []
        if self.high_poly is None:
            errors.append(f"[{self.channel_name}] 未指定高模")
        if self.low_poly is None:
            errors.append(f"[{self.channel_name}] 未指定低模")
        if not self.output_path:
            errors.append(f"[{self.channel_name}] 未设置输出路径")
        if not self.channel_name:
            errors.append(f"[{self.channel_name}] 通道名称为空")
        return errors

    def __repr__(self):
        hp_name = self.high_poly.name if self.high_poly else "None"
        lp_name = self.low_poly.name if self.low_poly else "None"
        post = f", post={len(self.post_effects)}" if self.post_effects else ""
        return (
            f"BakeTask(ch={self.channel_name!r}, type={self.bake_type}, "
            f"hp={hp_name}, lp={lp_name}, "
            f"res={self.resolution}, out={self.output_path!r}, "
            f"fmt={self.file_format}, depth={self.color_depth}"
            f"{post})"
        )


@dataclass
class CompositeTask:
    """将多个烘焙通道合成为单一 RGBA 输出"""
    combine_mode: str = "RGB_PLUS_A"
    sources: list = field(default_factory=list)
    output_path: str = ""
    channel_name: str = ""
    file_format: str = "PNG"
    color_depth: str = "8"
    post_effects: list = field(default_factory=list)  # list of PostEffect

    def is_valid(self):
        return all([
            len(self.sources) >= 1,
            self.output_path,
            self.channel_name,
            all(t.is_valid() for _, t in self.sources),
        ])

    def validation_errors(self):
        errors = []
        if not self.sources:
            errors.append(f"[{self.channel_name}] 合成任务没有输入源")
        if not self.output_path:
            errors.append(f"[{self.channel_name}] 未设置输出路径")
        for socket_name, task in self.sources:
            for err in task.validation_errors():
                errors.append(f"[{self.channel_name}/{socket_name}] {err}")
        return errors

    def __repr__(self):
        src_names = [f"{sn}={t.channel_name}" for sn, t in self.sources]
        post = f", post={len(self.post_effects)}" if self.post_effects else ""
        return (
            f"CompositeTask(ch={self.channel_name!r}, mode={self.combine_mode}, "
            f"sources=[{', '.join(src_names)}], out={self.output_path!r}{post})"
        )
