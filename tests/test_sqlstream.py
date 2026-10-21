"""Service-free dump parser contract tests (stdlib only)."""
import importlib
import importlib.util
from decimal import Decimal
import io
import unittest


class SQLStreamTests(unittest.TestCase):
    def test_ddl_names_and_streamed_rows(self):
        self.assertIsNotNone(importlib.util.find_spec('whn.sqlstream'), 'SQL streaming parser missing')
        sql = importlib.import_module('whn.sqlstream')
        text = "CREATE TABLE `page` (`page_id` int unsigned NOT NULL, `page_title` varbinary(255) NOT NULL, PRIMARY KEY (`page_id`)); INSERT INTO `page` VALUES (1,'中文,分類'),(2,'second');"
        rows = sql.iter_rows(iter(text), 'page')
        self.assertEqual(list(rows), [{'page_id': 1, 'page_title': '中文,分類'}, {'page_id': 2, 'page_title': 'second'}])
        self.assertEqual(rows.schema.columns, ('page_id', 'page_title'))
        self.assertEqual(rows.stop_reason, 'eof')


    def test_literals_explicit_columns_and_dump_wrappers(self):
        from whn.sqlstream import iter_rows
        text = r"""-- official-style header
/*!40101 SET NAMES binary */;
DROP TABLE IF EXISTS `categorylinks`;
CREATE TABLE `categorylinks` (
 `cl_from` int unsigned NOT NULL,
 `cl_target_id` bigint unsigned NOT NULL,
 `label` varbinary(255) NOT NULL,
 `score` float DEFAULT NULL,
 PRIMARY KEY (`cl_from`,`cl_target_id`)
) ENGINE=InnoDB DEFAULT CHARSET=binary;
LOCK TABLES `categorylinks` WRITE;
/*!40000 ALTER TABLE `categorylinks` DISABLE KEYS */;
INSERT INTO `categorylinks` (`label`,`score`,`cl_target_id`,`cl_from`) VALUES
(_binary'中文,\'\\;()\n\0',-1.25e+2,90,1),('it''s',NULL,91,2);
UNLOCK TABLES;
"""
        for chunks in (io.StringIO(text), iter(text)):
            rows = iter_rows(chunks, 'categorylinks')
            self.assertEqual(list(rows), [
                {'label': "中文,'\\;()\n\0", 'score': Decimal('-125'), 'cl_target_id': 90, 'cl_from': 1},
                {'label': "it's", 'score': None, 'cl_target_id': 91, 'cl_from': 2},
            ])


    def test_rejections(self):
        from whn.sqlstream import iter_rows, SQLStreamError
        ddl = 'CREATE TABLE `page` (`id` int, `title` varbinary(255));'
        bad = [
            '', 'INSERT INTO `page` VALUES (1);',
            ddl + "INSERT INTO `category` VALUES (1,'x');",
            ddl + "INSERT INTO `page` VALUES (1,'x'",
            ddl + "INSERT INTO `page` VALUES (1,'x'); LOAD DATA INFILE 'x' INTO TABLE page;",
            ddl + "INSERT INTO `page` VALUES (1);",
            ddl + "INSERT INTO `page` (`missing`) VALUES (1);",
            ddl + "INSERT INTO `page` VALUES (1,CONCAT('x','y'));",
            'CREATE TABLE `page` (`id` mystery);',
            'CREATE TABLE `page` (`id` int, `id` int);',
            ddl + "INSERT INTO `page` VALUES (1,'bad\\q');",
            ddl + "INSERT INTO `page` VALUES (1,'x'),;",
            'CREATE TABLE `category` (`id` int);',
            ddl + "INSERT INTO `page` VALUES (1,0xFF);",
            '/*!99999 LOAD DATA INFILE x */;' + ddl,
            "SET SQL_MODE='NO_BACKSLASH_ESCAPES';" + ddl,
        ]
        for text in bad:
            with self.subTest(text=text), self.assertRaises(SQLStreamError):
                list(iter_rows(io.StringIO(text), 'page'))
        with self.assertRaises(SQLStreamError):
            iter_rows([], 'revision')

    def test_budgets_and_prefix_status(self):
        from whn.sqlstream import iter_rows, SQLStreamError, Limits
        ddl = 'CREATE TABLE `page` (`id` int, `title` varbinary(255));'
        def parts():
            yield ddl + "INSERT INTO `page` VALUES (1,'x'),"
            raise AssertionError('prefix consumed more input')
        rows = iter_rows(parts(), 'page', max_rows=1)
        self.assertEqual(list(rows), [{'id': 1, 'title': 'x'}])
        self.assertEqual(rows.stop_reason, 'max_rows')
        self.assertFalse(rows.complete)
        for limit in (Limits(field_chars=4), Limits(tuple_chars=8), Limits(statement_chars=40)):
            with self.subTest(limit=limit), self.assertRaises(SQLStreamError):
                list(iter_rows(io.StringIO(ddl + "INSERT INTO `page` VALUES (1,'abcdefghijklmnop');"), 'page', limits=limit))
        zero = iter_rows(parts(), 'page', max_rows=0)
        self.assertEqual(list(zero), [])
        self.assertEqual(zero.stop_reason, 'max_rows')
        with self.assertRaises(ValueError):
            iter_rows([], 'page', max_rows=-1)


    def test_chunk_numeric_and_identifier_guards(self):
        from whn.sqlstream import iter_rows, SQLStreamError, Limits
        ddl = 'CREATE TABLE `page` (`id` int);'
        for text in [ddl + "INSERT INTO 'page' VALUES (1);", "CREATE TABLE 'page' (`id` int);", ddl + 'INSERT INTO page VALUES (' + '9' * 5000 + ');']:
            with self.subTest(text=text[:80]), self.assertRaises(SQLStreamError):
                list(iter_rows(io.StringIO(text), 'page'))
        with self.assertRaises(SQLStreamError):
            list(iter_rows([ddl], 'page', limits=Limits(chunk_chars=8)))

    def test_many_tuples_without_statement_materialization(self):
        import tracemalloc
        from whn.sqlstream import iter_rows
        def chunks():
            yield 'CREATE TABLE `page` (`id` int); INSERT INTO page VALUES '
            for i in range(20000):
                yield ('(%d)' % i) + (';' if i == 19999 else ',')
        tracemalloc.start()
        try:
            rows = iter_rows(chunks(), 'page')
            count = sum(1 for _ in rows)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(count, 20000)
        self.assertTrue(rows.complete)
        self.assertLess(peak, 1024 * 1024)


if __name__ == '__main__':
    unittest.main()
