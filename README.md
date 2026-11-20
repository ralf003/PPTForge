# PPTForge

> 让 AI 产出的 PPT 不再是“卡片格阵 + 满屏小字”，而是一份能直接上台、且每一页都可编辑的 PPTX。

[![CI](https://github.com/ralf003/PPTForge/actions/workflows/ci.yml/badge.svg)](https://github.com/ralf003/PPTForge/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](#30-秒跑通)

## 为什么做这个

做 PPT 最难的不是排版，而是它把两种完全不同的认知活压在一起：**想清楚内容**，和**设计好视觉**。

AI 没把这件事变简单，它只是把痛苦换了个形式：

- 在线 slides 工具给你一个黑盒，导出 PPTX 时图表变图片、字体和位置漂移，文件甚至可能打不开；
- 用 python-pptx 手写，你要自己算每一个元素的坐标，做得好不好全靠肉眼和自觉；
- 最常见的“AI 生成”：一页塞 5–9 个矩形卡片，字小、留白大、配图是占位图。

这不是主观吐槽。我们把“空”和“挤”做成了可计算指标，对自己的基础版式实测：内容页非背景像素只有 **2.4%–7.3%**，最大一块空白占掉画面 **45.9%–62.5%**。肉眼觉得“空”，数据上它确实是空的。

## PPTForge 的答案

把“想清楚”和“画出来”拆成两条流水线：

1. 你只声明**每页的主张和用哪个骨架**，不写坐标；
2. 引擎确定性地渲染，布局不依赖模型临场发挥；
3. 质量门把小字、空页、留白、对比度、OOXML 损坏全部拦下来，过不了门就不交付。

产物是 100% 原生、可编辑的 PPTX：形状、文字、图片都是 PowerPoint 对象，不是截图，也不是黑盒。

## 和现有方案的差异

| | 在线 slides | 手写 python-pptx | PPTForge |
| --- | --- | --- | --- |
| 产物 | 在线黑盒，导出会漂移 | 原生 PPTX | 原生 PPTX |
| 谁来定布局 | 平台固定模板 | 你自己算坐标 | 选骨架，引擎算坐标 |
| 质量保证 | 平台说了算 | 全靠自觉 | 硬门拦截，不达标不交付 |
| 配图/空页可量化 | 否 | 否 | 是 |
| 可编辑、可审计 | 弱 | 是 | 是 |

## 30 秒跑通

```bash
pip install -e .
pptforge doctor
pptforge build examples/sample_spec.yaml -o out.pptx
```

渲染回看并跑视觉门（需要 LibreOffice 与 poppler）：

```bash
soffice --headless --convert-to pdf --outdir /tmp out.pptx
pdftoppm -png -r 110 /tmp/out.pdf /tmp/slide
pptforge check-visual /tmp/slide-*.png --roles cover,section,content,summary
```

## 视觉语法：五个骨架

| 骨架 | 承载的语义 | 图面形态 |
| --- | --- | --- |
| `track` | 沿时间或因果推进的叙事 | 轨迹 + 递进节点，底部结论带 |
| `stat` | 并列的关键指标 | 大数字 + 短分隔线，底部结论带 |
| `topology` | 分层架构 | 层条自上而下，左侧层级标识，层间箭头 |
| `hero` | 封面或全幅概念页 | 图片铺满整页，底部实色带压标题 |
| `split` | 图文对照 | 左侧深色文字栏，右侧照片满高裁剪 |

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

未知骨架直接抛错，不静默降级。

## 质量门

静态门（看结构）六类：字体名、投影级字号、元素越界、WCAG 对比度、文本溢出、区域重叠，外加 OOXML 轴 ID 修复。

视觉门（看渲染图）两类，按页型分档：

| 指标 | 内容页阈值 | 说明 |
| --- | --- | --- |
| 墨迹覆盖率 | ≥ 15% | 低于即判空页，抓配图没加载 |
| 最大空白块 | ≤ 28% | 抓“上半屏空一片” |

封面、分隔页单独放宽——那里的留白是设计意图；深底满版页不参与留白判定——背景本身就是元素。

## 设计哲学

- 内容和视觉是两种认知任务，必须分成两条流水线。
- 视觉语法冻结成骨架，模型只选骨架、不写坐标。
- 质量门宁可严，不静默降级；但设计性留白和缺陷性留白分开判，不制造假红。
- 结论先行，证据进备注，图面只放结构化关键词与判断句。

## 状态与路线图

当前是 **P0**，接口在 0.x 不承诺稳定。

- 已实现：五骨架、静态质量门、视觉门、CLI（build / validate / check-visual / doctor）、单页与多页五角色端到端出 PPTX，静态门兜底。
- 未实现：Deck 级大纲冻结与封面/结论页自动生产、真实 LLM 后端产出验证、现有 PPT 的反向解析与优化、原生图表与表格渲染、MCP 入口。

未实现的能力不会写进“已实现”清单。

## 许可证

[MIT](LICENSE)
