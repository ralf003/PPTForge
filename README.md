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
