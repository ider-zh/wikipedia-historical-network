# Quarterly SQL provenance caveat

Inspection: 2026-10-21 UTC. **The sampled quarterly SQL must not be treated as original contemporaneous Wikipedia SQL snapshots or automatically eligible nearest-date SQL.**

## Decision

- Confirmed representation: later logical SQL exports, with compact page/link/category schemas and a mydumper-style file/metadata layout.
- Original acquisition and transformation lineage: **unknown**. A reconstructed or transformed historical graph dataset is strongly suspected, not proven. Re-export of an older source is also possible; the inspection cannot distinguish these alternatives.
- Eligibility: **blocked / unknown provenance**, including when approximate SQL is permitted. Date-shaped database/directory names are target labels, not verified capture times, revision cutoffs or completeness guarantees.
- Preserve these acquired files. This decision neither rejects their future utility nor authorizes replacement or deletion.

## Actual bounded observations

The three `enwiki20041231.{categorylinks,pagelinks,page}.00000.sql.xz` files were opened through a streaming XZ reader. Each exposed only four session-setting lines before an `INSERT` statement prefix; inspection stopped before values. Their DDL is in separate `*-schema.sql.xz` files, not in those data-file headers. The settings include `SET NAMES binary`, disabled foreign-key checks, `NO_AUTO_VALUE_ON_ZERO,NO_ENGINE_SUBSTITUTION`, and session `TIME_ZONE='+00:00'`. These are export settings, not historical cutoff evidence.

The neighboring `metadata` file reports:

```text
# Started dump at: 2024-06-29 13:40:56
# Finished dump at: 2024-06-29 13:43:47
```

The metadata timestamps have **no explicit timezone**. The SQL session timezone does not establish the metadata clock's timezone. These timestamps date the declared export run, not acquisition of underlying historical records.

The selected DDL has these columns, all nullable with ordinary secondary indexes:

| Table | Observed columns |
|---|---|
| `page` | `page_id`, `page_namespace`, `page_title`, `page_is_redirect`, `page_revision_id` |
| `pagelinks` | `pl_from`, `pl_from_namespace`, `pl_title`, `pl_namespace` |
| `categorylinks` | `cl_from`, `cl_to`, `cl_type` |

All sampled schemas declare InnoDB and `DEFAULT CHARSET=utf8`; titles/targets are `varbinary(255)`. The compact page table has no revision timestamp, cutoff, origin-dump identifier or historical-title provenance. A `page_revision_id` field name alone does not prove which revision was selected or how its ID relates to other datasets.

The same column sets were observed across all seven sampled quarters. Some page/pagelinks index names differ between the 2001 and later samples; no byte-identical-schema claim is made.

### Neighboring quarters

The following are **metadata-declared row counts, not counted or validated records**:

| Target label | page | pagelinks | categorylinks | Declared export date |
|---|---:|---:|---:|---|
| 2001-03-31 | 726 | 3,678 | 0 | 2024-06-29 |
| 2001-06-30 | 3,104 | 16,046 | 0 | 2024-06-29 |
| 2001-09-30 | 9,082 | 66,048 | 0 | 2024-06-29 |
| 2001-12-31 | 20,160 | 233,032 | 0 | 2024-06-29 |
| 2004-09-30 | 488,312 | 8,927,653 | 276,612 | 2024-06-29 |
| 2004-12-31 | 626,048 | 11,541,501 | 562,380 | 2024-06-29 |
| 2005-03-31 | 755,793 | 13,854,477 | 726,307 | 2024-06-29 |

Each sampled 2001 directory contains a categorylinks schema and metadata section declaring zero rows, **but no categorylinks data shard**. This is not evidence that a 2001 operational categorylinks table existed, nor that historical category coverage is complete. A later export can create an empty schema for an earlier target.

For independent schema context, the official MediaWiki manuals identify `categorylinks` with MediaWiki >=1.3 and `page` with >=1.5, and describe `page_latest` rather than this export's `page_revision_id`. They do not establish this dataset's lineage. References retrieved on 2026-10-21: `https://www.mediawiki.org/wiki/Manual:Categorylinks_table` and `https://www.mediawiki.org/wiki/Manual:Page_table`.

## Known orchestration is not established provenance

The existing Gitee project was inspected at commit `c50f4e991cc96833edc914c586593a1057cb2767`. Its complete tree listing reported `truncated=false`. Five selected source/readme blobs were fetched and verified against their Git blob SHA1s. In `goDump/cmd/s01ExtractPageFromXml.go:35-44`, the command invokes `ExtractArticleXMLByGRPC`; `goDump/internal/extract/extract_xml_to_json.go:25-28` reads version-labelled `pages-articles.xml.bz2` and writes JSON, and line 128 passes `item.Revisions[0].Text.Value` to the parser. Those inspected files do **not** demonstrate production of the sampled quarterly SQL exports, a latest-revision-at-quarter-cutoff algorithm, or original input identities. Do not attribute these SQL files to that code without a matching recipe/run manifest.

## Required before enabling source selection

1. Recover the export/creation recipe and pinned producer revision, original input identities and hashes, run manifests and the relation between target labels and actual record time.
2. Establish revision cutoff and tie-breaking rules, page/revision ID domains, historical title handling, redirect/namespace scope, deleted-history survivorship and link/category extraction semantics.
3. Verify complete shard coverage, immutable input fingerprints/hashes and actual table identity mappings. Validate category data absence explicitly rather than replacing missing shards with assumed empty history.
4. Classify separately as original capture, re-exported original, reconstructed graph or other transformed source. If approximation is approved, retain that classification and uncertainty in the immutable source manifest; never promote a filename into capture provenance.

This finding applies directly to the seven sampled directories. Other quarterly directories are **uninspected**, not cleared by association; absent separate provenance, keep them ineligible too. No source-planner implementation was changed in this task.

## Commands, evidence and limits

The private SSD evidence bundle is keyed `evidence/sql-provenance/`; private host/mount identifiers are intentionally omitted here. The actual SSH argv and source script are retained privately. Equivalent command shape:

```sh
ssh -o BatchMode=yes -o ConnectTimeout=8 "$SOURCE_HOST" 'python3 -' < probe.py
ssh -o BatchMode=yes -o ConnectTimeout=8 "$SOURCE_HOST" 'python3 -' < verify.py
```

`probe.py` lists directory/file metadata and streams only bounded SQL header/DDL text (16 KiB header cap, 2 KiB line cap), stops at a data-statement prefix, and allowlists export timestamps/metadata section names. `verify.py` extracts only numeric metadata counts and reads back file sizes/mtimes. Metadata reads are bounded in the header probe; readback covers the small selected metadata files. XZ libraries may internally buffer compressed/decompressed blocks; no record values were extracted, emitted or retained. No body/user tables were opened, SQL imported, database started, remote script written, archives repacked, source file explicitly written, or mount altered. Ordinary reads may update access times under the existing mount policy.

Private evidence: `remote-discovery.json`, `remote-headers.json`, `remote-readback.json`, `probe.py`, `verify.py`, execution/verification records, `upstream-tree.json`, `upstream-sources.json`, and `evidence-manifest.json`. Before/after sizes and mtimes matched for every sampled directory entry. This is stat evidence only: no full source hashes, full data decompression, data-shard CRC validation, row counts, body/record sampling, restore, graph reconstruction or cross-quarter identity validation was performed. Evidence-file hashes identify this inspection bundle, not the underlying SQL payloads.
