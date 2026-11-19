# PPTForge

声明式工程化 PPT 生产工具链，产出**本地可编辑 PPTX**，覆盖两个场景：

- **从零生成**：idea → 大纲 → 声明式 spec → PPTX
- **现有 PPT 优化**：全页渲染诊断 → 编辑式改造 → 质量门验收

## 特性

- 声明式 spec（YAML），agent 只描述意图、不写坐标
- 投影级字号体系，默认微软雅黑（Microsoft YaHei）
- 确定性布局引擎，原生可编辑 shape/chart/table
- 内置质量门：schema、字号、对比度、OOXML 轴 ID 修复
- 库 / CLI / MCP 多入口

## 快速开始

```bash
pip install -e .
pptforge doctor
pptforge build examples/sample_spec.yaml -o out.pptx
```

## 工程状态

当前为 P0 工程骨架，接口在 0.x 版本不承诺稳定。
