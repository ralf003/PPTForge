# PPTForge

声明式工程化 PPT 生产工具链，产出**本地可编辑 PPTX**，覆盖两个场景：

- **从零生成**：idea → 大纲 → 声明式 spec → PPTX
- **现有 PPT 优化**：全页渲染诊断 → 编辑式改造 → 质量门验收

## 特性

- 声明式 spec（YAML），agent 只描述意图、不写坐标
- **骨架库**：页型沉淀为可复用骨架，agent 只"选骨架 + 填内容 + 定强调"
- 投影级字号体系，默认微软雅黑（Microsoft YaHei）
- 确定性布局引擎，原生可编辑 shape/chart/table
- 内置质量门：字体/字号、元素越界、WCAG 对比度、文本溢出、区域重叠、OOXML 轴 ID 修复
- 五角色编排：Director / Researcher / Designer / Engine / Reviewer
- 库 / CLI / MCP 多入口

## 骨架库

| 骨架 | 承载的语义 | 图面形态 |
| --- | --- | --- |
| `track` | 沿时间或因果推进的叙事 | 一条轨迹 + 递进节点，底部结论带 |
| `stat` | 并列的关键指标 | 大数字 + 短分隔线，底部结论带 |
| `topology` | 分层架构 | 层条自上而下，左侧层级标识，层间箭头 |
| `hero` | 封面或全幅概念页 | 图片铺满整页，底部实色带压标题与主张 |
| `split` | 图文对照（左论点右实体） | 左侧深色文字栏，右侧照片满高裁剪 |

`hero` 与 `split` 依赖 `image` 字段；缺图时骨架退化为纯色底不白页，但图面价值随之消失——配图是这类页的主语，不是装饰。

页面只声明 `skeleton` 与语义字段，坐标由引擎推导：

```yaml
- role: content
  skeleton: track
  title: 规模化的瓶颈是长程轨迹与治理
  items:
    - name: 误差级联
      desc: 单步高成功率在长链上坍缩
      value: 90% → 12%
  claim: 治理必须内建在运行时
  note: 证据与缺口留档在这里，不占图面
```

配图骨架加一个图片路径：

```yaml
- role: cover
  skeleton: hero
  title: 智能体规模化
  subtitle: 三个量化边界
  image: assets/final/cover_gen.jpg
  claim: 瓶颈不在模型能力，在长程轨迹与治理
```

未知骨架会直接报错，不静默降级。

## 快速开始

```bash
pip install -e .
pptforge doctor
pptforge build examples/sample_spec.yaml -o out.pptx
```

## 工程状态

当前为 P0 工程骨架，接口在 0.x 版本不承诺稳定。
