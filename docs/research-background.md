# 研究背景：可重建的历史网络与证据边界

日期：2026-10-21。本文解释为何本项目采用多来源历史 XML 加邻近 SQL 的有标记近似，而不把最新 history dump 当作所有过去季度的完整快照。**目标是 enwiki 与 zhwiki，自 2001 Q1 起按季度末 UTC 23:59:59 生成已结束季度；此阶段没有构建页面图、分类图或 NGD。NGD 公式、计数集合及零共现口径仍待确认。**

## 1. 背景证据来自哪里

本次只读重用了先前 enwiki 差异研究的 `final-verification.json`，以及后续 `normal-page-check/` 中修正了日志身份字段的 JSON/说明；未改写旧项目，未重扫原始 XML，未重新执行旧 verifier 或在线重查这五项日志。公共仓库只保留手工选择字段的 [`evidence-background.json`](evidence-background.json)，不复制完整报告、manifest、原始目录、用户名、IP、编辑摘要或 revision 正文。

| 实际重读的文件（不公开私有路径） | SHA256 |
|---|---|
| `final-verification.json` | `84ea977b2069638cc455ecd4d5982f2da24381459c265aec2d49da7c1991ae9b` |
| `normal-page-check/normal-page-log-evidence.json` | `f7bca9e90a143ab88c924414bf0ce4a784df6563ba094a30b2350f6a5f0b4552` |

来源获取边界：MediaWiki 说明页的本文窄范围事实来自检索返回的官方页面摘录；直接页面读取超时。官方日志实现与 export schema 则已通过 GitHub content API 读取实际源码，不以搜索摘要代替源码。本文只对这些证据支持的范围作结论。

这些 hash 是本次对实际文件字节计算的身份锚，不是新一次全量复算证明，也不是官方原始 dump checksum。旧 verifier 的 `status=verified` 与两个明确限制同时成立：`official_historical_completeness_verified=false`、`raw_source_hashes_are_official=false`。其验证采用了已有 scanner 记录及定点重复 RID 复核，没有重新读取所有 revision binary 的完整哈希，也没有重新解压全部原始归档。不能把“研究产物已对账”扩写成“所有官方历史输入已证明完整”。

本次核对了投影计数的基本恒等式、五条 `delete/delete` 记录的 `logpage == old_page_id`、样本 namespace/redirect 与来源哈希。下面提及的缺页历史三分组及重复页/merge event 的精确标识来自已确认任务交接；sanitized JSON 明确标注该 provenance，未在本范围重读对应底层报告/原始流。它们不是本仓库新产生的实验结果。

## 2. 实际比较的集合，不是整站同比增长

| 集合 | dump 标签 | 文件数 | namespace 范围 | 页面数 | 修订口径 |
|---|---|---:|---|---:|---:|
| 旧研究 cohort | `20210501` | 705 | **只有 0、14** | 17,933,535 | 686,697,676 个旧 RID |
| 新辅助身份查找集合 | `20220201` | 742 | **所有 namespace** | 55,140,566 | 989,043,144 条原始记录；989,043,139 个唯一 RID |

新集合扩大 namespace 是为了在全站查找旧身份，不是把研究 cohort 扩为全 namespace。两行页面/修订总数不能直接用来解释内容增长率。旧字段、namespace 与 redirect 状态均按旧 cohort 解释。

最终对账：

- 缺失旧 page ID：**64,460**；缺失旧 RID：**894,428**。
- A 类：旧 page ID 在新集合缺失的修订，共 **892,791**；B 类：旧 page ID 仍在但 RID 缺失，共 **1,637**。A+B 等于 894,428；它们是修订分类，不是页面分类。
- 匹配到的旧 RID 为 **685,803,248**；匹配+缺失等于 686,697,676。`ambiguous_matched_revisions=0`，不代表新源没有重复 ID。
- 缺失 page ID 的旧历史三分组：**229** 页的全部旧 RID 在其他 page ID 下仍能找到；**62** 页部分幸存、部分缺失；**64,169** 页全部旧 RID 都缺失。三者相加为 64,460。该分组为交接中的已验证结果，本次仅对分组总数与最终缺页数做算术核对。

因此，“旧 page ID 不在新 dump”不自动等于“该页面全部历史已消失”；“同标题出现新 ID”也不足以独自证明删除重建或语义连续。上述缺失首先是给定两组输入的集合差异，不是删除原因清单。

### 重复 RID 并非只能归因于本地解析器

