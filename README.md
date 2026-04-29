# PBR-BakeMaster

PBR 纹理烘焙 Blender 插件 — 基于节点编辑器的可视化烘焙流程工具。

## 功能

- **节点编辑器** — 在 Blender 节点编辑器中通过拖拽连线构建烘焙流程
- **8 种 PBR 通道** — 法线、漫反射、环境光遮蔽、粗糙度、金属度、曲率、高度、自发光
- **通道合成** — RGB+A 与 RGBA 分离两种模式，将多个通道合成为单一贴图
- **后期效果** — 抗锯齿、缩放、降噪、数学运算、色彩压缩
- **纯内存管线** — 烘焙与合成全程在浮点缓冲中完成，无中间文件量化损失
- **烘焙缓存** — 相同通道/分辨率自动复用，避免重复烘焙
- **PNG 直接写入** — 绕过 Blender alpha 预乘问题，保证像素精度

## 安装

1. 下载 `PBR-BakeMaster-BlenderScript.zip`（或克隆本仓库）
2. Blender → 编辑 → 偏好设置 → 插件 → 安装
3. 搜索 "PBR-BakeMaster" 并启用
4. 在节点编辑器中创建 "PBR 烘焙" 节点树

## 使用

1. 切换到节点编辑器，新建节点树，选择 **PBR 烘焙**
2. 添加 **网格选择** 节点，指定高模和低模
3. 添加 **烘焙通道** 节点，选择要烘焙的 PBR 通道
4. （可选）添加 **后期效果** 节点进行缩放/降噪/抗锯齿
5. （可选）添加 **组合通道** 节点将多个通道合成为 RGBA
6. 添加 **保存图像** 节点，设置输出路径和格式
7. 连接节点，点击 **开始烘焙**

## 要求

- Blender 4.0+
- Cycles 渲染引擎

## 开发

本项目全程使用 **DeepSeek V4 Pro** 进行 AI 辅助开发。

```
PBR-BakeMaster-BlenderScript/
├── __init__.py              # 插件入口
├── tree.py                  # 自定义节点树
├── categories.py            # 节点分类
├── sockets/                 # 自定义 Socket 类型
├── nodes/                   # 节点定义
│   ├── bake_channel.py      # 烘焙通道节点
│   ├── combine_channel.py   # 组合通道节点
│   ├── mesh_select.py       # 网格选择节点
│   ├── sample_settings.py   # 采样设置节点
│   ├── save_image.py        # 保存图像节点
│   └── post_nodes.py        # 后期效果节点
├── operators/               # 操作符
│   ├── bake_execute.py      # 烘焙执行
│   └── ...
├── panels/                  # UI 面板
└── core/                    # 核心逻辑
    ├── executor.py          # 烘焙执行引擎
    ├── graph_walker.py      # 节点图遍历
    └── task.py              # 任务数据结构
```

## 许可证

MIT License — 详见 [LICENSE](LICENSE)

---

**开发者**: MARK42IRPC
