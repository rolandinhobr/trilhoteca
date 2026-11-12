"""Music album manifests read with bounded HTTP ranges, without fetching audio."""
import hashlib
import io
import re
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from library import now, slug
from collect_catalog import proof, rights, tags


class RangeZip(io.RawIOBase):
    """Seekable, small-range reader for the existing approved download host."""
    def __init__(self, url):
        super().__init__()
        p = urllib.parse.urlparse(url)
        if p.scheme != 'https' or p.hostname != 'loyaltyfreakmusic.com' or p.username or p.password or p.port not in (None, 443):
            raise ValueError('Manifesto deve vir do download oficial do artista.')
        self.url, self.pos, self.transferred = url, 0, 0
        class SameFileRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                raise ValueError('Manifesto redirecionou para outro endereço; precisa de conferência.')
        self.opener = urllib.request.build_opener(SameFileRedirect())
        self.size = None
        self._range(0, 0)
        if self.size > 250 * 1024 * 1024:
            raise ValueError('Álbum excede o limite de 250 MB para download sob demanda.')

    def _range(self, start, end):
        req = urllib.request.Request(self.url, headers={'User-Agent': 'TrilhotecaPersonal/0.3', 'Range': f'bytes={start}-{end}', 'Accept-Encoding': 'identity'})
        with self.opener.open(req, timeout=20) as response:
            if response.geturl() != self.url or response.status != 206:
                raise ValueError('Servidor não oferece leitura parcial do manifesto; álbum não foi baixado.')
            match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
            if not match or tuple(map(int, match.groups()[:2])) != (start, end):
                raise ValueError('Resposta parcial inválida.')
            size = int(match.group(3))
            if self.size is not None and size != self.size:
                raise ValueError('Álbum mudou durante a leitura.')
            self.size = size
            raw = response.read(end - start + 2)
            if len(raw) != end - start + 1:
                raise ValueError('Manifesto incompleto.')
            self.transferred += len(raw)
            return raw

    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos

    def seek(self, offset, whence=0):
        pos = offset if whence == 0 else self.pos + offset if whence == 1 else self.size + offset
        if pos < 0: raise ValueError('Posição inválida.')
        self.pos = pos
        return pos

    def read(self, size=-1):
        size = min(self.size - self.pos, size if size >= 0 else self.size - self.pos)
        if size <= 0: return b''
        if size > 2 * 1024 * 1024 or self.transferred + size > 4 * 1024 * 1024:
            raise ValueError('Manifesto excede o limite de leitura de metadados.')
        raw = self._range(self.pos, self.pos + size - 1)
        self.pos += len(raw)
        return raw


def audio_members(infos):
    chosen = {}
    if len(infos) > 12000: raise ValueError('Álbum tem arquivos demais.')
    for i in infos:
        p = PurePosixPath(i.filename)
        if i.is_dir() or p.is_absolute() or '..' in p.parts or '\\' in i.filename or any(v.startswith('.') or v == '__MACOSX' for v in p.parts): continue
        if ((i.external_attr >> 16) & 0o170000) == 0o120000: continue
        ext = p.suffix.lower()
        if ext not in ('.mp3', '.ogg', '.wav', '.flac') or not 0 < i.file_size <= 250 * 1024 * 1024: continue
        key = '/'.join(v for v in p.with_suffix('').parts if v.lower() not in ('mp3', 'ogg', 'wav', 'flac')) .lower()
        if key not in chosen or ext == '.mp3': chosen[key] = i
    return sorted(chosen.values(), key=lambda i: i.filename)


def loyalty_records(soup, raw, url, lib):
    content = soup.select_one('article')
    if not content: raise ValueError('Ficha do álbum não encontrada.')
    text = content.get_text(' ', strip=True)
    heading = next((h for h in content.select('h1') if 'sr_only' not in h.get('class', [])), None)
    match = re.search(r'By\s*:\s*(.*?)\s*Genre\s*:\s*(.*?)\s*Licence\s*:', text)
    lic = content.find('a', href=re.compile(r'^https://creativecommons.org/publicdomain/zero/1.0/?$'))
    if not heading or not match or not lic: raise ValueError('Artista, gêneros e CC0 precisam estar explícitos na ficha.')
    artist, genres = match.groups(); title = heading.get_text(' ', strip=True)
    original = [v.strip() for v in genres.split(',')]
    if 'cover and remix' in original or re.search(r'\b(?:cover of|remix of|suno|udio|ai[- ]generated)\b', text, re.I):
        raise ValueError('Versão de obra alheia ou geração por IA declarada; fora desta seleção.')
    link = content.find('a', href=re.compile(r'^https://loyaltyfreakmusic.com/.*\.zip$'))
    if not link: raise ValueError('Download oficial não encontrado.')
    parts = urllib.parse.urlsplit(link['href'])
    download = urllib.parse.urlunsplit(parts._replace(path=urllib.parse.quote(parts.path, safe='/%:@!$&\'()*+,;=-._~')))
    with RangeZip(download) as remote, zipfile.ZipFile(remote) as archive:
        members = audio_members(archive.infolist())
        transferred = remote.transferred
    if not members: raise ValueError('Nenhum áudio individual encontrado no álbum.')
    evidence = [proof(lib.root, 'lfm-' + slug(url.rstrip('/').split('/')[-1]), url, raw, text)]
    # Album-level genres are retained as such; no fabricated per-track instrumentation.
    records = []
    for i in members:
        name = Path(i.filename).stem
        name = re.sub(r'^.*? - .*? - \d+ ', '', name)
        name = re.sub(r'^\d+[. _-]+', '', name).strip() or title
        records.append({'id': hashlib.sha256((url + '|' + i.filename).encode()).hexdigest()[:20],
            'kind': 'music', 'title': name, 'artist': artist, 'album': title,
            'source_name': 'Loyalty Freak Music', 'source_url': url, 'download_url': download,
            'archive_member': i.filename, 'extension': Path(i.filename).suffix.lower(),
            'duration': None, 'vocals': None, 'tags': tags(original), 'collection_tags': tags(original),
            'description': f'Faixa do álbum {title}. Gêneros declarados pelo artista para o álbum: {genres}.',
            'metadata_basis': 'nome da faixa no manifesto oficial; gêneros do álbum; voz e duração a conferir na prévia',
            'manifest_bytes_read': transferred, 'editorial_status': 'candidate', 'discovered_at': now(),
            'rights': rights('CC0 1.0', 'https://creativecommons.org/publicdomain/zero/1.0/', evidence, name, artist, url)})
    return records
