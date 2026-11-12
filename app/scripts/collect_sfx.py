"""Verified CC0 effects: inspect official pack manifests, keep downloads on demand."""
import hashlib
import re
import shutil
import subprocess
import urllib.parse
import zipfile
from pathlib import Path

from collect_catalog import proof, rights, tags
from library import now, slug, MAX_BYTES

AUDIO = ('.mp3', '.wav', '.ogg', '.flac')


def valid_member(item):
    p = Path(item.filename)
    return (p.suffix.lower() in AUDIO and not p.is_absolute() and '..' not in p.parts
            and not any(s.startswith(('.', '__MACOSX')) for s in p.parts)
            and 0 < item.file_size <= MAX_BYTES
            and (item.external_attr >> 16) & 0o170000 != 0o120000)


def measure(path):
    probe = shutil.which('ffprobe') or next((str(p) for p in [Path('/opt/homebrew/bin/ffprobe'), Path('/usr/local/bin/ffprobe')] if p.is_file()), None)
    if not probe:
        return None
    r = subprocess.run([probe, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', str(path)], capture_output=True, text=True, timeout=15)
    try:
        value = float(r.stdout.strip())
        return value if value > 0 else None
    except ValueError:
        return None


def pack_entries(download, scratch, lib, label):
    bundle = scratch / (label + '-' + hashlib.sha256(download.encode()).hexdigest()[:12] + '.zip')
    if not bundle.exists():
        lib._fetch(download, bundle)
    chosen, measured = {}, []
    with zipfile.ZipFile(bundle) as archive:
        members = archive.infolist()
        if len(members) > 12000 or sum(i.file_size for i in members) > 1024 * 1024 * 1024:
            raise ValueError('Pacote grande demais para esta coleta.')
        for item in members:
            if not valid_member(item):
                continue
            key = str(Path(item.filename).with_suffix('')).lower()
            key = re.sub(r'(^|/)(?:mp3|wav|ogg|flac)(/|$)', r'\1', key)
            rank = {'.mp3': 0, '.wav': 1, '.ogg': 2, '.flac': 3}
            if key not in chosen or rank[Path(item.filename).suffix.lower()] < rank[Path(chosen[key].filename).suffix.lower()]:
                chosen[key] = item
        for item in chosen.values():
            temp = scratch / ('measure-' + hashlib.sha256(item.filename.encode()).hexdigest()[:12] + Path(item.filename).suffix.lower())
            try:
                with archive.open(item) as source, temp.open('wb') as target:
                    shutil.copyfileobj(source, target)
                measured.append((item.filename, measure(temp), hashlib.sha256(temp.read_bytes()).hexdigest()))
            finally:
                temp.unlink(missing_ok=True)
    return measured


def make_record(lib, source, title, artist, description, original, evidence, download, filename=None, duration=None, single=False):
    name = Path(filename or urllib.parse.unquote(urllib.parse.urlparse(download).path)).stem
    readable = re.sub(r'([a-z])([A-Z])', r'\1 \2', name).replace('_', ' ').replace('-', ' ')
    relative = str(Path(filename).with_suffix('')) if filename else readable
    # Individual filenames and folders carry the object/material. A mixed pack's tags
    # must not make every member a rain/footstep/door sound.
    specific = ' '.join([relative, title] + (original + [description] if single else []))
    aid = hashlib.sha256((source + '|' + (filename or urllib.parse.unquote(Path(urllib.parse.urlparse(download).path).name))).encode()).hexdigest()[:20]
    vocal = True if re.search(r'\b(voiceover|voice|speech|dialogue|taunt|spoken)\b', specific, re.I) else None
    display = readable if filename and len(readable)>2 and not readable.isdigit() else (title if single else title + ' · ' + readable)
    record = {'id': aid, 'kind': 'sfx', 'title': display,
              'artist': artist, 'album': title, 'source_name': 'Kenney' if artist == 'Kenney' else 'OpenGameArt',
              'source_url': source, 'download_url': download, 'extension': Path(filename or urllib.parse.urlparse(download).path).suffix.lower(),
              'duration': duration, 'vocals': vocal, 'tags': tags(original if single else re.findall(r'[a-zA-Z]+', specific)),
              'collection_tags': original, 'description': description[:5000], 'search_text': specific,
              'metadata_scope': 'individual' if single else 'member', 'member_text': relative,
              'metadata_basis': 'objeto/material pelo nome e pasta do arquivo; contexto declarado na ficha; duração medida no pacote' if filename else 'informações declaradas na ficha; duração medida ao preparar a prévia',
              'editorial_status': 'candidate', 'discovered_at': now(),
              'rights': rights('CC0 1.0', 'https://creativecommons.org/publicdomain/zero/1.0/', evidence, readable, artist, source)}
    if filename:
        record['archive_member'] = filename
    return record


def kenney_records(soup, raw, url, scratch, lib):
    if not soup.find('a', href=re.compile(r'creativecommons.org/publicdomain/zero/1.0')):
        raise ValueError('CC0 não confirmada na página oficial.')
    link = soup.find('a', href=re.compile(r'^https://kenney.nl/.*\.zip$'))
    heading = soup.find('h1')
    if not link or not heading:
        raise ValueError('Título e download oficial não encontrados.')
    title = heading.get_text(' ', strip=True)
    label = 'kenney-' + slug(url.rstrip('/').split('/')[-1])
    evidence = [proof(lib.root, label, url, raw, soup.get_text(' ', strip=True))]
    original = [a.get_text(' ', strip=True) for a in soup.select('a[href*="/assets/tag:"]')]
    records = []
    for filename, duration, digest in pack_entries(link['href'], scratch, lib, label):
        r = make_record(lib, url, title, 'Kenney', 'Efeito da coleção ' + title + '. Objeto e variação conforme o arquivo original.', original, evidence, link['href'], filename, duration)
        r['indexed_sha256'] = digest; records.append(r)
    return records


def oga_sfx_records(soup, raw, url, scratch, lib):
    node = soup.select_one('.node')
    if not node:
        raise ValueError('Ficha de efeito não encontrada.')
    heading = node.select_one('h1,h2'); author = node.select_one('.field-name-author-submitter .username')
    license_field = node.select_one('.field-name-field-art-licenses')
    if not heading or not author or not license_field or not license_field.find('a', href=re.compile(r'creativecommons.org/publicdomain/zero/1.0')):
        raise ValueError('Autor e licença CC0 precisam estar explícitos na ficha.')
    art_type = node.select_one('.field-name-field-art-type')
    if art_type and 'Sound Effect' not in art_type.get_text():
        raise ValueError('A ficha não é um efeito sonoro.')
    title = heading.get_text(' ', strip=True); artist = author.get_text(' ', strip=True)
    desc = node.select_one('.field-name-field-art-description')
    description = desc.get_text(' ', strip=True) if desc else ''
    if re.search(r'\b(suno|udio|ai[- ]generated|generated (?:by|with) ai|cover of|remix of)\b', description, re.I):
        raise ValueError('Autoria/derivação precisa de conferência adicional.')
    original = [a.get_text(' ', strip=True) for a in node.select('.field-name-field-art-tags a')]
    evidence = [proof(lib.root, 'oga-sfx-' + slug(url.rstrip('/').split('/')[-1]), url, raw, node.get_text(' ', strip=True))]
    direct, packs = {}, {}
    for a in node.select('.field-name-field-art-files a[href]'):
        download = urllib.parse.urljoin(url, a['href'])
        p = urllib.parse.urlparse(download); filename = urllib.parse.unquote(Path(p.path).name)
        ext = Path(filename).suffix.lower()
        if p.scheme != 'https' or p.hostname != 'opengameart.org':
            continue
        if ext in AUDIO:
            key = Path(filename).stem.lower()
            if key not in direct or ext == '.mp3':
                direct[key] = download
        if ext == '.zip':
            # MP3/WAV/OGG editions of the same pack are alternatives, not new sounds.
            key = re.sub(r'\b(mp3|wav|ogg|flac)\b', '', Path(filename).stem.replace('_',' ').replace('-',' '), flags=re.I).strip()
            if key not in packs or 'mp3' in filename.lower():
                packs[key] = download
    records = [make_record(lib, url, title, artist, description, original, evidence, download, single=len(direct)==1 and not packs) for download in direct.values()]
    for download in packs.values():
        for filename, duration, digest in pack_entries(download, scratch, lib, 'oga-sfx'):
            r = make_record(lib, url, title, artist, description, original, evidence, download, filename, duration)
            r['indexed_sha256'] = digest; records.append(r)
    if not records:
        raise ValueError('Nenhum áudio direto ou ZIP compatível; ficha preservada para nova tentativa.')
    notice = node.select_one('.field-name-field-copyright-notice')
    if notice:
        for record in records:
            record['rights']['source_attribution_notice'] = notice.get_text(' ', strip=True)
    return records
