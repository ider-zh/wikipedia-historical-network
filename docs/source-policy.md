# Source policy v1 · 选源规则与非精确性

## 季度目标

从 `2001-03-31T23:59:59Z` 起至运行时已经结束的季度末，每语言一份计划。日期一律UTC；文件名的YYYYMMDD是来源标签，不是全站同一事务快照时刻。未来未结束季度不作为已可重建快照。

## XML

1. 只选择 wiki、有效日期、非临时/部分下载且 representation 可识别的候选来源；仅按目录名称推断的来源仍为 metadata-only，不宣称内容完整。
2. Full-history XML 必须标签日期 >= target_time；其后才可从保存下来的历史中选择每页 `max(revision_timestamp <= target_time)`。从合格候选中选择距离目标最近的日期，确定性ID打破同日平局。
3. 比目标早的 history dump 无法提供之后发生的编辑，不能当成“目标时间已恢复”。较晚的 current/articles dump 没有历史，不能倒推旧页面；标签同日的 current 也只可列为时间待验证候选，不能声称精确日末。
4. revision ID 在历史合并场景可同时关联不同pageID：必须保留来源/冲突，不能随意按pageID丢弃。后期history无法恢复已删且未公开导出的内容；还存在标题、重定向、模板与分类展开的历史状态不完整。
5. 本期选单个最接近来源集是基线；未来可多history补缺，但必须以显式多来源 recipe、RID冲突和身份规则生成新版本，不偷偷把跨期观察合成精确历史。

## SQL

1. 在同wiki中选与目标日期绝对距离最小的category SQL来源；同距优先较早来源。至少需要categorylinks和同源page身份映射；按版本可能还需要linktarget/category/linktables，实际SQL schema预检后确认。
2. categorylinks 的创建时间字段不提供完整删除/生效区间；较晚SQL中边的存在不能证实它在更早目标时刻存在。按用户确认，允许作为近似补充，记录offset_days及future_sql_observations。
3. XML分类观察与SQL观察分开保留；融合关系取union去重，同时保留来源比特/来源集，不能让SQL覆盖或抹掉XML证据。提供XML-only、SQL-only和union三种视图以及差异统计。
4. 如2004目标暂用2020历史XML + 2007 SQL，日后找到2004 SQL：生成新的分类来源计划版本，保留旧版本，不重建未变化的page network。若新来源不完整或身份映射缺失，先注册不可用候选，不自动替换已有合格来源。
5. SQL table独立文件、压缩整体archive、数据库物理目录是不同representation；尚未打开内部目录的opaquearchive只能列候选，不能默认含page/categorylinks且可执行。

## 来源、位置与版本

物理文件索引记录path/stat/inode/device/host仅在私有SSD；对公众只投影wiki、日期、类型、计数、来源集ID、偏差与不完整原因。来源资格 = 可计划候选，不等于build-ready。整文件hash、归档CRC、官方分片列表和SQL映射预检是后续执行门。

不可变manifest中记录来源集fingerprint及未来validated content hash、策略/解析器/依赖/存储schema版本、时间口径和父版本。发布新manifest后可原子更新latest指针；构建产物同样按generation追加，不覆盖旧generation。新增不相关来源不应迫使所有snapshot重建。

## 质量标签

`exact_source_date_label` / `history_reconstructed_with_survivorship_bias` / `sql_temporal_approximation` / `historical_title_uncertain` / `unresolved_identity` / `shard_completeness_unverified` / `source_payload_unverified` 必须可机器读取。没有来源的季度明确blocked，不填充虚构来源和节点数。
