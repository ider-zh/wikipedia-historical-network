"""Bounded MySQL dump reader for graph tables, not a general SQL interpreter."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re

TABLES = frozenset({'page', 'categorylinks', 'linktarget', 'category'})
_TYPES = frozenset('tinyint smallint mediumint int integer bigint float double decimal numeric binary varbinary char varchar blob tinyblob mediumblob longblob text tinytext mediumtext longtext enum timestamp datetime'.split())
_NUMBER = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z')
_ESCAPES = {'0': '\0', 'b': '\b', 'n': '\n', 'r': '\r', 't': '\t', 'Z': '\x1a', "'": "'", '"': '"', '\\': '\\', '%': '\\%', '_': '\\_'}


class SQLStreamError(ValueError):
    """Unsupported, malformed, truncated or over-budget SQL."""


@dataclass(frozen=True)
class Limits:
    statement_chars: int = 64 * 1024 * 1024
    tuple_chars: int = 1024 * 1024
    field_chars: int = 256 * 1024
    ddl_chars: int = 1024 * 1024
    columns: int = 256
    chunk_chars: int = 65536

    def __post_init__(self):
        if any(type(v) is not int or v <= 0 for v in vars(self).values()):
            raise ValueError('limits must be positive integers')


@dataclass(frozen=True)
class Schema:
    table: str
    columns: tuple[str, ...]


class _Chars:
    def __init__(self, stream, limits):
        self.parts = iter(lambda: stream.read(limits.chunk_chars), '') if hasattr(stream, 'read') else iter(stream)
        self.part, self.pos, self.count = '', 0, 0
        self.start = 0
        self.tuple_start: int | None = None
        self.limits = limits

    def peek(self):
        while self.pos == len(self.part):
            try:
                self.part = next(self.parts)
            except StopIteration:
                return ''
            if not isinstance(self.part, str):
                raise SQLStreamError('text input required')
            if len(self.part) > self.limits.chunk_chars:
                raise SQLStreamError('input chunk character budget exceeded; use a text reader or smaller chunks')
            self.pos = 0
        return self.part[self.pos]

    def get(self):
        ch = self.peek()
        if ch:
            self.pos += 1
            self.count += 1
            if self.count - self.start > self.limits.statement_chars:
                raise SQLStreamError('statement character budget exceeded')
            if self.tuple_start is not None and self.count - self.tuple_start > self.limits.tuple_chars:
                raise SQLStreamError('tuple character budget exceeded')
        return ch


class _Tokens:
    def __init__(self, stream, limits):
        self.chars = _Chars(stream, limits)

    def next(self):
        c = self.chars
        while True:
            while c.peek().isspace():
                c.get()
            ch = c.get()
            if ch == '#' or (ch == '-' and c.peek() == '-'):
                if ch == '-':
                    c.get()
                    if c.peek() and not c.peek().isspace():
                        raise SQLStreamError('unsupported comment syntax')
                while c.peek() and c.get() != '\n':
                    pass
                continue
            if ch == '/' and c.peek() == '*':
                c.get()
                comment = []
                while True:
                    x = c.get()
                    if not x:
                        raise SQLStreamError('truncated comment')
                    if x == '*' and c.peek() == '/':
                        c.get()
                        break
                    comment.append(x)
                    if len(comment) > c.limits.field_chars:
                        raise SQLStreamError('comment character budget exceeded')
                value = ''.join(comment)
                if value.startswith('!'):
                    return ('VERSION', re.sub(r'^!\d*\s*', '', value))
                continue
            break
        if not ch:
            return ('EOF', '')
        if ch in "'`":
            value = []
            size = 0
            while True:
                x = c.get()
                if not x:
                    raise SQLStreamError('truncated quoted token')
                if x == ch:
                    if c.peek() == ch:
                        c.get()
                    else:
                        break
                elif x == '\\' and ch == "'":
                    escape = c.get()
                    if escape not in _ESCAPES:
                        raise SQLStreamError('unsupported string escape')
                    x = _ESCAPES[escape]
                size += len(x)
                if size > c.limits.field_chars:
                    raise SQLStreamError('field character budget exceeded')
                value.append(x)
            return ('STR' if ch == "'" else 'ID', ''.join(value))
        if ch.isalnum() or ch in '_+-.' :
            value = [ch]
            while c.peek() and (c.peek().isalnum() or c.peek() in '_+-.'):
                value.append(c.get())
                if len(value) > c.limits.field_chars:
                    raise SQLStreamError('token character budget exceeded')
            return ('WORD', ''.join(value))
        return (ch, ch)

    def expect(self, value):
        token = self.next()
        if token[0] in {'STR', 'VERSION', 'EOF'} or token[1].upper() != value.upper():
            raise SQLStreamError('expected ' + value)
        return token

    def rest(self, cap=None):
        result = []
        start = self.chars.count
        while True:
            token = self.next()
            if token[0] == 'EOF':
                raise SQLStreamError('truncated statement')
            if cap is not None and self.chars.count - start > cap:
                raise SQLStreamError('DDL character budget exceeded')
            if token[0] == ';':
                return result
            result.append(token)


def _wrapper(tokens, table):
    """Validate inert dump scaffolding; never execute its contents."""
    words = [value.upper() for _, value in tokens]
    if not words:
        return
    if any('NO_BACKSLASH_ESCAPES' in w or 'ANSI_QUOTES' in w for w in words):
        raise SQLStreamError('unsupported SQL mode')
    head = words[0]
    if head == 'SET':
        if ';' in words or any(w in {'LOAD', 'INSERT', 'CREATE', 'DROP'} for w in words):
            raise SQLStreamError('unsupported SET scaffolding')
        return
    if head == 'UNLOCK' and words == ['UNLOCK', 'TABLES']:
        return
    expected = None
    if words[:4] == ['DROP', 'TABLE', 'IF', 'EXISTS'] and len(words) == 5:
        expected = tokens[4][1]
    elif words[:2] == ['LOCK', 'TABLES'] and len(words) == 4 and words[3] == 'WRITE':
        expected = tokens[2][1]
    elif words[:2] == ['ALTER', 'TABLE'] and len(words) == 5 and words[3] in {'ENABLE', 'DISABLE'} and words[4] == 'KEYS':
        expected = tokens[2][1]
    if expected != table:
        raise SQLStreamError('unsupported scaffolding or wrong table')


def _schema(tokens, table, limits):
    if not tokens or tokens[0][0] != '(':
        raise SQLStreamError('unsupported CREATE TABLE schema')
    columns, group, depth = [], [], 1
    for kind, word in tokens[1:]:
        if kind == '(':
            depth += 1
        elif kind == ')':
            depth -= 1
        if (kind == ',' and depth == 1) or depth == 0:
            if not group:
                raise SQLStreamError('empty DDL column')
            first = group[0]
            if first[0] == 'ID' or first[1].upper() not in {'PRIMARY', 'UNIQUE', 'KEY', 'CONSTRAINT', 'INDEX', 'FULLTEXT'}:
                if len(group) < 2 or group[1][1].lower() not in _TYPES:
                    raise SQLStreamError('unknown column type')
                columns.append(first[1])
                if len(columns) > limits.columns or len(set(columns)) != len(columns):
                    raise SQLStreamError('duplicate or excess columns')
            group = []
            if depth == 0:
                break
        else:
            group.append((kind, word))
    if depth != 0 or not columns:
        raise SQLStreamError('truncated or empty schema')
    return Schema(table, tuple(columns))


class RowIterator:
    """Lazy dictionaries, with explicit running/eof/max_rows/error status."""
    def __init__(self, stream, table, max_rows=None, *, limits=None):
        if table not in TABLES:
            raise SQLStreamError('table not allowlisted')
        if max_rows is not None and (type(max_rows) is not int or max_rows < 0):
            raise ValueError('max_rows must be a nonnegative integer or None')
        self.schema = None
        self.stop_reason = 'running'
        self.rows_yielded = 0
        self._generator = self._run(stream, table, max_rows, limits or Limits())

    @property
    def complete(self):
        return self.stop_reason == 'eof'

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return next(self._generator)
        except StopIteration:
            raise
        except Exception:
            self.stop_reason = 'error'
            raise

    def _run(self, stream, table, max_rows, limits):
        if max_rows == 0:
            self.stop_reason = 'max_rows'
            return
        t = _Tokens(stream, limits)
        while True:
            t.chars.start = t.chars.count
            kind, word = t.next()
            if kind == 'EOF':
                if self.schema is None:
                    raise SQLStreamError('missing CREATE TABLE schema')
                self.stop_reason = 'eof'
                return
            if kind == ';':
                continue
            if kind == 'VERSION':
                embedded = _Tokens([word + ';'], limits)
                _wrapper(embedded.rest(limits.ddl_chars), table)
                continue
            if kind != 'WORD':
                raise SQLStreamError('unsupported statement token')
            if word.upper() == 'CREATE':
                if self.schema is not None:
                    raise SQLStreamError('duplicate schema')
                t.expect('TABLE')
                name = t.next()
                if name[0] not in {'ID', 'WORD'} or name[1] != table:
                    raise SQLStreamError('wrong table or invalid identifier')
                self.schema = _schema(t.rest(limits.ddl_chars), table, limits)
            elif word.upper() == 'INSERT':
                if self.schema is None:
                    raise SQLStreamError('missing CREATE TABLE schema')
                t.expect('INTO')
                name = t.next()
                if name[0] not in {'ID', 'WORD'} or name[1] != table:
                    raise SQLStreamError('wrong table or invalid identifier')
                columns = self.schema.columns
                token = t.next()
                if token[0] == '(':
                    selected = []
                    while True:
                        name = t.next()
                        if name[0] not in {'ID', 'WORD'} or name[1] not in columns or name[1] in selected:
                            raise SQLStreamError('unknown or duplicate INSERT column')
                        selected.append(name[1])
                        if len(selected) > limits.columns:
                            raise SQLStreamError('too many columns')
                        separator = t.next()[0]
                        if separator == ')':
                            break
                        if separator != ',':
                            raise SQLStreamError('bad INSERT column list')
                    columns = tuple(selected)
                    token = t.next()
                if token != ('WORD', 'VALUES') and (token[0] != 'WORD' or token[1].upper() != 'VALUES'):
                    raise SQLStreamError('expected VALUES')
                while True:
                    t.chars.tuple_start = t.chars.count
                    t.expect('(')
                    values = []
                    while True:
                        kind, value = t.next()
                        if kind == 'WORD' and value.lower() == '_binary':
                            kind, value = t.next()
                            if kind != 'STR':
                                raise SQLStreamError('expected _binary string')
                        if kind == 'STR':
                            values.append(value)
                        elif kind == 'WORD' and value.upper() == 'NULL':
                            values.append(None)
                        elif kind == 'WORD' and _NUMBER.fullmatch(value):
                            if len(value) > 128:
                                raise SQLStreamError('numeric literal exceeds 128 characters')
                            try:
                                number = Decimal(value) if any(x in value.lower() for x in '.e') else int(value)
                            except (ValueError, InvalidOperation) as exc:
                                raise SQLStreamError('unsupported numeric literal') from exc
                            values.append(number)
                        else:
                            raise SQLStreamError('unsupported literal')
                        if len(values) > len(columns):
                            raise SQLStreamError('too many tuple fields')
                        delimiter = t.next()[0]
                        if delimiter == ')':
                            break
                        if delimiter != ',':
                            raise SQLStreamError('truncated tuple')
                    t.chars.tuple_start = None
                    if len(values) != len(columns):
                        raise SQLStreamError('column count mismatch')
                    self.rows_yielded += 1
                    if max_rows is not None and self.rows_yielded >= max_rows:
                        self.stop_reason = 'max_rows'
                    yield dict(zip(columns, values))
                    if self.stop_reason == 'max_rows':
                        return
                    delimiter = t.next()[0]
                    if delimiter == ';':
                        break
                    if delimiter != ',':
                        raise SQLStreamError('truncated INSERT')
            elif word.upper() in {'SET', 'DROP', 'LOCK', 'UNLOCK', 'ALTER'}:
                _wrapper([(kind, word)] + t.rest(limits.ddl_chars), table)
            else:
                raise SQLStreamError('unsupported statement: ' + word)


def iter_rows(stream, table, max_rows=None, *, limits=None):
    """Yield DDL-mapped dictionaries from iterable text or a text reader."""
    return RowIterator(stream, table, max_rows, limits=limits)
