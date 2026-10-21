# 上游复用审计与更新边界

审计日期：2026-10-21。**本阶段只读检查，不修改上游、不安装运行解析服务、不构建图、不提交或推送。** 本仓库负责编排、季度选择、来源/版本记录与图装配；XML 解码及 wikitext 解析的必要改进回到指定上游维护，不在这里复制一套解析器。

## 指定上游P1追加（2026-10-21）

下文保留P0只读审计的历史状态，不代表目前未做上游开发。P1已在两个上游各自的feature branch实现opt-in历史选择与graph-only CLI，测试及真实XML选择见[试跑报告](pilot-report.md)。真实wikitext仍因literal markup拒绝；SQL身份映射亦受阻，不能把新接口和合成测试写成完整季度图已验证。最终commit及复核/发布状态在试跑报告追加；legacy API不被此P1调用替代。

## Parent integration note

后续父流程已创建并实测SSD的项目专属目录；不改变此前审阅时PermissionError这一事实。上游检查采用只读替代路径，项目现在的staging/catalog/plan可以写入指定SSD。原生可执行依赖位于主机运行环境，因SSD为noexec挂载；业务处理数据仍全部在SSD。

## 1. 固定到实际检查的版本

| 项目 | 实际 commit | 检查方式与复用角色 |
|---|---|---|
| `ider-zh/wikipedia-dump-parser` | `87039da130d49835b8cbdc5009d7e3be8bc4f543` | 本机已有干净 checkout，与远端 HEAD、`v0.0.5` tag 一致；读取 tracked Go 源码。复用压缩 XML 读取/解码接口。[1] |
| `ider-zh/wtf_wikipedia_server` | `a66606691252165d9135ce9c0c12fa4a3604741f` | `git ls-remote` 后按此 commit 下载 GitHub 源码归档并在内存读取。复用 wikitext 服务、tiny worker 与既有回归用例。[2] |
| Gitee `ider001/wikipedia-dump` | `c50f4e991cc96833edc914c586593a1057cb2767` | `git ls-remote` 成功；Gitee commit tree API 返回 `truncated=false`，按 tree 指定的 blob ID 读取 14 个相关文件并校验 Git blob SHA1。作为已有编排/图与 SQL 适配参考，不照搬常驻数据库链路。[3] |

计划在指定 SSD 的 `upstreams/` 建临时 checkout，但该项目目录在本执行环境不可写，创建目录即 `PermissionError`，因此没有执行成功的 clone，也没有改写本机已有 checkout。替代读取已覆盖以下入口；没有把“获取了 HEAD”当作“读到了源码”。Gitee 页面路由失败后 API 成功；两个试探性 GitHub 同名镜像均返回 repository not found。以上是本次检查的 pin，不保证未来 HEAD 不变。

`evidence-background.json` 保留三个 pin 和 11 个关键源文件的 SHA256；完整上游代码、私有数据位置、环境文件均不复制进公共仓库。Go parser 的 module 声明 Go `1.23.2`；Gitee `goDump/go.mod` 声明 Go `1.24.4` 并依赖 parser `v0.0.5`，恰好对应所查 parser commit。WTF `package.json` 声明 `wtf_wikipedia ^10.4.2`，lockfile 实际锁定 `10.4.2`；复现应固定 lockfile，而不是只记录 semver 范围。[1][2][3]

## 2. Go XML parser：实际接口与内存边界

模块导入路径是 `github.com/ider-zh/wikipedia-dump-parser/wikiparser`。`wikiparser/wikiparser.go:228–316` 的两个 mixed-flow 公共入口为：[1]

```go
ParseBzipXmlMixedFlow(filePathList []string, threadCount int, nsScope []int32) (<-chan *Page, <-chan string)
Parse7zXmlMixedFlow(filePathList []string, threadCount int, nsScope []int32) (<-chan *Page, <-chan string)
```

