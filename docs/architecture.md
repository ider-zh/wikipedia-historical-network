# 项目架构与阶段边界

## 已确认的目标

- 语言：英文 `enwiki` 为主；中文 `zhwiki` 作为低成本快速验证，再推广英文。
- 时间：自 2001 Q1 起，季度末 UTC 23:59:59；仅生成已经结束的季度，语言尚未创建时允许空快照，不凭空造页面。
- 首阶段交付：真实 dump 目录索引、逐季度来源计划与不可变版本、存储/解析契约、静态 dashboard。
- NGD：先保留图与统计接口，公式、样本空间、入链/分类集合、计数去重规则、零共现处理待单独确认。本次不产出伪 NGD。
- 热处理：所有源读取缓存、环境、spill、Parquet 和图产物在用户指定的 220 SSD 项目目录。代码仓库不是数据仓库，不移动/删除现有 dump；冷迁移另行计划与授权。

## 模块与数据流

```text
220 / 222 / 229 本地原始归档（只读）
  → metadata inventory（path/stat/filename inference，非内容验证）
  → source-set registry（wiki/date/representation/table/shard/replica）
  → quarterly source planner → immutable recipe/version manifest
  → source validation + bounded Chinese pilot（下一阶段）
  → streaming XML / SQL adapters
      XML：wikipedia-dump-parser 选择每页 latest revision <= target
           → transient selected wikitext → wtf_wikipedia_server graph-only
      SQL：stream table decode → dump-local page/category identity mapping
  → immutable Parquet observations
  → page graph / XML category observations / SQL category observations
  → provenance-aware deduplicated category union
  → graph validation & statistics
  → NGD（口径确认后再开发）
  → allowlisted static dashboard projection
```

本仓库只负责编排、来源选择、版本与图装配。XML 提取与 wikitext 解析不重写第二套：有必要的功能/内存优化应在指定上游项目加测试并提交，上游 commit 固定进每个构建 recipe。当前不启动解析服务、不扫描数十 TB XML，也不做“空实现已完成”的标记。

## 图与身份

- 页面键至少包含 `(wiki, snapshot_id, page_id)`；`page_id` 不跨语言比较，也不能作为永久语义实体 ID。保留 title/ns、selected_revision_id/time、redirect_target_title、来源与解析版本。
- 页面链接图为有向边，`source_id → sorted unique target_id_list`。按目标快照标题表与命名空间解析；红链、互维基、片段、自环和 redirect 规则分别统计，不静默混入同一整数域。
- 分类成员边为 `page → category`；分类层次边为 `child category → parent category`。分类关系是有向图，不保证是一棵树；必须保留多父节点、孤立点、环和自环诊断。
- 分类使用可追溯的 `(wiki, normalized_category_title)` 注册键，可映射到 snapshot page ID；SQL 中的 page IDs 仅在该 SQL dump 的 page 表内解释，不能和异年份 XML ID 直接硬连接。映射不明时保留 unresolved，而不是丢边或误连。
- `category tree = XML observations ∪ SQL observations` 是用户接受的融合视图。XML/SQL 原始观察分开存，union 边带来源标记；SQL 时间不等于历史 snapshot 时间时必须标记近似。不能把较晚才出现的分类边当作已证实的早期存在。

## 增量和版本

每个 snapshot 有独立 plan version、recipe SHA256 与构建 generation。状态依次区分 `blocked / planned_unverified / validated / building / verified / published`，本阶段最多到来源计划。

新来源到达时重建索引 → 比较选择结果 → 相同 recipe 不生成重复版本；来源变化生成新不可变版本并保留 supersedes。SQL 替换一般只失效 SQL 观察、分类 union/graph 和下游统计，不重跑未变化的 XML 页面图。XML/解析/身份规则变化则失效相应页面图及分类链路。索引时间戳、物理副本数量不是构建身份；源文件内容哈希与上游版本在实际构建前必须固化。

## 执行与验收

批处理 CLI/文件队列即可，不依赖常驻数据库。Parquet 用 PyArrow 或 DuckDB 等嵌入式工具处理；“无服务存储”不等于解析器不许是临时批处理进程。dashboard 完全静态，无作业启动按钮、远端 shell 或私有绝对路径。

每个构建必须执行：输入覆盖及官方/本地 checksum 状态核验；源指纹前后核验；latest-revision 时间上界；重复 RID 多源冲突证据；title/redirect 解析审计；节点/边/list counts 对账；category union 去重和来源并集核验；Parquet schema/codec/readback；不可变版本 manifest/产物哈希最后提交。未通过不能发布“精确还原”。

先做中文单个历史季度试跑测量吞吐/临时空间/解析字段，再决定英文并发及 SSD 预算。所有语言全部季度同时解析不在本次初始化范围。
