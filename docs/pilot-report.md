# P1 中文季度试跑报告 · 2026-10-21

## 结论

**P1 状态：blocked。完整季度图产出：0；通过完整 wikitext 管道的真实局部图：0。**

已完成单归档的完整性与历史修订选择验证，并实际执行端到端管道。wikitext 阶段在第27条页面记录因 `UNSUPPORTED_MARKUP` 安全拒绝，未发布成功标记或 Parquet 图。SQL 另因缺少同源 `linktarget` 阻塞。不能据此批准英文批量或推导全量图容量。

## 目标与来源边界

- 目标：`zhwiki-2025Q3`，cutoff=`2025-09-30T23:59:59Z`。
- XML 来源标签：2025-10-01；试跑只选择64份归档中的一份，**不是完整季度来源集**。
- 选中：`zhwiki-20251001-pages-meta-history6.xml-p9237651p9283260.7z`。
- 压缩大小：32,030,181字节；解码 XML：1,287,526,387字节；CRC32=`DCBAAED0`。
- 压缩文件 SHA256=`946b8bb3ed954b88f448f8b1b694832e066935fcca25693384b0b5dc4d89fdf6`。
- 远端与SSD副本整文件SHA256一致，源复制前后指纹不变。MD5/SHA1与邻近保留的dumpstatus一致，但该元数据未独立认证。
- 全部64份仅完成header、文件名范围和catalog-stat核对；没有声称全部payload校验或官方完整性。

## 真实执行结果

| 验证 | 结果 | 不代表什么 |
|---|---|---|
| 独立Expat流式审计 | 全文EOF、1,287,526,387字节、CRC一致，约53.77秒 | 不是项目生产提取器，不生成图 |
| 上游Go selector | 44,221页、105,128修订，选中27,180页；完整root/EOF且退出0 | 不是全wiki节点数 |
| 选中修订独立比对 | 全部27,180页的ID/ns/title/RID/time/state一致；可见正文SHA256逐页一致 | hash比较不证明wikitext解析正确 |
| namespace分布 | ns0=22,986；ns14=4,194 | 不代表所有选中页面已解析成边 |
| XML→selector→WTF真实管道 | 第27条记录拒绝；退出码decoder=-13、selector=-13、WTF=1 | SIGPIPE为下游拒绝后的终止，不是已证明归档损坏 |
| SQL有界探针 | page/categorylinks各1,000行；max_rows、complete=false | 未读到GZIP尾部，未验证CRC或完整SQL |

独立审计脚本仅用于证据复核，不是本仓库的第二套生产XML解析器。生产XML选择实际复用上游 `historyselect.Select` 与 `cmd/history-select`。selected wikitext只存在于内存及管道；没有写出选中正文JSON、完整解压XML、plaintext或crash输入文件。

## 资源观测

selector独立比对命令实测wall约58.92秒，GNU time报告maximum RSS为214,936 KiB，swap=0。这是该验证命令进程树的high-water观察，**不是多进程同时RSS之和，也不是graph pipeline容量测量**。独立比对脚本自身保留元数据及hash，亦有内存开销。

失败的wikitext管道wall约0.39秒，maximum RSS=211,800 KiB；因为在第27条记录就中断，该数字不能代表完整图解析峰值或吞吐。当前没有可用于外推的真实Parquet图字节/边比率，也没有英文并发预算。

## 阻塞与修复边界

### Wikitext

锁定的 `wtf_wikipedia 10.4.2` 在 literal-extension 内容及部分本地化图片caption上有错误提取。当前graph-only入口对已知不支持的markup拒绝，而不是剥掉标签或把失败页记为空边。已确认 `nowiki/pre/source/syntaxhighlight` 不可通过现有library选项安全修复；不能把继续增加少量guard当成完整解析正确性的证明。

独立复核另发现TemplateData字面内容错误生成边，以及图片caption可能进入 `links[].target`。相关回归与上游fail-closed修复进行中。`present`+空文本的producer/consumer不一致已修复；超JavaScript safe-integer的ID需要显式无损串编码，并在Python安全边界转为整数。

下一次真实运行必须先固定上游commit并复核接口。若仍不支持真实第27条记录，保持blocked；不自动抽掉该页、不换一份容易成功的归档，也不发布“完整局部图”。

### SQL

该日期categorylinks实际DDL有 `cl_target_id`，无 `cl_to`；当前来源绑定与相邻目录缺同源linktarget。不得拿category表ID、跨年份ID或字段位置猜测替代。SQL staging与融合未启动；原季度来源计划v1未被覆盖或悄悄换源。

## 测试与产物状态

主项目当前65项测试通过，含图/Parquet合成fixture、SQL流式语法、嵌套字段隐私、ID无损转换、分类alias/redirect与已有generation拒写。RED/GREEN日志保存在私有SSD evidence目录。合成fixture成功不能代替真实图产出。

上游修改保留在各自feature branch；最终commit、独立复核及发布状态应在本报告后续追加。旧来源计划和完整snapshot generation未升级，NGD未开始。

## 独立复核与执行版本

主项目8份新增代码/测试文件的完整diff经独立复核通过，无安全或阻塞逻辑发现；复核方实际运行65项测试全部通过。复核diff SHA256=`539aec4ab28873173229de36546cffa934803ca62a8fbda0b7d4181faef8ab85`，父流程再次比较当前代码，确认与该diff逐字节一致。复核结论仅覆盖这8份代码/测试，不把文档/dashboard或上游接口冒充同一复核范围；dashboard另通过真实HTTP/file/手机视口及P1状态显示检查。

真实失败运行的Go版本是`78436d1d0e0ee490368dd1bc7dc0e331462102a2`（clean）。WTF以`22269ed21249cd122f71d68c7018b55861025df4`为HEAD，但运行时工作树正在修复present-empty契约，**不是干净commit构建**。运行时`graph.js` SHA256=`1d1f5ffc4166c878107f837e5f08ba72d80d6a064769d0d0901a66b12bae8d08`，`graph-cli.js` SHA256=`cec5c6c12d7b603e957a23fbba9f8d8b54ec60829f3818813f0512b4ff4ce393`。因此该运行仅为失败诊断证据，不能晋升为版本固定的图generation。后续干净commit运行必须另建run目录，不覆盖旧证据。

## 私有证据定位（相对SSD项目根）

- `evidence/preflight/preflight-manifest.private.json`、`all64-headers-manifest.private.json`。
- `evidence/preflight/independent-full-01/proof.json`及metadata-only逐页结果。
- `pilot/runs/selector-real-01/proof.json`、`selector.stderr.log`及逐页metadata/hash。
- `pilot/runs/pipeline-real-01/code-inputs.private.json`、`pipeline/*.stderr.log`、未提交的graph-only `.partial`。
- `evidence/upstream-selector-real-time.log`、`pipeline-real-01-time.log`。
- `evidence/history-selection/`、`evidence/wtf-graph/`、`evidence/sqlstream/`及主项目RED/GREEN日志。

公开dashboard只更新P1工作项为受阻，不改206份计划的来源/version，不显示上述私有路径或未验证节点/边统计。当前进度是静态证据声明，不是后台任务监控。