返回页面通道及完成文件通道；两者都要持续消费。`318–396` 的 `ParseBzipXmlSeparateFlow` / `Parse7zXmlSeparateFlow` 接受 `callback func(pageChan <-chan *Page, filePath string)`；callback 必须把该文件页面通道读完再返回。实际路径是 compressed reader → `extract_xml_to_page_by_golang_ext` (`58–153`) → `encoding/xml` token/`DecodeElement` → page channel；不是另一个 `xml-stream-parser` 函数，后者存在于源码但不在这些公共入口的调用链里。[1]

`model.go:4–38` 定义 `Page{ID,Ns,Title,Redirect,Revisions []Revision}`；`Revision` 包含 `ID,Parentid,Timestamp,Text,Comment,Model,Format,Contributor`，`Text.Value` 是正文字符串。`nsScope` 为空表示不过滤，否则使用 namespace 集合。[1]

**可复用的优点：** 7z/bzip2 直接读取，不需要整份解压 XML 落盘；按文件开 worker，页面通道提供背压；页面/修订 ID 使用 `int64`，namespace 使用 `int32`；调用者可保留来源文件身份。它是“文件流式、页面级交付”，不是“修订级有界内存”。[1]

**必须在上游补齐并测试的门槛，不是本仓库已实现的能力：**

- `119–122` 把每次 `DecodeElement(Revision)` 结果追加到 `page.Revisions`，而每条修订保留 `Text.Value`。大历史页面会积累全部正文，255 个 buffered pages 及多 worker 会放大峰值；当前没有季度 cutoff、选中修订回调或 revision stream。[1]
- Go 的 token API 不等于每段字符数据自动限长：`encoding/xml` 的 `text` 实现使用内部 buffer 收集字符内容。即使只是忽略 token 或跳过非目标 namespace，也不能由此承诺正文内存常数有界。需要在上游验证大文本 token、CDATA、实体、UTF-8 与 CRLF 语义，不能简单按字节截断 XML。[11][14]
- `94–104` 对单个 `CharData` 做断言且忽略若干解析错误；`119–122` revision 解码出错仅 warn 后仍追加；fatal 日志会退出进程，没有可恢复的 error channel。需要严格失败、取消/错误传播、结构与 root/EOF 校验及可重启输出协议。[1]
- 7z 入口直接取 `File` 的第零个成员 (`295,379`)，没有“唯一且非加密目标 XML member”的入口校验；现有 completed-file 字符串不是内容哈希、CRC/字节数与持久化原子提交证明。[1]
- mixed flow 的 completed-file buffer 是 2048，忽略它在文件数足够多时会阻塞。跨文件页面顺序不确定；不要用通道到达顺序选“最后修订”或解决重复 RID。[1]
- 模型未完整表达缺失/空/隐藏状态：text/contributor 的 deleted 是字符串，comment 没有 deleted presence 字段；也没有 revision SHA1 或多内容 role 结构。需显式区分 hidden 与 present-empty，按实际 export schema 支持或拒绝多内容格式；不将未知字段当已验证支持。[1][23]

建议在上游加新的 opt-in revision/selection API，保留现有 API 兼容；让本仓库传季度 UTC cutoff、namespace 和 source identity 并消费结构化结果。选中规则需比较 `(timestamp, revision_id)` 并明定同秒 tie-break，不依赖 XML 顺序；同 RID 跨页冲突应保留证据而非任取一条。所有这些均为下一阶段提案。

## 3. WTF：实际 tiny 输出不等于完整 graph-only 契约

入口是 npm scripts 指向的 `expressServer.js` 或 `grpcServer.js`，不是 `package.json` 中并不存在的 `index.js`。HTTP `POST /api/wikitext` 接收 `{wikitext: string}`，返回 HTTP 201 的 `{text: plaintext}`；它不是图关系接口。gRPC 使用 `wikiTextParser.WikiTextParserService/GetWikiTextParse`，请求 `WikiText{text:string}`、响应 `JsonText{text:string}`；响应 text 还需要一次 JSON decode。两边 proto 的字段/service 相容，Gitee proto 另有 Go package option。[2][3]

