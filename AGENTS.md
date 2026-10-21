# Agent working rules

- User-approved scope: enwiki primary, zhwiki validation; quarter ends UTC from 2001 Q1; page/category graph first, NGD definition deferred. See docs/architecture.md and docs/source-policy.md.
- Code/config/docs are owned by this repository. Private full inventories, raw paths, staging, spill, cache, Parquet and graph output live under the configured SSD project directory; never commit them. Public dashboard projection must omit host addresses, mount paths, disk identifiers, credentials and private files.
- Inventory source files read-only; do not start database servers, alter mounts, delete sources or silently repackage original archives. Inventory stat evidence is not full checksumming, CRC validation, official completeness or successful historical reconstruction.
- Stream XML through wikipedia-dump-parser; reuse wtf_wikipedia_server for graph-only wikitext extraction. Required parser changes belong in those upstream repositories with tests and pinned revisions, not a second parser here. Transient selected-revision wikitext is permitted; no persistent page body output.
- Prefer typed Parquet with ZSTD, sorted/deduplicated list-valued adjacency per source ID. Preserve source-specific category observations before union; future SQL is an explicit approximation. Resolve SQL page IDs within its own dump, never blindly join across years.
- Historical graph must choose latest revision <= target time; preserve ambiguity, deleted-history survivorship bias, historical-title uncertainty, missing targets and invalid/cyclic category relations instead of claiming exact recovery.
- Source choice and graph generation are distinct immutable versions. Append new manifests and supersedes links; do not overwrite old snapshot versions. Block a build if fingerprint/hash verification, shard coverage or required identity mapping is unresolved.
- Do not launch bulk extraction until the plan and capacity pilot pass. No public service deployment is implied by generating a local static dashboard.
- Use TDD for executable changes; run actual commands and retain real RED/GREEN evidence on the SSD. No fabricated inventory, test output or build progress.
