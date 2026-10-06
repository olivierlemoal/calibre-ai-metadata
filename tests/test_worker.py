import json
import threading
import unittest

from calibre.ai import ChatResponse

from calibre_plugins.ai_metadata.worker import parse_answer, run_calibre_ai


def answer(*ids):
    return '```json\n' + json.dumps({'books': [{'id': i, 'changes': {}} for i in ids]}) + '\n```'


class FakeProvider:
    name = 'Fake'

    def __init__(self, replies):
        self.replies = iter(replies)

    def text_chat(self, messages, use_model=''):
        reply = next(self.replies)
        if isinstance(reply, Exception):
            yield ChatResponse(exception=reply, error_details='details')
        else:
            # Streamed in two chunks, like real providers.
            yield ChatResponse(content=reply[:5])
            yield ChatResponse(content=reply[5:])


class ParseAnswerTest(unittest.TestCase):

    def test_fenced_block_surrounded_by_prose(self):
        self.assertEqual(parse_answer('Sure!\n' + answer(1) + '\nHope it helps')['books'][0]['id'], 1)

    def test_bare_json_inside_prose(self):
        self.assertEqual(parse_answer('Result: {"books": [{"id": 2}]} done')['books'], [{'id': 2}])

    def test_last_valid_answer_wins(self):
        self.assertEqual(parse_answer(answer(1) + '\nCorrected:\n' + answer(3))['books'][0]['id'], 3)

    def test_objects_without_books_list_are_rejected(self):
        for text in ('no json here', '{"books": "nope"}', '```json\n{"id": 1}\n```', '{"books": [1,'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_answer(text)


class RunCalibreAITest(unittest.TestCase):

    def test_failed_batch_keeps_the_others(self):
        provider = FakeProvider([answer(1, 2), 'garbage', RuntimeError('rate limited'), answer(7)])
        result = run_calibre_ai([([1, 2], 'p1'), ([3, 4], 'p2'), ([5, 6], 'p3'), ([7], 'p4')], provider)
        self.assertEqual([b['id'] for b in result['books']], [1, 2, 7])
        self.assertEqual([e['book_ids'] for e in result['errors']], [[3, 4], [5, 6]])
        self.assertIn('rate limited', result['errors'][1]['error'])

    def test_all_batches_failing_raises(self):
        with self.assertRaises(RuntimeError):
            run_calibre_ai([([1], 'p1'), ([2], 'p2')], FakeProvider(['garbage', RuntimeError('down')]))

    def test_abort_stops_instead_of_being_recorded_as_a_batch_error(self):
        abort = threading.Event()
        abort.set()
        with self.assertRaises(Exception) as cm:
            run_calibre_ai([([1], 'p1'), ([2], 'p2')], FakeProvider([answer(1), answer(2)]), abort=abort)
        self.assertEqual(type(cm.exception).__name__, 'Aborted')
