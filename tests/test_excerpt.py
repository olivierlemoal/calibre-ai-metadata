import os
import shutil
import tempfile
import unittest
import zipfile

from calibre_plugins.ai_metadata.excerpt import HEAD, TAIL, book_excerpt

CONTAINER = '''<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'''

OPF = '''<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>T</dc:title><dc:identifier id="id">x</dc:identifier></metadata>
<manifest>{items}</manifest><spine>{refs}</spine></package>'''

XHTML = '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>ignored head</title></head><body>{}</body></html>'


class EpubExcerptTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def epub(self, *bodies):
        path = os.path.join(self.tmp, 'book.epub')
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('mimetype', 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
            z.writestr('META-INF/container.xml', CONTAINER)
            z.writestr('content.opf', OPF.format(
                items=''.join(f'<item id="f{i}" href="f{i}.xhtml" media-type="application/xhtml+xml"/>' for i in range(len(bodies))),
                refs=''.join(f'<itemref idref="f{i}"/>' for i in range(len(bodies)))))
            for i, body in enumerate(bodies):
                z.writestr(f'f{i}.xhtml', XHTML.format(body))
        return path

    def test_start_and_end_of_a_long_book(self):
        chapter = '<p>' + 'Lorem ipsum dolor sit amet. ' * 200 + '</p>'
        excerpt = book_excerpt(self.epub(
            '<img src="cover.jpg"/>', '<h1>La Main gauche de la nuit</h1>', '<p>ISBN 978-2-221-12345-6</p>',
            *[chapter] * 10, '<p>Dépôt légal : mars 1971</p>'))
        self.assertIn('La Main gauche de la nuit', excerpt['start'])
        self.assertIn('ISBN 978-2-221-12345-6', excerpt['start'])
        self.assertTrue(excerpt['end'].endswith('Dépôt légal : mars 1971'))
        self.assertLessEqual(len(excerpt['start']), HEAD)
        self.assertLessEqual(len(excerpt['end']), TAIL)
        self.assertNotIn('ignored head', excerpt['start'])

    def test_short_book_is_not_sent_twice(self):
        self.assertEqual(book_excerpt(self.epub('<p>Title page</p>', '<p>Colophon</p>')), {'start': 'Title page\n\nColophon'})

    def test_unreadable_file_gives_no_excerpt(self):
        path = os.path.join(self.tmp, 'broken.epub')
        with open(path, 'wb') as f:
            f.write(b'not a zip')
        self.assertEqual(book_excerpt(path), {})
        self.assertEqual(book_excerpt(self.epub('<img src="scan.jpg"/>')), {})
