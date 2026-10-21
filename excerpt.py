import re
import subprocess

# Title and copyright pages open a book; colophons (dépôt légal, printer) often close it.
HEAD, TAIL = 4000, 1500
# Preferred first.
FORMATS = ('EPUB', 'KEPUB', 'AZW3', 'PDF')


def excerpt_source(db, book_id):
    '''Path of the book file to read the excerpt from, or None.'''
    formats = set(db.formats(book_id))
    for fmt in FORMATS:
        if fmt in formats:
            return db.format_abspath(book_id, fmt)


def book_excerpt(path):
    '''{"start": text, "end": text} from the book file; {} when it has no readable text (DRM, scans, errors).'''
    try:
        if path.lower().endswith('.pdf'):
            return _cut(*_pdf_pages(path))
        from calibre.ptempfile import TemporaryDirectory
        with TemporaryDirectory('_ai_metadata') as tdir:
            return _cut(*_spine_texts(path, tdir))
    except Exception:
        return {}


def _cut(count, text_at):
    '''Text of the first units up to HEAD chars and of the last ones up to TAIL chars, without overlap.'''
    head, i = '', 0
    while i < count and len(head) < HEAD:
        head += '\n\n' + text_at(i)
        i += 1
    tail, j = '', count - 1
    while j >= i and len(tail) < TAIL:
        tail = text_at(j) + '\n\n' + tail
        j -= 1
    ans = {'start': _clean(head)[:HEAD], 'end': _clean(tail)[-TAIL:]}
    return {k: v for k, v in ans.items() if v}


def _clean(text):
    return re.sub(r'\n\s*\n\s*', '\n\n', text).strip()


def _spine_texts(path, tdir):
    from html2text import HTML2Text
    from lxml import etree

    from calibre.ebooks.oeb.base import XPath
    from calibre.ebooks.oeb.polish.container import get_container
    from calibre.utils.logging import Log

    container = get_container(path, log=Log(level=Log.ERROR), tdir=tdir, tweak_mode=True)
    names = [name for name, _linear in container.spine_names]
    body = XPath('//h:body')
    h2t = HTML2Text()
    h2t.body_width = 0
    h2t.ignore_images = h2t.ignore_links = h2t.ignore_emphasis = True

    def text_at(i):
        return ''.join(h2t.handle(etree.tostring(b, encoding='unicode')) for b in body(container.parsed(names[i])))
    return len(names), text_at


def _pdf_pages(path):
    from calibre.ebooks.metadata.pdf import check_output, get_tools
    from calibre.ebooks.pdf.pdftohtml import PDFTOTEXT

    info = check_output(get_tools()[0], path).decode('utf-8', 'replace')
    count = int(re.search(r'^Pages:\s*(\d+)', info, re.M).group(1))

    def text_at(i):
        page = str(i + 1)
        return check_output(PDFTOTEXT, '-q', '-enc', 'UTF-8', '-f', page, '-l', page, path, '-').decode('utf-8', 'replace')
    return count, text_at
