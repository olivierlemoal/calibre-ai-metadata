import math
import re

from calibre.ebooks.metadata import check_isbn
from calibre.utils.date import UNDEFINED_DATE, as_local_time, is_date_undefined, now, parse_date
from calibre.utils.html2text import html2text
from calibre.utils.localization import canonicalize_lang

from calibre_plugins.ai_metadata.worker import FIELDS

DB_FIELD = {'title_sort': 'sort'}
# Fields shown in calibre's compare dialog; 'sort' is mirrored onto Metadata objects as an ad hoc attribute.
REVIEW_FIELDS = ('title', 'sort', 'authors', 'author_sort', 'series', 'tags', 'publisher', 'pubdate', 'languages', 'identifiers')


def _iso_date(dt):
    # calibre displays dates in local time.
    return '' if dt is None or is_date_undefined(dt) else as_local_time(dt).date().isoformat()


def _local_day(value):
    '''Noon local time, so the day stays the same once displayed or stored as UTC.'''
    default = now().replace(day=15, hour=12, minute=0, second=0, microsecond=0)
    return parse_date(value, assume_utc=False, as_utc=False, default=default)


def current_values(db, book_id):
    def f(name):
        return db.field_for(DB_FIELD.get(name, name), book_id)
    pubdate = f('pubdate')
    return {
        'title': f('title'),
        'title_sort': f('title_sort') or '',
        'authors': list(f('authors')),
        'author_sort': f('author_sort') or '',
        'tags': list(f('tags')),
        'series': f('series') or '',
        'series_index': f('series_index'),
        'publisher': f('publisher') or '',
        'pubdate': _iso_date(pubdate),
        'languages': list(f('languages')),
        'identifiers': dict(f('identifiers')),
    }


def book_snapshot(db, book_id):
    ans = {'id': book_id}
    ans.update(current_values(db, book_id))
    comments = db.field_for('comments', book_id)
    if comments:
        ans['description'] = html2text(comments).strip()[:1500]
    return ans


def library_context(db):
    def counts(field):
        names = db.get_id_map(field)
        return {names[i]: c for i, c in db.get_usage_count_by_id(field).items() if i in names and c}
    return {
        'tags': counts('tags'),
        'series': counts('series'),
        'authors': sorted(set(db.get_id_map('authors').values())),
    }


def _str_list(value):
    if isinstance(value, str):
        value = value.split(',')
    return [s for s in (str(x).strip() for x in value or ()) if s]


def _existing_spelling(db, field):
    # calibre renames an item library-wide when it is set with a different case: reuse the existing spelling instead.
    names = {n.lower(): n for n in db.all_field_names(field)}
    return lambda v: names.get(v.lower(), v)


def normalize(db, field, value, current):
    '''Return the proposed value in the same shape as current_values(), or raise ValueError.'''
    if field == 'authors':
        return _str_list(value)
    if field == 'tags':
        return list(dict.fromkeys(map(_existing_spelling(db, 'tags'), _str_list(value))))
    if field == 'languages':
        return [lc for lc in map(canonicalize_lang, _str_list(value)) if lc]
    if field == 'series_index':
        value = float(value)
        if not math.isfinite(value) or value < 0:
            raise ValueError('invalid series_index')
        return value
    if field == 'pubdate':
        value = str(value or '').strip()[:10]
        if not value:
            return value
        if not re.fullmatch(r'\d{4}(-\d{2}){0,2}', value):
            raise ValueError('invalid pubdate')
        # A year or month only: keep the current day when it falls inside, else the first day.
        if current['pubdate'].startswith(value):
            return current['pubdate']
        value = (value + '-01-01')[:10]
        _local_day(value)
        return value
    if field == 'identifiers':
        if not isinstance(value, dict):
            raise ValueError('identifiers must be an object')
        merged = dict(current['identifiers'])
        for k, v in value.items():
            k, v = str(k).strip().lower(), str(v or '').strip()
            if k == 'isbn' and v:
                v = check_isbn(v)
                if not v:
                    continue
            if v:
                merged[k] = v
            else:
                merged.pop(k, None)
        return merged
    value = str(value or '').strip()
    if field in ('series', 'publisher') and value:
        value = _existing_spelling(db, field)(value)
    return value


def _same(field, a, b):
    if field == 'tags':
        return sorted(a) == sorted(b)
    return a == b


def diff(db, book_id, changes):
    '''[(field, current, proposed)] for proposed values that actually differ from the library.'''
    cur = current_values(db, book_id)
    ans = []
    for field in FIELDS:
        if field not in changes:
            continue
        try:
            new = normalize(db, field, changes[field], cur)
        except (TypeError, ValueError):
            continue
        if field in ('title', 'authors') and not new:
            continue
        if not _same(field, cur[field], new):
            ans.append((field, cur[field], new))
    return ans


def apply(db, book_id, values):
    # FIELDS order puts title before title_sort and authors before author_sort,
    # since calibre recomputes the sort fields when those change.
    for field in FIELDS:
        if field not in values:
            continue
        value = values[field]
        if field == 'pubdate':
            value = _local_day(value) if value else UNDEFINED_DATE
        # Authors keep calibre's default so capitalization fixes reach every book of that person.
        db.set_field(DB_FIELD.get(field, field), {book_id: value}, allow_case_change=field == 'authors')


def _set_on_mi(mi, field, value):
    if field == 'title_sort':
        mi.title_sort = value
        mi.set('sort', value)
    elif field == 'pubdate':
        mi.pubdate = _local_day(value) if value else UNDEFINED_DATE
    elif field == 'identifiers':
        mi.set_identifiers(value)
    else:
        mi.set(field, value)


def review_pair(db, book_id, rows):
    '''(current, proposed) Metadata for calibre's compare dialog.'''
    old = db.get_metadata(book_id)
    new = old.deepcopy_metadata()
    for mi in (old, new):
        mi.set('sort', old.title_sort)
    for field, _, value in rows:
        _set_on_mi(new, field, value)
    return old, new


def values_from_mi(mi):
    return {
        'title': mi.title,
        'title_sort': mi.get('sort') or mi.title_sort or '',
        'authors': list(mi.authors),
        'author_sort': mi.author_sort or '',
        'tags': list(mi.tags),
        'series': mi.series or '',
        'series_index': float(mi.series_index if mi.series_index is not None else 1.0),
        'publisher': mi.publisher or '',
        'pubdate': _iso_date(mi.pubdate),
        'languages': list(mi.languages),
        'identifiers': dict(mi.identifiers),
    }


def accepted_values(db, book_id, mi):
    '''{field: value} of the reviewed Metadata that differ from the library.'''
    cur = current_values(db, book_id)
    new = values_from_mi(mi)
    return {f: new[f] for f in FIELDS if not _same(f, cur[f], new[f])}