`grpcServer.js:9–28` 接受 `--host/--port/--worker full|tiny`，默认 `0.0.0.0:30051`、full，Piscina dispatch 到相应 worker。`worker_tiny.js:55–116` 实际禁用 images/sections/coordinates/infoboxes/plaintext，保留 categories，并另取 `doc.links()`：按 `raw` 去重、按 `type` 分组、删除各项 `raw/type` 后 JSON.stringify；无数据的字段可能被省略。因此不能声称它已按规范化 target ID 去重，或保证只有固定字段。[2]

| 项目 | 所查 commit 的实际行为 | 建议上游新增的 graph-only 契约（尚未实现） |
|---|---|---|
| 请求 | 只有正文；无 wiki、revision ID、cutoff、schema version。[2] | 用 request ID 与外层元数据关联；明确语言/namespace alias 和规范化版本。 |
| 输出 | tiny 的 category 名与按类型分组的 link 对象；full 还会产 plaintext 等字段。[2] | allowlist：category target、internal link target/fragment、redirect observation、状态/诊断；不含 plaintext、原始 wikitext、显示锚文本、图片/信息框/章节。 |
| 去重 | `uniqBy("raw")`；相同 target 可来自不同 raw 写法。[2] | 解析后按明确 title/namespace 规则形成 target key；本仓库按最终 target identity 去重，保留 unresolved。 |
| 错误与隐私 | 见下段，可能写正文与日志片段。[2] | 默认禁止请求/正文/响应全文日志与 crash case 落盘；只记 ID、hash、错误码、版本与计数；安全合成 fixture 回归。 |

**直接复用前必须处理的实际泄漏点：** `crashCase.js:21–40` 会把至多 5 MiB 的完整输入写入 `data/crash-cases/`，tiny/full/HTTP 都会调用；`grpcServer.js:80–84` 还会打印前 500 字符。Gitee handler 在失败/空结果时 `.Any("item", item)` 可把含正文的 Page 整体写日志。现有 tiny 仅减少正常输出，并没有实现“正文绝不落盘”。这些开关应回到各自上游改，不能仅靠本仓库丢弃 plaintext 宣称满足约束。[2][3]

`grpcServer.js:67` 对输入再次 `he.decode`；Go XML 解码后字符实体已经处理过，因此端到端需测双重解码是否改变本应保留的字面实体。现有 sanitize 会钳制或移除 percentage 家族模板，fallback 也可能再次失败；要输出 parse/fallback 状态。gRPC 自定义上限是 `1_000_000_000` 个 JS 字符，不是 README 所说 10MB，也不等于传输层 message limit。正式批处理应固定较小的字节上限、deadline、有限队列/并发和消息大小，并在回归测试里验证。[2]

**正文必须瞬时存在，但不保留派生正文。** 解析所选历史 revision 的链接/分类需要其 wikitext 在 reader、Go/JS 内存及本地 RPC 中短暂存在；“不保留正文”不是 metadata-only 扫描。未来 graph-only 模式应在选中正文解析后释放引用，不写出解压正文、完整 page/revision JSON、plaintext、crash 输入或正文日志。原有只读压缩来源归档属于输入，不意味着可以新增正文副本；本阶段没有执行正文处理。

## 4. Gitee orchestration：可参考什么，不能直接拿来做历史季度

已沿活动命令追踪：`goDump/main.go:19–24` → `cmd.Execute()` → `cmd/s01ExtractPageFromXml.go:35–44` → `extract.ExtractArticleXMLByGRPC`。其 `extract_xml_to_json.go:25–98` 读取 `{input}/{lang}/{version}/{lang}wiki-{version}-pages-articles.xml.bz2`，parser 用 namespace `[0,14]`；20 个 handler 调 RPC，写 `{lang}wiki-{version}-pages-articles.json.zst_tmp` 后 rename 到 `.json.zst`。实际文件名不是命令帮助里的 `.ndjson.zstd`。[3]

