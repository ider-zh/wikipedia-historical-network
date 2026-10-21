# Parquet 数据契约 v1（图产物尚未生成）

默认 Parquet + ZSTD；目录按 wiki / snapshot / recipe generation / relation 分区，文件内按 source_id 排序，ID尽量uint64。字符串使用UTF-8，列表使用Parquet/Arrow原生LIST，不把target_id_list序列化为JSON字符串。实际rowgroup/压缩级别需要中文试跑测量后固化；不能把测试数据的压缩率外推为英文历史体积。

## 核心关系

| 文件/视图 | 主键与字段 | 说明 |
|---|---|---|
| pages | wiki, snapshot, page_id:uint64, ns:int32, title:string, selected_revision_id:uint64?, revision_time:timestamp[us,UTC]?, redirect:bool, redirect_target_title:string?, source_set_id:string, quality_flags:list<string> | 不存page text/comment/editor/IP |
| page_links | source_id:uint64, target_id_list:list<uint64> | 每source一行；目标排序去重；方向source→target |
| page_categories_xml | source_id:uint64, target_id_list:list<uint64> | 目标为category registry ID，不是跨年直接复用SQL整数 |
| page_categories_sql | source_id:uint64, target_id_list:list<uint64> | 同源page表先解码；单独保留SQL时点身份映射和unresolved |
| category_links_xml/sql | source_id:uint64, target_id_list:list<uint64> | child category→parent category，允许环，诊断另表 |
| category_registry | category_id:uint64, wiki:string, canonical_title:string | 规范化策略版本固定；禁止混用page ID和registry ID |
| category_union | source_id:uint64, target_id_list:list<uint64>, source_mask_list:list<uint8> | 两个列表按位置一一对应，mask:XML=1,SQL=2,both=3 |
| unresolved_links | source_id, target_title, namespace, reason, source_set_id | 保留无法历史定位/红链等原因，不捏造目标ID |
| source_observations | source_set_id, source_date, target_time, offset_days, extraction_version, quality_flags | 融合视图可追溯到源层，不只保留合并后的黑盒结果 |

“页面没有链接”保留空列表，和“页面解析失败/正文不可用”分开状态。相同source不应因重复物理副本生成多行；观测冲突另表。自环、重复引用和redirect折叠前后的计数应明确。

category_union的来源mask列表增加少量存储但不可省略，否则无法撤回较晚SQL带来的近似边。更早SQL出现时重建SQL观察及union而非重写不可变XML观察。

## 分类回填的视图引用契约

目标T分类侧不可重建时，按[分类回填策略](category-fallback-policy.md)引用同wiki之后最近合格时点C的完整分类侧generation。新增view manifest记录`category_fallback_policy`、`category_mode`、`target_time`、`category_effective_time`、精确正时间偏差、`category_origin_snapshot_id`、`category_origin_generation_id`及manifest SHA256、原生失败原因和跨时间质量标记。引用式复用不要求复制整套Parquet。

XML/SQL mask是C的来源标记，不代表T同期关系；C的page/category整数域不能直接接入T。若需投影到T的页面集合，身份映射和unresolved需单独版本化。分类侧视图更新只使相关分类统计/映射失效，不改写T的page network或旧分类generation。目前是存储契约，回填writer/registry尚未实现。

## 服务无依赖边界

落地存储无需数据库服务；PyArrow批处理读写，未来可加DuckDB嵌入式查询。wikitext解析如以临时worker/HTTP进程运行，不改变存储层无服务设计。page text只在selected revision流中转瞬存在，解析后丢弃；不能为了不落地正文而声称不必读取正文。

## 初期验证与资源

`whn/storage.py` 已提供并测试最小有向adjacency写入契约：只允许source_id/target_id_list，拒绝正文等多余字段，要求source有序且唯一，targets去重排序，ZSTD，临时文件完成后原子发布，不覆盖已有文件。它不是XML/wikitext解析器，也不是整个graph builder；仅合成fixture写读实测，不冒充真实维基图已经产生。

每个热点文件必须有source-recipe与SHA256；catalog和plan也导出Parquet，原始路径细节仅私有目录。构建前验证所有分片和源hash，不仅文件数量。保留足够SSD余量，并发/rowgroup/最大list内存经中文试跑确定。

指定SSD为noexec挂载：原生执行依赖(PyArrow共享库/浏览器)安装在主机运行环境；**所有业务数据、缓存、staging、spill、清单和输出仍在指定SSD**。不擅自remount改变安全属性。无pip的当前解释器通过校验PyPI wheel的临时bootstrap安装依赖，后续普通环境可以标准venv+pip安装锁定版本。

依赖参考：Apache Parquet logical LIST规范 https://parquet.apache.org/docs/file-format/types/logicaltypes/ （本次实际取回HTTP200）；PyArrow版本见requirements.txt，项目实测Python3.14。