新源有 **5 个重复 RID，10 条相关观察，5 条 excess records**，所以 raw 比 unique 多 5。既有最终验证确认了定点 10 条 binary 记录和两页身份，且已有独立 raw XML prefix 探针与公开 merge 日志交叉支持：两个相关 page ID 为 **68711819、69945288**，merge log ID 为 **127166675**，UTC 日期 **2022-02-02**。这些精确上下文来自交接，原始证据文件 hash 由旧最终验证绑定；本次未重新跑 raw probe 或重新查询 merge 事件。

结论的强度是“重复记录在所查原始来源中有佐证，公开历史合并提供上下文”，不是“已证明导出器为何重复”或“已知道两 shard 的精确读取顺序”。旧验证明确 `exact_shard_read_order_known=false`；raw prefix 探针也不是整份 archive 的 CRC 复核。这五组新源歧义与旧 RID 匹配零歧义并不矛盾，不能丢弃冲突后伪称源数据唯一。

### dump 日期标签不是单一全站时刻

旧验证记录的 archive member Modified 范围：旧为 `2021-05-07 08:18:48` 至 `2021-05-08 01:45:15`；新为 `2022-02-07 07:51:46` 至 `2022-02-08 01:28:18`，**archive listing 未提供时区**。它们不是精确 revision cutoff 或事件窗口。尤其 `20220201` 标签不排除与 2022-02-02 事件相关的生成期现象；仅据文件标签不能断言所有 shards 在 2 月 1 日已原子冻结。

## 3. 页面身份、标题与删除日志

MediaWiki 文档说明普通移动/重命名不改变 page ID；删除再恢复等流程可能改变它。page ID 是特定 wiki 的数据库身份，不是永久语义实体标识；标题可重命名也可复用。跨 wiki 的相同整数更不能当同一个节点。[6]

官方 `ApiQueryLogEvents.php` 的 1.39.9 源码明确区分：`log_page` 是记录事件时保存的 page ID，`page_id` 来自查询时按标题关联，删除/重建时会不同；输出相应为 `logpage` 和 `pageid`。本次通过官方 GitHub 镜像 content API 读取，blob ID 为 `3e4ed24316440657bed916c18378659f3a186848`，关键位置 `113–123,340–342`。这是为什么不能因为 API 返回新 ID 或 0 就否定旧 ID 的删除事件关联。[22]

前次 `normal-page-check` 的五个样本均为旧 namespace 0、非 redirect，旧 page ID 及全部旧 RID 在比较新集合缺失；独立公开日志查询保留了历史身份字段，实际找到以下 `delete/delete` 事件。表格只重述 retained response，不声称今天刚查到：（见本地 sanitized evidence）

| 标题 | 旧 page ID / `logpage` | 删除 `logid` | 事件 UTC | 缺失旧 RID | 查询时 `pageid` |
|---|---:|---:|---|---:|---:|
| Religion of peace | 8229053 | 121883932 | 2021-09-22T19:05:34Z | 1502 | 68792346 |
| Creationist cosmologies | 1450561 | 123152393 | 2021-10-25T00:53:05Z | 1294 | 69109154 |
| Cushitic peoples | 36400137 | 118144533 | 2021-05-26T19:37:19Z | 1229 | 67994460 |
| 2019 in home video | 59319702 | 126522616 | 2022-01-18T15:40:50Z | 1968 | 0 |
| KISS (system) | 17175 | 125787618 | 2022-01-02T01:03:01Z | 26 | 0 |

保留的查询采集时间是 **2026-10-19 UTC**，`request_url`、`retrieved_utc` 与上述 allowlisted 事件字段在 JSON 中可核对。五项均无 continuation 且匹配同一旧身份，但它们只支持“这些旧页面身份有对应公开删除事件”，不能外推全部缺失页面均为同一机制，不能确定删除原因或证明逐 RID 物理抹除，也不能断言这些标题现在仍不存在。复查时按目标站点实际 API 能力设置标题/时间窗口并检查 continuation，不能把另一版本文档的可用参数当所有旧接口都支持。

## 4. 为什么最新 history 不足以精确还原所有过去

官方 dumpBackup 文档说明 XML export 不是完整数据库备份，不包含删除修订等数据；全历史表示导出当时可导出的历史，不是“曾经存在的所有正文永远可得”。实际旧新集合差异为本项目提供了直接例证。[12]

