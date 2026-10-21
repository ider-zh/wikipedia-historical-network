import unittest
from tools import pilot_preflight as p


class CoverageTests(unittest.TestCase):
    def test_declared_ranges_find_gaps_and_overlaps(self):
        names = ['zhwiki-20251001-pages-meta-history1.xml-p1p10.7z',
                 'zhwiki-20251001-pages-meta-history1.xml-p12p20.7z',
                 'zhwiki-20251001-pages-meta-history2.xml-p20p30.7z']
        result = p.range_coverage(names)
        self.assertEqual(result['gaps'], [[11, 11]])
        self.assertEqual(result['overlaps'], [[20, 20]])
        self.assertFalse(result['official_completeness_verified'])


class HeaderTests(unittest.TestCase):
    def test_xml_size_selection_ignores_packed_size(self):
        header = 'Path = a.xml\nSize = 100\nPacked Size = 999\nCRC = 1234ABCD\nEncrypted = -\n\n'
        self.assertEqual(p.archive_member(header), {'path': 'a.xml', 'size_bytes': 100, 'crc32': '1234ABCD', 'encrypted': False})
        with self.assertRaises(ValueError):
            p.archive_member(header + header)


if __name__ == '__main__':
    unittest.main()
