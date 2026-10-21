# P1 中文季度局部试跑：执行契约

## 授权与范围

本次用户已要求推进下一步，开始P1工程与有界真实数据试跑。目标为 `zhwiki-2025Q3`，截止 `2025-09-30T23:59:59Z`；候选来源为2025-10-01 history XML 与2025-10-01 SQL。**局部试跑不等于完整季度图构建。** NGD仍待定义，英文批量不启动。

所有业务输入副本、临时目录、日志、图Parquet和测量证据保存在指定SSD项目目录；源归档只读。SSD为noexec，Go二进制/Node运行时与原生依赖使用主机可执行目录，缓存及数据仍在SSD。

## 输入门

- 对history全部64份归档做文件名范围与header列表检查；只可证明本地观察覆盖与归档成员声明，不等于官方必需分片完整性。
- 以声明的XML member字节数选择最小可用archive；不足以出现目标namespace/cutoff时明确记录空结果，另选归档，不伪造节点。
- 选中的原始压缩文件复制到SSD；源前后stat、源整文件SHA256与副本SHA256匹配。未取到官方checksum必须明示。
- 解码后流式计算XML字节数/CRC32，要求压缩解码退出0、上游selector根闭合和EOF验证通过。
- SQL先检查实际DDL/INSERT或LOAD DATA格式及categorylinks目标字段。需要linktarget但不存在时不得默默按旧cl_to索引解释。SQL source IDs须由同源page表解释，映射至XML所选页面身份/标题需明确且可拒绝。

## 处理链

```text
7z → in-memory CRC/byte tap → upstream history-select
   → selected-revision JSONL transient pipe (contains selected wikitext)
   → upstream WTF graph-only CLI
   → allowlisted graph-only JSONL
   → pilot assembler → native-list Parquet ZSTD
```

不写完整解压XML、selected wikitext、plaintext、评论、用户名、IP或正文crash样本。图JSON只允许page_id/ns/title/revision_id/timestamp/text_state/links/categories/redirect_target/parse_status；隐藏/缺失正文必须明确unavailable且不生成虚假边。WTF从所选历史正文判断redirect，不把export时页面redirect属性当成cutoff的状态。

上游修改保持opt-in；现有接口兼容。revision选择按 `(timestamp, revision_id)`，timestamp必须<=cutoff；不靠XML顺序。标题与namespace来自export页面层，仍有历史身份偏差标签。

## 图与融合边界

试跑页面图为所读archive/page范围内的诱导图：范围外或未解析历史标题保留unresolved，不声称不存在。分类registry ID是当前pilot generation内编号，不与page_id混用，也不声称跨generation稳定；后续全量注册层另按版本维护。

XML分类观察、SQL观察及union分别存储，union目标列表和source mask列表逐项对应；mask XML=1、SQL=2、both=3。分类图child→parent，多父与环保留并诊断。

若SQL仅使用有界prefix或仅复核schema，必须在报告中标记范围和GZIP CRC是否未读至EOF；未观察到某一SQL边不能解释为不存在。数据不能通过超预算的全表处理自动扩展试跑授权。

## 完成与报告

单个压缩归档通过完整解码，只能标记 `single_archive_pipeline_verified`；完整季度snapshot状态仍为未构建。记录页数/选中修订数、边与unresolved计数、SQL观察范围、分类union及mask、duplicate身份、环、runtime/RSS和SSD消耗；Parquet逐表读回与文件hash验证完成后发布单独pilot报告。

输入源集计划v1不因局部试跑自动升级成verified；actual build generation/源码commit/参数/输入hash必须独立绑定。失败保留未提交的partial及无正文诊断，不发布成功完成标记。