handler (`100–155`) 对非 redirect 只取 `item.Revisions` 首条修订的 `Text.Value`；redirect 直接写 `id/ns/title/redirect`；普通页写服务返回的整个 map 再加 `id/ns/title`。`streamConfig` 的环境键为 `WIKITEXT_PARSER_GRPC_URL`，默认 `localhost:50051`，与 WTF 默认 `30051` 不同，联调用配置显式统一。此命令面向 pages-articles，不是历史 revisions 截止选择；不能把输入文件换成 history 就得到季度快照。[3]

后续 `cmd/s02BuildWikipediaGraph.go:26–33` → `graph.BuildGraphFromNDJson` (`graph.go:459–544`) → `buildPageGraph` (`88–457`)；它把所有页面和多个标题索引装入 map，读 `links.internal[*].page` / `categories`，生成含出入邻接的 `.json.zst`。这提供字段对接与重定向处理参考，但不是外部内存的大规模季度图算法。[3]

复用前的具体风险：标题清洗会全串 lower-case (`63–65`)，不能冒充 MediaWiki 完整标题规则；redirect 最多追三次；category→page 原始标题命中分支 `368` 使用 `item.ID` 而非 `subItem.ID`，是静态发现的可疑错连点、未在本次复现；输出 `516–521` 会略过已解析 redirect 与孤立点；失败续跑仅按目标文件存在跳过，rename 错误未检查。这些语义均不宜直接继承。[3]

SQL 参考接口位于 `internal/graph/transformPageInDegreeInNthCategoryToPg/`：`extractCategoryLinks.ExtractCategoryPageTree(filePath)` 返回分类名→普通页 ID / 子分类 ID 两张 map；`extractPageSql.ExtractPage(filePath)` 返回普通页/分类标题→ID map。前者固定 9 列、后者固定 12 列，均先按字面 `),(` 拆元组且 scanner 上限 64 MiB；前者依赖旧 `cl_to`。官方 categorylinks 文档列出多代 schema，包括 `cl_target_id` 与不再含 `cl_to` 的布局。要按每个 SQL dump 的 DDL/列名解析，测试引号、转义及历史列变更；不要盲用固定索引、也不要把这套 map 构造称作流式有界内存。[3][17]

## 5. 更新责任与验收

- **parser 上游：** revision streaming/季度选择接口、隐藏与多内容状态、错误/取消、成员与完整性校验、大历史页内存回归。
- **WTF server 上游：** graph-only allowlist、no-retention、避免重复实体解码、语言 fixture、fallback 状态、上限与背压；沿用现有 tests 但加严格字段断言与“无正文写出”测试。
- **Gitee 上游：** 若继续复用它的执行链，在那里改 logging、配置、错误提交与 SQL schema 适配；仅作参考而不调用的代码不在这里复制。
- **本仓库：** orchestration、来源与选中 revision provenance、身份解析、XML/SQL 分类来源标记、Parquet/图组装、版本失效规则；pin 上游新 commit 后再跑中文有界 pilot，再决定英文规模。

此次是源码/接口审计，不是 parser benchmark 或依赖兼容性验收。没有运行现有 Go tests（tracked tree 不含其引用的 testdata）、npm tests、服务或图命令；没有拿静态检查替代集成测试。下一阶段必须实测多季度选择、真实/合成大页、hidden/empty、namespace aliases、redirect 环、重复 RID、取消/重试、输出 hash 与内存峰值，才能将状态从 planned 改为 validated。

## Sources

[1] https://github.com/ider-zh/wikipedia-dump-parser/tree/87039da130d49835b8cbdc5009d7e3be8bc4f543
[2] https://github.com/ider-zh/wtf_wikipedia_server/tree/a66606691252165d9135ce9c0c12fa4a3604741f
[3] https://gitee.com/ider001/wikipedia-dump/tree/c50f4e991cc96833edc914c586593a1057cb2767
[11] https://pkg.go.dev/encoding/xml
[14] https://go.dev/src/encoding/xml/xml.go
[17] https://mediawiki.org/wiki/Manual:Categorylinks_table
[23] https://api.github.com/repos/wikimedia/mediawiki/contents/docs/export-0.11.xsd?ref=1.39.9