官方 export 0.11 schema 的 `PageType` 把 title/ns 与 revisions 放在页面层；`RevisionType` 包含自己的 timestamp/content，并没有为每个 revision 附完整的历史页面标题时间线。本次从官方镜像 content API 读取 schema，blob ID `19142f78f20134789a4645b9cb8ad595676a1a84`。因此，取最新源内 `timestamp <= quarter_end` 的 revision 只重建“幸存可见历史中的所选内容”；不能直接假设该 XML 页面的当前 title/ns/redirect 属性就是每个历史季度的状态。[23]

推论与设计约束：

1. 同时利用多个已有 XML history 快照，可能找回后续来源中不再出现的旧页面/修订；不能据此保证找齐全部曾存在、后来删除/隐藏的历史。
2. 每个季度明确保存 source snapshot、selected RID/time、title provenance 与历史身份不确定性；同一 RID 多来源不一致时保留候选与冲突证据，不按最新源覆盖一切。
3. 内容时间、标题/namespace 身份时间、导出生成时间分别标记。没有 move/log 证据的历史标题解析须标为近似或 unresolved；普通改名保留 ID 不等于标题永远稳定。
4. 无可见正文、明确 hidden、缺失字段和空正文分别编码；不能把“解析失败”或“无历史来源”伪造为空页面。
5. 这些已验证差异只覆盖此次 enwiki 研究，不构成 zhwiki 同等缺失率的证据，更不验证 2001 年起所有季度。

## 5. 分类 XML ∪ 邻近 SQL：接受近似，但不改写时间含义

用户接受的融合视图为 **XML 所选正文的分类观察 ∪ 距季度最近可用 SQL 的分类观察**。这是一条项目规则，不是 Wikimedia 保证的历史精确性。XML/SQL 两层 observation 必须分开保留，union edge 要有来源位、真实 dump 日期、目标季度、时间偏移与 `approximate` 标记；更晚 SQL 引入的边不得包装成已证实的早期事实。

官方 categorylinks 定义中 `cl_from` 是成员页身份，分类目标需按相应 schema 解析；`cl_type` 区分 page/subcat/file，`cl_timestamp` 是该链接在表中最后更新的时间。它不是带有效起止时间的关系历史；按 `cl_timestamp <= cutoff` 过滤一份较晚 SQL 无法恢复后来已删除的边，也不能据它判定完整历史成员集。这是由快照表语义得出的限制。[17]

还需分别处理：

- SQL 成员 page ID 用同次 SQL 的 page/title 映射解释，不能直接按整数硬连其他年份 XML；分类名存在并不要求对应分类描述页一定存在。
- XML 直接 wikitext 的分类提取不等于 MediaWiki 在完整模板/模块环境下生成的全部分类；两者差异作为来源信息保留，不假称 union 后消除所有误差。
- 方向定义为页面→分类、子分类→父分类；一页/分类可以有多个父分类。设计不预设 acyclic：原始关系保留，遍历用 visited/环检测或 SCC，树形展示仅是投影视图，不能删环后声称原图就是树。此为基于分类关系表不提供 DAG 保证的工程约束。[17]
- schema 会变：旧 `cl_to` 与新 `cl_target_id` 不能混同。邻近 SQL 的实际 DDL、目标表 join 和 namespace/语言规则必须进入 recipe；上游参考实现的固定列数不是适用于所有年代的证明。[17]

## 6. 对本项目的实际影响

先验证 zhwiki 的有界季度 pilot，再扩展英文；保留重复/缺失/身份未解与 XML/SQL disagreement 计数，报告覆盖而不是承诺“精确还原”。正文只为解析所选 revision 瞬时存在，派生保留物只含身份、关系、provenance 与诊断；上游当前真实行为及 no-retention 门槛见 [`upstream-reuse.md`](upstream-reuse.md)。网络缺失可能影响度数、连通性、分类计数与未来 NGD，影响幅度尚未测量；公式待确认前不产出虚构距离或质量分数。

以上是已有证据支持的研究动机与下一阶段约束；不是当前仓库已经完成解析、还原或图验收的声明。

## Sources

[6] https://www.mediawiki.org/wiki/Manual:Page_table
[12] https://www.mediawiki.org/wiki/Manual:DumpBackup.php
[17] https://mediawiki.org/wiki/Manual:Categorylinks_table
[22] https://api.github.com/repos/wikimedia/mediawiki/contents/includes/api/ApiQueryLogEvents.php?ref=1.39.9
[23] https://api.github.com/repos/wikimedia/mediawiki/contents/docs/export-0.11.xsd?ref=1.39.9
