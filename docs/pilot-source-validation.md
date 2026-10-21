# Bounded Chinese pilot source validation

This preflight targets `2025-09-30T23:59:59Z`. Private evidence belongs under the configured SSD project's `evidence/preflight/`; original compressed pilot inputs belong under `pilot/input/`. Neither location belongs in the public projection.

## Handoff contract

`preflight-manifest.private.json` identifies the staged XML archive, cutoff, source IDs, compressed SHA256, retained dumpstatus checksum comparison, member CRC/size, SQL schemas, blockers and remaining gates. `all64-headers-manifest.private.json` retains every original `7z l -slt -ba` result, source fingerprints, catalog-stat comparisons and filename-range analysis. `selected-staged.private.json` contains the independent remote/local compressed hash comparison and source before/after-copy fingerprints. `selected-prefix-probe.private.json` is a bounded, local metadata-only eligibility probe, not a complete XML validation.

The selected archive is `zhwiki-20251001-pages-meta-history6.xml-p9237651p9283260.7z`: 32,030,181 compressed bytes, 1,287,526,387 declared XML bytes, declared CRC32 `DCBAAED0`. An 8 MiB local decompressed-prefix probe observed cutoff-eligible namespace 0 and 14 pages. No decompressed content was persisted. The deliberately terminated probe did not validate EOF or CRC.

## Evidence boundaries

All 64 declared filenames match the observed directory names; their declared page-ID intervals have no gaps or overlaps. Their current size/mtime/device/inode agree with the catalog, and fingerprints did not change during header listing. This establishes consistency against the declared names, **not official shard completeness**. The full 64 compressed payloads were not hashed or CRC-tested.

The selected compressed file was copied without repackaging, independently SHA256-hashed remotely and locally, and source fingerprints compared before/after hashing and transfer. Its MD5 and SHA1 match the neighboring retained `dumpstatus.json` entry. That retained metadata has not been independently authenticated. The parent must still stream the local XML to EOF, verify decoder success, byte count and CRC, and validate selected revisions with the designated upstream parser.

## Independent full-archive check

The parent independently consumed the selected archive through Python Expat event handlers and `7z`, without persisting XML or body text. All 1,287,526,387 declared XML bytes were read; CRC32 matched `DCBAAED0`, the decoder exited zero, and Expat accepted the complete document. The staged compressed SHA256 was rechecked and the local file fingerprint remained unchanged. This validates this one archive only, not all 64.

The observed archive contains 44,221 pages and 105,128 revisions. Independent cutoff selection found 27,180 namespace 0/14 pages: 22,986 articles and 4,194 category pages. These are validation counts, **not produced graph counts**. The actual pilot will use an explicit 30,000-record cap because the observed eligible set exceeds the default 20,000; no bulk scope expansion is implied. Private proof and metadata-only comparison records are in `evidence/preflight/independent-full-01/`.

## SQL blocker

Bounded 65,536-byte gzip prefixes were inspected for `page`, `categorylinks` and `category`. All three contain CREATE TABLE declarations and INSERT statements; LOAD DATA was not observed in these prefixes. The private manifest records exact columns and gzip magic. This is not a full SQL payload scan or historical graph.

`categorylinks` has `cl_from`, `cl_sortkey`, `cl_timestamp`, `cl_sortkey_prefix`, `cl_type`, `cl_collation_id`, **`cl_target_id`**, and no `cl_to`. A same-source `linktarget` table is therefore required. It is absent from both the eight-file binding and neighboring directory. SQL staging/build stopped at this blocker; no unrelated SQL files were copied and no database server was started. Do not substitute category IDs, cross-year IDs or a prior date without a separately approved source choice and schema check.

## Helper tests

`tools/pilot_preflight.py` provides declared-range analysis and single-member header parsing only. Run `python3 -m unittest tests.test_pilot_preflight -v`. Actual sequential RED/GREEN evidence is retained privately as `tdd-01-*` and `tdd-02-*`. Full-suite evidence is separate; concurrent SQL-stream work outside this helper may affect that run.
