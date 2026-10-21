import shutil
import tempfile
import unittest

from calibre.ebooks.metadata.book.base import Metadata
from calibre.library import db as open_db
from calibre.utils.date import parse_only_date

from calibre_plugins.ai_metadata.library import accepted_values, apply, current_values, diff, review_pair


class LibraryTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.legacy = open_db(self.tmp)
        self.db = self.legacy.new_api
        mi = Metadata('The Left Hand of Darkness', ['Ursula K. Le Guin'])
        mi.tags = ['Science Fiction', 'Classics']
        mi.series, mi.series_index = 'Hainish Cycle', 4
        mi.publisher = 'Ace Books'
        mi.languages = ['eng']
        mi.set_identifiers({'isbn': '9780441478125', 'goodreads': '18423'})
        mi.pubdate = parse_only_date('1969-03-01')
        self.book = self.db.create_book_entry(mi)
        other = Metadata('The Dispossessed', ['Ursula K. Le Guin'])
        other.tags = ['Science Fiction']
        other.publisher = 'Harper & Row'
        self.other = self.db.create_book_entry(other)

    def tearDown(self):
        self.legacy.close()
        shutil.rmtree(self.tmp)

    def changed(self, changes, book=None):
        return {field: new for field, _old, new in diff(self.db, book or self.book, changes)}

    # Proposals

    def test_case_only_tag_proposal_is_not_a_change(self):
        self.assertEqual(self.changed({'tags': ['classics', 'science fiction']}), {})

    def test_proposed_tags_reuse_existing_spelling(self):
        self.assertEqual(self.changed({'tags': ['science fiction', 'Gender']}), {'tags': ['Science Fiction', 'Gender']})

    def test_series_and_publisher_reuse_existing_spelling(self):
        self.assertEqual(self.changed({'series': 'hainish cycle', 'publisher': 'harper & row'}), {'publisher': 'Harper & Row'})

    def test_invalid_proposals_are_ignored(self):
        for changes in ({'series_index': 'nan'}, {'series_index': -1}, {'series_index': 'two'}, {'pubdate': 'someday'},
                        {'title': ''}, {'authors': []}, {'identifiers': 'isbn:123'}):
            with self.subTest(changes=changes):
                self.assertEqual(self.changed(changes), {})

    def test_identifiers_are_merged_and_empty_values_remove(self):
        self.assertEqual(self.changed({'identifiers': {'ISBN': '9780441007318', 'goodreads': ''}}),
                         {'identifiers': {'isbn': '9780441007318'}})

    def test_language_names_are_canonicalized(self):
        self.assertEqual(self.changed({'languages': ['fr']}), {'languages': ['fra']})

    # Writes

    def test_case_variants_do_not_rename_items_library_wide(self):
        apply(self.db, self.book, {'tags': ['science fiction'], 'publisher': 'harper & row'})
        self.assertIn('Science Fiction', self.db.all_field_names('tags'))
        self.assertNotIn('science fiction', self.db.all_field_names('tags'))
        self.assertEqual(self.db.field_for('publisher', self.other), 'Harper & Row')

    def test_author_case_fix_applies_to_every_book_of_that_author(self):
        apply(self.db, self.book, {'authors': ['Ursula K. le Guin']})
        self.assertEqual(self.db.field_for('authors', self.other), ('Ursula K. le Guin',))

    def test_explicit_sorts_survive_title_and_author_changes(self):
        apply(self.db, self.book, {
            'title': 'La Main gauche de la nuit', 'title_sort': 'Main gauche de la nuit, La',
            'authors': ['Ursula Le Guin'], 'author_sort': 'Le Guin, Ursula',
        })
        cur = current_values(self.db, self.book)
        self.assertEqual((cur['title_sort'], cur['author_sort']), ('Main gauche de la nuit, La', 'Le Guin, Ursula'))

    def test_series_and_pubdate_can_be_cleared(self):
        apply(self.db, self.book, {'series': '', 'pubdate': ''})
        cur = current_values(self.db, self.book)
        self.assertEqual((cur['series'], cur['pubdate']), ('', ''))

    def test_pubdate_keeps_its_day_at_month_and_year_boundaries(self):
        for day in ('1971-01-01', '1971-03-31'):
            with self.subTest(day=day):
                rows = diff(self.db, self.book, {'pubdate': day})
                self.assertEqual(review_pair(self.db, self.book, rows)[1].pubdate.astimezone().date().isoformat(), day)
                apply(self.db, self.book, {'pubdate': day})
                self.assertEqual(current_values(self.db, self.book)['pubdate'], day)

    # Review round trip

    def test_review_round_trip_writes_exactly_the_proposed_changes(self):
        rows = diff(self.db, self.book, {'tags': ['Science Fiction', 'Gender'], 'title_sort': 'Left Hand of Darkness, The',
                                         'pubdate': '1969-03-15', 'series': ''})
        old, new = review_pair(self.db, self.book, rows)
        self.assertEqual(accepted_values(self.db, self.book, old), {})
        values = accepted_values(self.db, self.book, new)
        self.assertEqual(values, {field: value for field, _old, value in rows})
        apply(self.db, self.book, values)
        self.assertEqual(diff(self.db, self.book, {field: value for field, _old, value in rows}), [])
