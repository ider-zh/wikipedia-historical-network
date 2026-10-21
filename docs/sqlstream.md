# Bounded SQL dump streaming

`whn.sqlstream` reads graph-table MySQL dump text without a database service,
without retaining a table or INSERT statement, and without parsing page bodies
or contributor records. Only `page`, `categorylinks`, `linktarget`, and
`category` are accepted. It does not resolve identities or project graph fields;
callers must select fields and bind IDs within the same source snapshot.

## API

```python
import gzip
from whn.sqlstream import iter_rows, Limits, SQLStreamError

with gzip.open(source, 'rt', encoding='utf-8', errors='strict') as stream:
    rows = iter_rows(stream, 'categorylinks', max_rows=1000)
    for row in rows:
        # A fresh dict whose keys come from this dump's CREATE TABLE.
        consume(row)
    columns = rows.schema.columns
    status = rows.stop_reason
    count = rows.rows_yielded
```

`iter_rows(stream, table, max_rows=None, *, limits=None)` returns a `RowIterator`.
Input is a text reader (preferred) or iterable of text chunks. Text readers use
bounded `read(65536)` calls, **not** line iteration. Iterable chunks must each be
at most `limits.chunk_chars`; passing a huge preconstructed INSERT line is
rejected. The caller owns the stream and must close it.

* `.schema` is `None` before DDL is consumed, then immutable
  `Schema(table, columns: tuple[str, ...])`. There is no separate consuming
  `read_schema` API; this avoids losing a buffered INSERT prefix between readers.
* Rows are dictionaries of `str`, `int`, `Decimal`, or `None`. Decimal/exponent
  numeric literals use `Decimal`, avoiding float rounding. Strings, including
  binary/varbinary columns and `_binary'...'`, remain decoded Python text, not
  bytes. No title normalization or coercion by declared type is performed.
* INSERT column lists are optional. If present, each row maps exactly the
  explicitly supplied columns, in that order; omitted columns are not fabricated
  from defaults. Names must be unique and present in the DDL. Without a list,
  tuple arity must equal the DDL's actual column count.
* `.stop_reason` is `running`, `eof`, `max_rows`, or `error`; `.complete` means
  **only** that this iterator reached text EOF with supported SQL framing.
  `.rows_yielded` counts returned rows. On a row cap the status changes before
  that final row is returned. `max_rows=0` consumes no input or schema.
* `max_rows` must be `None` or a nonnegative integer. Reaching it is deliberately
  conservative: `max_rows` remains the reason even if the last returned row
  happens to be the physical final row. Caller abandonment leaves `running`
  unless it already hit the cap. A caught input or parse error marks `error`.

## Grammar and failures

The tokenizer handles quoted commas, semicolons and parentheses, doubled quotes,
backslash-escaped quotes/backslashes, NUL and MySQL control escapes, UTF-8 text,
`NULL`, signed integers, decimal and exponent numbers. Numeric literals are
limited to 128 characters. Unknown escapes are rejected rather than silently
rewritten. Backticks delimit identifiers; single quotes delimit strings.

A CREATE TABLE must precede INSERT, have unique supported scalar column names,
and match the requested table. Types include integer/numeric, binary/varbinary,
char/varchar, blob/text families, enum and timestamp/datetime. Constraints and
indexes do not become columns. Engine/charset dump options are not evaluated.
Duplicate CREATEs, missing schema, mismatched tables, unknown column types,
unknown/duplicate INSERT columns, wrong arity, expressions/functions, hex
literals, truncated statements/tuples/strings/comments and unrecognized statement
kinds raise `SQLStreamError`. This is a constrained dump grammar, not a SQL
validator or interpreter; type constraints/defaults and engine semantics are
not enforced.

Ordinary line/block comments are skipped. Versioned comments are inspected and
only recognized dump scaffolding is accepted: SET, DROP TABLE IF EXISTS,
LOCK/UNLOCK TABLES, and ALTER TABLE ENABLE/DISABLE KEYS. Table-bearing scaffolding
must match the selected table. SQL is never executed. SQL modes changing quoted
string interpretation (`NO_BACKSLASH_ESCAPES`, `ANSI_QUOTES`) are rejected.
`LOAD DATA`, REPLACE, database-qualified table names and arbitrary executable
versioned comments are unsupported, not silently skipped.

Rows can be yielded before the remaining INSERT suffix has been checked. A
caller must exhaust the iterator and check status before claiming that its
selected SQL input parsed successfully. Persist partial results only with
explicit prefix/error provenance or transactional staging.

## Resource limits

Defaults in `Limits` (positive integers, measured in Python characters):

| Budget | Default |
| --- | ---: |
| `statement_chars` | 64 Mi characters consumed per statement |
| `tuple_chars` | 1 Mi characters consumed per tuple |
| `field_chars` | 256 Ki decoded characters per field/token/comment |
| `ddl_chars` | 1 Mi characters for materialized DDL/scaffolding |
| `columns` | 256 |
| `chunk_chars` | 65,536 |

The statement limit is an input-work cap, **not a 64 Mi-character allocation**:
INSERTs are parsed token by token, retaining only one tuple, field/token, and
input chunk. DDL/scaffolding alone are materialized, under their smaller cap.
Python object overhead and Unicode width mean these are not exact byte/RSS
limits (a character can require up to four bytes, plus object overhead). Input
chunks have already been allocated by the caller before size checking. Returned
rows retained by the consumer are outside the parser's memory budget. These
limits deliberately reject unusually large extended INSERTs; increase them only
after an explicitly bounded capacity pilot, not to silently admit full history.

## Prefix provenance and real source check

A bounded run is **not** gzip CRC validation, full-file verification, checksum
verification, shard completeness, or historical identity reconstruction. Gzip
read-ahead is possible even with bounded text reads. Stopping before EOF does
not validate the compressed trailer. Even `complete=True` does not prove an
archive fingerprint or independently verify that a caller's input is a full
original file rather than a valid truncated selection.

A read-only check against the local selected `zhwiki-20251001` source consumed
**1,000 rows each** from page and categorylinks, stopping with `max_rows` and
`complete=False`; no full extraction or CRC verification was performed. Evidence
is retained privately under `evidence/sqlstream/real-prefix.json`.
The observed categorylinks DDL has **seven** columns:

```text
cl_from, cl_sortkey, cl_timestamp, cl_sortkey_prefix,
cl_type, cl_collation_id, cl_target_id
```

There is no `cl_to` in this source: the caller needs matching-source
`linktarget` identity resolution for `cl_target_id`, not a guessed nine-column
mapping. The observed page DDL has twelve named columns; neither count is
hardcoded into the parser.

## Tests

```sh
python3 -m unittest discover -s tests -p 'test_sqlstream.py' -v
```

The suite exercises chunk boundaries, UTF-8/escapes, DDL names, explicit column
order, failure cases, budgets, no-read-ahead row caps, and a 20,000-tuple streaming
case with a tracemalloc peak assertion below 1 MiB. RED/GREEN command output is
retained privately under `evidence/sqlstream/`. These synthetic framing tests
and the real-source prefix check are not full-dump correctness certification.
