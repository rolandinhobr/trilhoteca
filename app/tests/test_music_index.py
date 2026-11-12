import io
import re
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_library as fixtures
from music_index import RangeZip, audio_members, loyalty_records
from discovery import DiscoveryJobs


URL = 'https://loyaltyfreakmusic.com/album.zip'
PAGE = 'https://loyaltyfreakmusic.com/music/test/'
MARKUP = '''<article><h1>Album</h1><p>By: Artist</p><p>Genre: ambient, electronic</p><p>Licence: <a href="https://creativecommons.org/publicdomain/zero/1.0/">CC0</a></p><a href="https://loyaltyfreakmusic.com/album.zip">Download</a></article>'''


def pack():
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        z.writestr('Artist - Album - 01 First.mp3', b'X' * 120000)
        z.writestr('Artist - Album - 01 First.ogg', b'Y' * 120000)
        z.writestr('../unsafe.mp3', b'X')
        z.writestr('__MACOSX/._track.mp3', b'X')
    return b.getvalue()


def opener_for(data, requests):
    class Response(io.BytesIO):
        status = 206
        def geturl(self): return URL
    class Opener:
        def open(self, req, timeout):
            start, end = map(int, re.fullmatch(r'bytes=(\d+)-(\d+)', req.get_header('Range')).groups())
            requests.append((start, end))
            r = Response(data[start:end+1]);r.headers = {'Content-Range': f'bytes {start}-{end}/{len(data)}'}
            return r
    return Opener()


class MusicIndexTests(fixtures.LibraryTests):
    def test_album_index_reads_only_manifest_and_preserves_unknown_audio_fields(self):
        requests = [];data = pack()
        with patch('music_index.urllib.request.build_opener', return_value=opener_for(data, requests)), patch.object(self.lib, '_fetch') as download:
            records = loyalty_records(BeautifulSoup(MARKUP, 'html.parser'), MARKUP.encode(), PAGE, self.lib)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['title'], 'First')
        self.assertEqual(records[0]['archive_member'], 'Artist - Album - 01 First.mp3')
        self.assertIsNone(records[0]['duration']);self.assertIsNone(records[0]['vocals'])
        self.assertLess(sum(end-start+1 for start,end in requests), 2000)
        download.assert_not_called()
        self.assertTrue((self.root / records[0]['rights']['evidence'][0]).is_file())

    def test_footer_permission_does_not_license_album(self):
        markup = MARKUP.replace('<a href="https://creativecommons.org/publicdomain/zero/1.0/">CC0</a>', '') + '<footer><a href="https://creativecommons.org/publicdomain/zero/1.0/">CC0</a></footer>'
        with patch('music_index.RangeZip') as reader:
            with self.assertRaises(ValueError):loyalty_records(BeautifulSoup(markup, 'html.parser'), markup.encode(), PAGE, self.lib)
        reader.assert_not_called()

    def test_unicode_download_link_is_encoded_for_manifest_and_later_preview(self):
        markup = MARKUP.replace('album.zip', 'música · álbum.zip')
        data = pack()
        class LocalReader(io.BytesIO):
            transferred = 0
        with patch('music_index.RangeZip', return_value=LocalReader(data)) as reader:
            records = loyalty_records(BeautifulSoup(markup, 'html.parser'), markup.encode(), PAGE, self.lib)
        self.assertIn('m%C3%BAsica%20%C2%B7%20%C3%A1lbum.zip', records[0]['download_url'])
        self.assertEqual(reader.call_args.args[0], records[0]['download_url'])

    def test_restricted_license_and_cover_are_not_imported(self):
        for markup in (MARKUP.replace('publicdomain/zero/1.0', 'licenses/by-nc/4.0'), MARKUP.replace('ambient, electronic', 'cover and remix')):
            with patch('music_index.RangeZip') as reader:
                with self.assertRaises(ValueError):loyalty_records(BeautifulSoup(markup, 'html.parser'), markup.encode(), PAGE, self.lib)
            reader.assert_not_called()

    def test_range_server_must_honor_partial_reads(self):
        response = io.BytesIO(b'X');response.status = 200;response.geturl = lambda: URL
        response.headers = {}
        with patch('music_index.urllib.request.build_opener') as build:
            build.return_value.open.return_value = response
            with self.assertRaises(ValueError):RangeZip(URL)

    def test_range_response_size_and_length_are_validated(self):
        for content_range, data in [('bytes 1-1/10', b'X'), ('bytes 0-0/10', b'XX'), ('bytes 0-0/262144001', b'X')]:
            response = io.BytesIO(data);response.status = 206;response.geturl = lambda: URL
            response.headers = {'Content-Range': content_range}
            with patch('music_index.urllib.request.build_opener') as build:
                build.return_value.open.return_value = response
                with self.assertRaises(ValueError):RangeZip(URL)

    def test_manifest_only_accepts_registered_https_downloads(self):
        for url in ('http://loyaltyfreakmusic.com/x.zip', 'https://127.0.0.1/x.zip', 'https://loyaltyfreakmusic.com:9000/x.zip', 'https://u:p@loyaltyfreakmusic.com/x.zip'):
            with self.assertRaises(ValueError):RangeZip(url)

    def test_music_job_is_supported_without_launching_sfx_work(self):
        with patch('discovery.subprocess.Popen') as launch:
            import os
            launch.return_value.pid = os.getpid()
            job = DiscoveryJobs(self.lib).start('music')['job']
        from discover import Runner
        runner = Runner(self.lib, DiscoveryJobs(self.lib), job)
        runner.valid_pages = 1
        with patch.object(runner, 'tracks') as music, patch.object(runner, 'sfx') as sfx:
            runner.run()
        music.assert_called_once();sfx.assert_not_called()


for name in vars(fixtures.LibraryTests):
    if name.startswith('test_') and name not in vars(MusicIndexTests):setattr(MusicIndexTests, name, None)

if __name__ == '__main__':unittest.main()
