# Wikipedia Historical Network

面向 **enwiki（重点）与 zhwiki（快速验证）** 的历史页面图 / 分类图重建项目。以已有 XML history 与 SQL dump 为依据，从 **2001 Q1** 起按季度末 UTC 制定可追溯来源计划，之后逐步构建图和统计。**NGD 的公式与计数口径尚未确定，本阶段不计算 NGD。**

## 核心约束

- **历史来源不等于精确历史全貌。** 后期history可能已丢失被删除的早期页面/修订；页面可更换身份或历史迁移，不能只靠标题或page ID。
- XML为页面网络与部分分类关系提供来源；SQL补充分类别与分类层次。保留两层观察再做 `category graph = XML ∪ SQL`，较晚SQL标为跨时间近似。
- 图数据优先 **Parquet + ZSTD**；adjacency采用一行 `source_id, target_id_list`，列表原生类型、排序去重。
- 不持久化page text；wikitext仅在流式选中修订后暂存并解析，结果仅标题/ID/redirect/link/category等图字段。
- 原始源文件只读；处理缓存、spill和数据产物落指定SSD项目目录。私有path/host信息不进Git或dashboard。
- 来源计划和实际构建是不同状态；新增来源产生新version，不覆盖旧snapshot generation。

## 当前实测（2026-10-21）

已为三台机器保存逐文件metadata索引及错误/覆盖清单，生成 **206份季度来源计划（enwiki、zhwiki各103份，2001Q1—2026Q3）**，204份有候选XML，2份2026Q3因缺少覆盖目标时点的XML而阻塞。所有来源仍须执行前验证；**图构建为0，NGD未开始**。32条访问/缺根错误有明确记录，不声称未知目录全部已查。

- [中文季度P1试跑报告：XML验证通过、图构建受阻](docs/pilot-report.md)
- [初始化实测报告](docs/initialization-report.md)
- [逐季度来源组成CSV](dashboard/data/quarterly-plan.csv)
- [静态dashboard入口](dashboard/index.html)（下载后打开或本地静态HTTP；未部署公共站点）

## 文档入口

| 文档 | 内容 |
|---|---|
| [历史研究背景](docs/research-background.md) | 删除、重建、修订迁移、重复RID与历史恢复偏差 |
| [项目架构](docs/architecture.md) | 模块边界、数据流、身份与验收 |
| [选源规则](docs/source-policy.md) | XML时序资格、SQL最近日期、近似union |
| [存储契约](docs/storage-schema.md) | Parquet字段、adjacency、来源层与资源约束 |
| [上游复用](docs/upstream-reuse.md) | XML / wikitext / 编排项目的实际审阅与固定版本 |
| [索引契约](docs/inventory-contract.md) | metadata索引证据与完整性边界 |
| [工作计划](docs/work-plan.md) | 初始化→中文试跑→英文→NGD→新数据/冷迁移 |
| [静态dashboard](docs/dashboard.md) | 公开安全JSON契约、file/HTTP预览与QA |

## 本地使用

普通开发环境（Python >=3.11）：

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

依赖只安装在可执行的主机环境。数据盘如noexec，不应remount或把原生库直接放在noexec目录加载。运行时把 `TMPDIR` 指到SSD的staging目录。

已有真实私有inventory后，生成Parquet索引、季度计划和dashboard：

```sh
python -m whn.project \
  --inventory "$WHN_INVENTORY" \
  --data-root "$WHN_DATA_ROOT" \
  --public-dir dashboard/data \
  --as-of "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

多份inventory可重复传 `--inventory`。`WHN_DATA_ROOT` 必须指向专用SSD项目目录，不能指到现有原始dump目录。相同recipe重复执行不增加version；来源变化追加到私有 `plans/versions/<snapshot>/vNNNN.json`。目前这是计划生成器，不会启动XML/SQL大规模提取。

静态dashboard无需Node服务和构建步骤：

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory dashboard
```

或直接打开 `dashboard/index.html`（使用随清单生成的安全JS回退）。预览仅绑定本机，不等于已部署GitHub Pages或公网服务。

## 仓库与私有数据边界

```text
whn/                 来源集、季度planner、版本、Parquet最小契约
 tools/              只读源索引工具
 tests/              TDD与契约测试（仅fixture）
 docs/               架构、研究背景、规则和实测说明
 dashboard/          纯静态页面与经过allowlist的计划JSON/JS

SSD / catalog/       完整私有逐文件索引、来源位置映射、Parquet
SSD / plans/         不可变季度来源版本、latest注册表、Parquet
SSD / staging|spill/ 流式作业临时目录
SSD / snapshots/     后续真实图generation（当前未构建）
SSD / evidence/      索引和测试/浏览器QA证据（不公开原路径）
```

上游复用：[wikipedia-dump-parser](https://github.com/ider-zh/wikipedia-dump-parser)、[wtf_wikipedia_server](https://github.com/ider-zh/wtf_wikipedia_server)、[wikipedia-dump编排参考](https://gitee.com/ider001/wikipedia-dump)。需要修改提取行为时回到对应上游加测试并固定commit，不在此复制一套解析器。

详细当前真实索引计数、覆盖缺口和每季度来源，请以初始化实测报告和dashboard中的最新generated_at为准；目录扫描、候选资格和计划均不证明图已经构建。
