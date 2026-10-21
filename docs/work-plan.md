# 工作计划与验收门

## P0 初始化（本次范围）

- [x] 建立仓库、工作约束与enwiki/zhwiki季度末口径。
- [x] 实现季度时间轴、最近合格XML / 最近SQL选源、不可变来源计划版本。
- [x] 建立只含图身份/adjacency的Parquet契约，真实写读测试（fixture不是维基图产物）。
- [x] 三台机器只读metadata index落盘并逐root对账；保留访问失败和覆盖缺口，未宣称全源完整。
- [x] 用真实索引生成206份季度计划、blocked原因、私有来源映射和公开安全投影。
- [x] 上游复用审阅与历史删除/迁移背景完成，SQL逻辑导出来源另行标记。
- [x] dashboard读取真实清单，通过浏览器HTTP/file/手机/过滤/详情检查。
- [x] 48项本地测试、真实Parquet与隐私投影检查、独立复审通过；初始化提交已推送GitHub并核对远端HEAD及关键文件blob。GitHub Actions尚未启用：现有OAuth缺workflow权限，已保留未激活模板于docs/ci/。

## P1 中文验证（下一阶段，不在本次自动启动）

1. 选择一个来源足够的zhwiki季度；验证原压缩文件hash和覆盖，留足SSD余量。
2. XML上游选定revision流式提取；在上游加入graph-only所需字段/内存修正和回归测试。
3. Wikitext上游graph-only输出links/categories/redirect，避免不必要的正文/infobox/sections抽取和持久化。
4. SQL分类解码先验证schema及同源page映射；历史时间近似标记不可关闭。
5. 写Parquet并做读回、节点/边/list长度、冲突/unresolved/category环诊断；测量峰值内存、spill、临时空间和吞吐。
6. 形成真实容量/并发预算后再批准英文批量。

## P2 英文季度图

- 以来源集为单位只解压一次，转瞬选择所有需要季度的revision；重复selected RID的图解析结果可按source/parser/schema身份缓存复用。
- 不跨修订重复落地正文；page network和category来源层独立generation。
- 批处理受锁、资源余量、原子完成标记及版本绑定约束；失败保持可复核checkpoint，不能跳过坏分片发布完整图。
- 构建范围按实际metadata源能力决定；晚于最新history覆盖的季度明确blocked，而不是复制上一期图冒充还原。

## P3 统计与NGD

- 先定义网络节点/边关系、redirect折叠、category union近似视图选择、跨语言隔离。
- NGD公式、f(x)/f(y)/f(x,y)、N、零共现/缺失处理、候选对策略与精度单独评审。
- NGD可能全对平方增长；不得默认生成全量笛卡尔积。单独预算压缩与稀疏候选策略。
- dashboard追加统计快照与版本，不从计划数推断构建进度或伪造统计。

## P4 新数据与冷迁移

- 新来源到达→只读index追加→来源资格核验→受影响季度新plan version→仅重建失效组件。
- 更早SQL替换未来SQL近似时保留旧generation；新旧分类边差异可审计。
- 冷迁移先制定保留/复现/双副本与hash验证计划；不自动删除唯一原始/派生产物。
