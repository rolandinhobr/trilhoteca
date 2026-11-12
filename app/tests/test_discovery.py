import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from bs4 import BeautifulSoup
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_library as fixtures
from discovery import DiscoveryJobs, merge_assets
from discover import Runner, index_urls, oga_records, validate_public_url, should_retry


class DiscoveryTests(fixtures.LibraryTests):
    # Base fixture shared without re-running unrelated tests in this class.
    def setUp(self):
        super().setUp()
        self.jobs = DiscoveryJobs(self.lib)

    def test_failed_page_retries_after_cooldown_but_imported_page_does_not(self):
        from datetime import datetime, timezone, timedelta
        self.assertTrue(should_retry(None))
        self.assertFalse(should_retry({'status': 'failed', 'checked': datetime.now(timezone.utc).isoformat()}))
        old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        self.assertTrue(should_retry({'status': 'failed', 'checked': old}))
        self.assertFalse(should_retry({'status': 'imported', 'checked': old}))

    def test_duplicate_recording_is_not_counted_twice(self):
        same = dict(self.asset, id='another-index-id')
        self.assertEqual(merge_assets(self.lib, [self.asset, same]), 0)
        new = dict(self.asset, id='new', download_url='https://loyaltyfreakmusic.com/new.wav')
        self.assertEqual(merge_assets(self.lib, [new]), 1)
        self.assertEqual(merge_assets(self.lib, [new]), 0)
        self.assertEqual(self.lib.search(self.pid)['total'], 2)
        self.assertEqual(self.lib.project(self.pid)['name'], 'Fixture')

    def test_second_search_reuses_active_job_and_does_not_launch_worker(self):
        with patch('discovery.subprocess.Popen') as launch:
            launch.return_value.pid = os.getpid()
            first = self.jobs.start('tracks')
            second = self.jobs.start('sources')
        self.assertTrue(first['started']);self.assertFalse(second['started'])
        self.assertEqual(first['job']['id'], second['job']['id'])
        self.assertEqual(launch.call_count, 1)

    def test_missing_worker_is_reported_as_interrupted_without_losing_assets(self):
        with patch('discovery.subprocess.Popen') as launch:
            launch.return_value.pid = os.getpid();job = self.jobs.start()['job']
        with patch('discovery.os.kill', side_effect=ProcessLookupError):
            self.assertEqual(self.jobs.status(job['id'])['status'], 'interrupted')
        self.assertEqual(self.lib.search(self.pid)['total'], 1)

    def test_failed_launch_does_not_leave_active_lock(self):
        with patch('discovery.subprocess.Popen', side_effect=OSError('fixture failure')):
            with self.assertRaises(OSError):self.jobs.start()
        self.assertEqual(self.jobs.status()['status'], 'failed')

    def test_license_link_in_footer_does_not_authorize_music(self):
        soup = BeautifulSoup('<div class="node"><h2>Example</h2><div class="field-name-author-submitter"><a class="username">Author</a></div></div><footer><a href="https://creativecommons.org/publicdomain/zero/1.0/">CC0</a></footer>', 'html.parser')
        with self.assertRaises(ValueError):oga_records(soup, b'fixture', 'https://opengameart.org/content/example', self.lib)

    def test_direct_music_index_prefers_mp3_without_downloading(self):
        markup = '''<div class="node"><h2>Example</h2><div class="field-name-author-submitter"><a class="username">Author</a></div><div class="field-name-field-art-licenses"><a href="https://creativecommons.org/publicdomain/zero/1.0/">CC0</a></div><div class="field-name-field-art-description">Instrumental track.</div><div class="field-name-field-art-files"><a href="https://opengameart.org/sites/default/files/example.ogg">OGG</a><a href="https://opengameart.org/sites/default/files/example.mp3">MP3</a></div></div>'''
        with patch.object(self.lib, '_fetch') as download:
            records = oga_records(BeautifulSoup(markup, 'html.parser'), markup.encode(), 'https://opengameart.org/content/example', self.lib)
        self.assertEqual(len(records), 1);self.assertEqual(records[0]['extension'], '.mp3')
        self.assertFalse(records[0]['vocals']);download.assert_not_called()
        self.assertTrue((self.root / records[0]['rights']['evidence'][0]).is_file())

    def test_discovery_cannot_read_loopback_and_reserved_pages(self):
        with patch('discover.socket.getaddrinfo', return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(ValueError):validate_public_url('https://private.example/')
        for url in ('http://example.com/', 'https://user:password@example.com/', 'https://example.com:9000/'):
            with self.assertRaises(ValueError):validate_public_url(url)

    def test_index_does_not_follow_navigation_or_external_links(self):
        s=BeautifulSoup('<article><h2><a href="https://www.scottbuckley.com.au/library/new/">New</a></h2><h2><a href="https://example.com/">No</a></h2></article><nav><a href="/library/about/">About</a></nav>','html.parser')
        self.assertEqual(index_urls(s, 'https://www.scottbuckley.com.au/library/', 'scott'), ['https://www.scottbuckley.com.au/library/new/'])

    def test_unreachable_index_preserves_catalog_and_retry_cursor(self):
        with patch('discovery.subprocess.Popen') as launch:
            launch.return_value.pid=os.getpid();job=self.jobs.start()['job']
        with patch('discover.html', side_effect=OSError('unreachable')):
            Runner(self.lib,self.jobs,job).run()
        self.assertEqual(self.jobs.status(job['id'])['status'],'failed')
        self.assertEqual(self.lib.search(self.pid)['total'],1)
        with self.lib.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM discovery_cursors').fetchone()[0],0)


# Inherited base tests run in LibraryTests; retain only the new cases here.
for name in list(vars(fixtures.LibraryTests)):
    if name.startswith('test_') and name not in vars(DiscoveryTests):
        setattr(DiscoveryTests, name, None)

if __name__ == '__main__':unittest.main()
