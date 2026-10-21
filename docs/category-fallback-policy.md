# Category fallback policy v1 · 向后续最近可重建时点回填

## 用户确认的口径

当目标 snapshot 的 category network 无法重建时，使用**同一 wiki、目标时点之后最近可重建的 category network**作为替代视图。此规则适用于早期未有现代分类机制、来源缺失、必要身份映射缺失或解析不支持等情况；各自原因仍必须保留，不因回填而改写成“已精确恢复”。

该策略是分类图视图层规则，独立于原来的 XML/SQL dump 选源规则。较晚 history dump 的文件日期不等于分类图的有效时点：必须用该图实际重建的时间选择，而不是用文件名、下载日期或构建完成时间选择。

## 选择顺序

设目标时间为 T，同一语言站的分类图实际有效时间为 C：

1. 优先重建/使用 T 自身的分类图；已验证的空分类结果也是有效结果，不能仅因边数为0就触发回填。
2. 确认 T 无法重建或当前执行受阻，并记录具体原因后，搜索所有 C > T 的可重建候选，按 C 升序选择最近者。不是绝对时间差最近，不采用更早的图，不跨语言借用。
3. “可重建候选”必须通过相应构建的来源hash/覆盖、schema/parser、必需身份映射和关系范围预检。仅有dump标签、metadata eligible、计划状态或一个局部archive，不构成可用分类图。
4. 最近候选尚未生成时，先记录 planned fallback dependency，按其自身 C 构建并验证；只有完整、验证通过且绑定不可变manifest/hash的generation才可被实际引用。不得把候选标成已回填。较近候选资格未解决时，保持等待，不默默跳到更远且容易成功的候选。
5. 某候选确定不可重建时保留失败证据，继续检查下一个后续候选。如果所有后续候选均不可用，则分类视图为 blocked_no_reconstructible_later_category；不得生成虚构空图或改用过去的图。
6. 同一 C 存在多个generation时，使用显式审核/激活的不可变generation；不能按目录顺序或latest文件存在任意选取。将选择写入新的目标snapshot view manifest。

## 回填范围和身份

- **page network始终属于T**：仍选择每页 latest revision <= T，不借用C的page network或未来修订。
- category network按本项目分类侧契约，包括 page→category 成员关系及 category→category 层次关系；缺少其中一项不能默默当完整分类侧已恢复。XML-only/SQL-only诊断视图仍可保留，但不能自动冒充当前recipe所需的完整融合视图。
- 回填默认引用C的整套分类侧generation，不按目标T的页面集合静默裁剪，也不把T的部分观察与C的完整图偷偷合成新的“同期图”。T已提取的部分观察、失败诊断仍独立保留。
- 引用保留C的wiki、节点域、注册表及generation身份，不复制并重编号成T的节点。C中的 page_id/category registry ID不能直接和T的page_id当成跨时点同一实体连接。
- 需要联合分析T的页面和C的分类时，另产显式、带版本的身份映射；不能映射的目标保留unresolved，不能把未来才出现的页面当作T已存在。默认完整回填视图不等于该映射投影。

## 必须记录的出处

目标snapshot view manifest至少包含：

- `category_fallback_policy = nearest_reconstructible_later_v1`；
- `category_mode = native | future_fallback | blocked`；
- `target_time`、`category_effective_time`及其UTC正时间偏差（不能仅保留舍入后的天数）；
- `category_origin_snapshot_id`、`category_origin_generation_id`、被引用manifest SHA256；
- 原生重建失败原因、候选排除/等待理由、来源SQL日期及XML/SQL各自的质量标记；
- `category_temporal_approximation`、`future_category_network`、`not_contemporaneous_category_graph`等机器可读质量标签。

XML=1、SQL=2、both=3的边来源mask仅表示原图generation内部的来源并集，不表示时间可信度。future fallback不能通过更改mask冒充T的XML/SQL原生观测。

报告/dashboard/未来统计必须同时展示T和category_effective_time。可以报告“目标2003Q4，分类采用2004Q3替代”，不能只报告“2003Q4分类图已还原”。NGD尚未定义；后续若使用回填分类，必须保留这一跨时间输入身份。

## 示例（说明规则，不是现有可用数据声明）

- T=2003Q4无法重建；2004Q2确定不可用，2004Q3与2005Q1可重建：选择2004Q3。若2004Q3尚待预检则保持pending，不默默使用2005Q1。
- T=2010Q1无法重建；2009Q4可用，2010Q2不可用，2010Q3可用：选择2010Q3，不因2009Q4更近而采用过去的图。
- T=2003Q4已有经验证、确实为空的原生分类结果：保留native空图；若空是源缺失/未支持机制导致的不可重建状态，则按原因触发回填，不能混淆二者。
- T无可重建的后续分类候选：page network仍可独立构建和验证，但分类侧blocked；不声称page+category组合snapshot完整。

## 更新和当前实施边界

新增来源使T自身或更近的后续时点可重建时，为T追加新的分类视图/构建版本和supersedes引用，保留旧版本。仅分类选择变化不重跑T已验证且输入/解析策略未变的page network；分类视图、所需映射和下游分类统计失效，未来NGD依赖另行评审。

本次更新固化用户口径与执行/manifest契约，**尚未实现category generation registry、回填resolver和dashboard双时间字段**。现有`whn.planner.plan_snapshot`仍负责原始dump选源，不是分类图回填选择器；不把缺linktarget的SQL列为已合格。206份旧来源计划和既有snapshot版本保持不变，下一阶段在具备可验证分类generation后追加分类视图版本。当前没有完成的真实分类图可被宣称已回填。
