"""Storage regressions with an in-memory filesystem; no synthetic production records."""
import copy
import io
import json
import unittest
from unittest.mock import MagicMock, patch
import review_scorecard as ledger

FIELDS = ['review_id', 'recorded_at_ist', 'record_type', 'strategy_id', 'schema_version',
          'parent_review_id', 'supersedes_review_id', 'analytics_json']


def event(rid='r1', **kw):
    row = dict.fromkeys(FIELDS, '')
    row.update(review_id=rid, recorded_at_ist='2026-09-19T10:00:00+05:30',
               record_type='REVIEW', strategy_id='synthetic', schema_version='2', analytics_json={})
    row.update(kw)
    return row


def document(rows=None):
    return {'format': ledger.STORE_FORMAT, 'format_version': ledger.STORE_VERSION,
            'event_fields': FIELDS, 'events': rows or []}


class MemoryFile(io.StringIO):
    name = 'memory-only-atomic-file'

    def fileno(self):
        return 99

    def close(self):
        pass


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.saved = json.dumps(document())
        self.root, self.path = MagicMock(), MagicMock()
        self.root.is_dir.return_value = True
        self.path.is_file.return_value = True
        self.path.read_text.side_effect = lambda **kw: self.saved
        self.root.__truediv__.return_value.open.side_effect = lambda *a, **k: MemoryFile()
        self.temp = MemoryFile()
        self.patches = [patch.object(ledger, 'ROOT', self.root), patch.object(ledger, 'LEDGER', self.path),
                        patch.object(ledger.fcntl, 'flock'), patch.object(ledger.os, 'fsync'),
                        patch.object(ledger.os, 'unlink'),
                        patch.object(ledger.tempfile, 'NamedTemporaryFile', return_value=self.temp),
                        patch.object(ledger.os, 'replace', side_effect=self.replace),
                        patch('simple_ledger.refresh', return_value={'status':'UNCHANGED'})]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def replace(self, source, destination):
        self.saved = self.temp.getvalue()

    def test_native_analytics_and_legacy_callers(self):
        a = {'nested': {'values': [1, None, '₹', 'a\nb']}}
        self.assertEqual(ledger.data({'analytics_json': a}), a)
        self.assertEqual(ledger.data({'analytics_json': json.dumps(a)}), a)
        self.assertEqual(ledger.data({'analytics_json': ''}), {})

    def test_append_roundtrip_preserves_prior_records(self):
        original = event(analytics_json={'a': {'nested': [1, 2]}})
        self.saved = json.dumps(document([original]))
        new = event('r2', analytics_json=json.dumps({'details': 'comma, quote" and\nnewline'}))
        result = ledger.append_event(new)
        stored = ledger.read_rows()
        self.assertEqual(result['rows'], 2)
        self.assertEqual(stored[0], original)
        self.assertEqual(stored[1]['analytics_json'], {'details': 'comma, quote" and\nnewline'})
        self.assertIsInstance(stored[1]['analytics_json'], dict)

    def test_duplicate_and_unknown_fields_do_not_write(self):
        self.saved = json.dumps(document([event()]))
        before = self.saved
        for row in [event(), event('r2', unexpected='typo')]:
            with self.assertRaises(ValueError):
                ledger.append_event(row)
            self.assertEqual(self.saved, before)

    def test_correction_history_and_empty_parent_preserved(self):
        self.saved = json.dumps(document([event()]))
        correction = event('r2', supersedes_review_id='r1')
        correction.pop('parent_review_id')
        ledger.append_event(correction)
        self.assertEqual(len(ledger.read_rows()), 2)
        self.assertEqual([r['review_id'] for r in ledger.active(ledger.read_rows())], ['r2'])

    def test_partial_commit_reports_projection_failure(self):
        with patch('simple_ledger.refresh', side_effect=OSError('Storage projection unavailable')):
            with self.assertRaisesRegex(OSError, 'REVIEW_COMMITTED_BUT_SIMPLE_LEDGER_FAILED'):
                ledger.append_event(event())
        self.assertEqual([r['review_id'] for r in ledger.read_rows()], ['r1'])

    def test_atomic_replace_failure_preserves_source(self):
        before = self.saved
        with patch.object(ledger.os, 'replace', side_effect=OSError('unavailable')):
            with self.assertRaises(OSError):
                ledger.append_event(event())
        self.assertEqual(self.saved, before)

    def test_readback_mismatch_detected(self):
        with patch.object(ledger.os, 'replace', return_value=None):
            with self.assertRaisesRegex(OSError, 'STORAGE_READBACK_FAILED'):
                ledger.append_event(event())

    def test_missing_json_never_falls_back_to_csv(self):
        self.path.is_file.return_value = False
        with self.assertRaisesRegex(OSError, 'canonical JSON ledger missing'):
            ledger.append_event(event())
        self.path.read_text.side_effect = FileNotFoundError('JSON absent')
        with self.assertRaises(FileNotFoundError):
            ledger.read_rows()

    def test_storage_schema_corruption_rejected(self):
        variants = []
        d = document(); d['format_version'] = 99; variants.append(d)
        d = document(); d['event_fields'] = [*FIELDS, FIELDS[0]]; variants.append(d)
        d = document([event(), event()]); variants.append(d)
        d = document([event()]); d['events'][0].pop('strategy_id'); variants.append(d)
        d = document([event(analytics_json='{}')]); variants.append(d)
        for d in variants:
            with self.assertRaises(ValueError):
                ledger.validate_document(d)

    def test_duplicate_keys_and_nonfinite_rejected(self):
        for text in ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}']:
            with self.assertRaises(ValueError):
                ledger.decode_json(text)
        with self.assertRaises(ValueError):
            ledger.append_event(event(analytics_json={'bad':float('nan')}))


if __name__ == '__main__':
    unittest.main()
