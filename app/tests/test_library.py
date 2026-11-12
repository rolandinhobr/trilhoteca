import hashlib
import io
import json
import sys
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from library import Library


def wav():
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(b'\x00\x00' * 4800)
    return stream.getvalue()


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'data/evidence').mkdir(parents=True)
        (self.root / 'data/evidence/proof.txt').write_text('Test fixture, not a real permission.')
        self.asset = {'id': 'fixture-audio', 'kind': 'music', 'title': 'Piano calmo', 'artist': 'Fixture',
                      'source_url': 'https://loyaltyfreakmusic.com/test/', 'source_name': 'Fixture',
                      'download_url': 'https://loyaltyfreakmusic.com/test.wav', 'extension': '.wav',
                      'vocals': False, 'tags': ['piano', 'calm'], 'description': 'Fixture for tests.',
                      'rights': {'status': 'verified', 'license': 'CC0 1.0', 'video': True, 'commercial': True,
                                 'advertising': True, 'evidence': ['data/evidence/proof.txt'], 'attribution_required': False}}
        (self.root / 'data/catalog.json').write_text(json.dumps({'assets': [self.asset]}))
        self.lib = Library(self.root)
        self.pid = self.lib.set_project('Fixture', 'proprio', False, False)['project']['id']

    def tearDown(self):
        self.temp.cleanup()

    def mutate(self, **changes):
        a = self.lib.asset(self.asset['id'])
        a.update(changes)
        with self.lib.db() as db:
            db.execute('UPDATE assets SET body=? WHERE id=?', (json.dumps(a), a['id']))

    def fetch(self, url, destination):
        destination.write_bytes(wav())

    def test_missing_context_returns_questions_and_no_candidates(self):
        answer = self.lib.search(query='piano')
        self.assertTrue(answer['needs_context'])
        self.assertEqual(len(answer['questions']), 3)
        self.assertEqual(answer['assets'], [])

    def test_incomplete_context_is_not_defaulted(self):
        p = self.lib.set_project('Incomplete', 'proprio', True, None)
        self.assertEqual(p['questions'][0]['field'], 'sponsored')
        self.assertIsNone(p['project']['sponsored'])

    def test_string_boolean_is_rejected(self):
        with self.assertRaises(ValueError):
            self.lib.set_project('Unsafe', 'proprio', 'false', False)

    def test_removed_source_cannot_be_selected_after_refresh(self):
        with patch.object(self.lib, '_fetch', side_effect=self.fetch):
            preview = self.lib.preview(self.asset['id'], self.pid)
        (self.root / 'data/catalog.json').write_text(json.dumps({'assets': []}))
        refreshed = Library(self.root)
        self.assertEqual(refreshed.search(self.pid)['total'], 0)
        with self.assertRaises(ValueError):
            refreshed.deliver([self.asset['id']], self.pid)
        self.assertTrue(Path(preview['path']).exists())

    def test_archived_test_project_is_not_offered_as_current_project(self):
        p = self.lib.project(self.pid)
        p['archived'] = True
        with self.lib.db() as db:
            db.execute('UPDATE projects SET body=? WHERE id=?', (json.dumps(p), self.pid))
        self.assertEqual(self.lib.projects(), [])
        self.assertEqual(self.lib.project(self.pid)['name'], 'Fixture')

    def test_own_content_monetized_and_sponsored_are_commercial(self):
        a = self.lib.asset(self.asset['id'])
        a['rights']['commercial'] = False
        for usage, monetize, sponsor, expected in [('proprio', False, False, True), ('proprio', True, False, False),
                                                   ('proprio', False, True, False), ('publicidade', False, False, False)]:
            p = {'usage': usage, 'monetized': monetize, 'sponsored': sponsor}
            self.assertEqual(self.lib.eligible(a, p)[0], expected)

    def test_advertising_restriction_does_not_block_eligible_own_content(self):
        a = self.lib.asset(self.asset['id'])
        a['rights']['advertising'] = False
        self.assertFalse(self.lib.eligible(a, {'usage': 'publicidade', 'monetized': False, 'sponsored': False})[0])
        self.assertTrue(self.lib.eligible(a, self.lib.project(self.pid))[0])

    def test_nd_unknown_and_missing_evidence_do_not_pass(self):
        for key, value in [('video', False), ('status', 'unknown'), ('share_alike', True), ('evidence', ['data/evidence/not-found.txt'])]:
            a = self.lib.asset(self.asset['id'])
            a['rights'][key] = value
            self.assertFalse(self.lib.eligible(a, self.lib.project(self.pid))[0])

    def test_no_voice_excludes_unknown_vocals(self):
        self.assertEqual(self.lib.search(self.pid, 'piano sem voz')['total'], 1)
        self.mutate(vocals=None)
        self.assertEqual(self.lib.search(self.pid, 'piano sem voz')['total'], 0)

    def test_credit_filter_and_favorite_survive_restart(self):
        a = self.lib.asset(self.asset['id'])
        a['rights']['attribution_required'] = True
        self.mutate(rights=a['rights'])
        self.assertEqual(self.lib.search(self.pid, credit='no_credit')['total'], 0)
        self.lib.feedback(self.asset['id'], 'favorite')
        self.assertEqual(Library(self.root).search(self.pid, favorites=True)['total'], 1)
        self.lib.feedback(self.asset['id'], 'dislike')
        self.assertEqual(self.lib.search(self.pid)['total'], 0)
        self.lib.feedback(self.asset['id'], 'clear')
        self.assertEqual(self.lib.search(self.pid)['total'], 1)

    def test_delivery_preserves_existing_assets_and_includes_proof(self):
        target = self.root / 'editor-assets'
        target.mkdir()
        sentinel = target / 'existing.wav'
        sentinel.write_bytes(b'original project asset')
        with patch.object(self.lib, '_fetch', side_effect=self.fetch) as download:
            first = self.lib.deliver([self.asset['id']], self.pid, str(target))
            second = self.lib.deliver([self.asset['id']], self.pid, str(target))
            self.assertEqual(download.call_count, 1)
        self.assertNotEqual(first['delivery_path'], second['delivery_path'])
        self.assertEqual(sentinel.read_bytes(), b'original project asset')
        d = Path(first['delivery_path'])
        manifest = json.loads((d / 'MANIFESTO.json').read_text())
        self.assertEqual(hashlib.sha256(Path(first['files'][0]).read_bytes()).hexdigest(), manifest['assets'][0]['sha256'])
        self.assertTrue((d / 'CREDITOS.txt').exists())
        self.assertTrue((d / 'licencas/proof.txt').exists())
        self.assertEqual(self.lib.details(self.asset['id'], self.pid)['use_count'], 1)

    def test_corrupt_cache_is_reacquired(self):
        with patch.object(self.lib, '_fetch', side_effect=self.fetch) as download:
            preview = self.lib.preview(self.asset['id'], self.pid)
            Path(preview['path']).write_bytes(b'corrupt')
            second = self.lib.preview(self.asset['id'], self.pid)
            self.assertEqual(download.call_count, 2)
            self.assertEqual(Path(second['path']).read_bytes(), wav())

    def test_failed_download_does_not_publish_incomplete_delivery(self):
        target = self.root / 'assets'
        def fail(url, destination):
            destination.write_bytes(b'partial')
            raise OSError('simulated source failure')
        with patch.object(self.lib, '_fetch', side_effect=fail), self.assertRaises(OSError):
            self.lib.deliver([self.asset['id']], self.pid, str(target))
        self.assertEqual(list(target.iterdir()), [])

    def test_html_disguised_as_audio_is_rejected(self):
        with patch.object(self.lib, '_fetch', side_effect=lambda url, dest: dest.write_bytes(b'<html>not music</html>')):
            with self.assertRaises(ValueError):
                self.lib.preview(self.asset['id'], self.pid)
        self.assertEqual(self.lib.stats()['downloads'], 0)

    def test_zip_download_extracts_only_requested_member(self):
        pack = io.BytesIO()
        with zipfile.ZipFile(pack, 'w') as z:
            z.writestr('audio/selected.wav', wav())
            z.writestr('audio/other.wav', b'unselected')
        self.mutate(archive_member='audio/selected.wav', download_url='https://loyaltyfreakmusic.com/pack.zip')
        with patch.object(self.lib, '_fetch', side_effect=lambda url, dest: dest.write_bytes(pack.getvalue())):
            p = self.lib.preview(self.asset['id'], self.pid)
        self.assertEqual(Path(p['path']).read_bytes(), wav())
        self.assertFalse((self.root / 'data/cache/audio/other.wav').exists())

    def test_zip_path_traversal_is_rejected(self):
        pack = io.BytesIO()
        with zipfile.ZipFile(pack, 'w') as z:
            z.writestr('../escape.wav', wav())
        self.mutate(archive_member='../escape.wav', download_url='https://loyaltyfreakmusic.com/pack.zip')
        with patch.object(self.lib, '_fetch', side_effect=lambda url, dest: dest.write_bytes(pack.getvalue())):
            with self.assertRaises(ValueError):
                self.lib.preview(self.asset['id'], self.pid)

    def test_unregistered_download_origin_is_rejected_without_network(self):
        for url in ['http://127.0.0.1/file', 'https://example.com/a.wav', 'https://kenney.nl:8443/a.wav']:
            with self.assertRaises(ValueError):
                self.lib._fetch(url, self.root / 'unused')


if __name__ == '__main__':
    unittest.main()
