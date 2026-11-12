"""Small, explicit source list. No recursive crawler or platform harvesting."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from library import Library, ROOT, now, slug, catalog_lock

TRANSLATIONS = {'ambient': 'ambiente', 'guitar': 'guitarra', 'electronic': 'eletrônica',
                'piano': 'piano', 'orchestral': 'orquestral', 'strings': 'cordas',
                'peaceful': 'calmo', 'bittersweet': 'melancólico', 'dark': 'sombrio',
                'dramatic': 'dramático', 'epic': 'épico', 'tension': 'suspense',
                'mysterious': 'misterioso', 'sad': 'triste', 'uplifting': 'inspirador',
                'cute': 'lúdico', 'videogame music': 'jogos', 'soundtrack': 'trilha sonora',
                'shitty flute and silly songs': 'flauta e humor', 'utilitarian music': 'música para projetos',
                'click': 'clique', 'switch': 'transição', 'confirmation': 'confirmação',
                'error': 'erro', 'select': 'seleção', 'scroll': 'rolagem', 'tick': 'clique',
                'back': 'voltar', 'open': 'abrir', 'close': 'fechar', 'pluck': 'dedilhado'}


def tags(original):
    return list(dict.fromkeys([TRANSLATIONS.get(t.lower(), t.replace('-', ' ')) for t in original] + original))


def fetch_html(url, scratch, label):
    f = scratch / (label + '.html')
    # Saved pages are reused only within this collector run, not as a license refresh.
    req = urllib.request.Request(url, headers={'User-Agent': 'TrilhotecaPersonal/0.1 (+small private catalogue)'})
    raw = urllib.request.urlopen(req, timeout=45).read()
    f.write_bytes(raw)
    time.sleep(.7)
    return BeautifulSoup(raw, 'html.parser'), raw


def proof(root, label, url, raw, text):
    f = root / 'data' / 'evidence' / (label + '.txt')
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(f'Fonte: {url}\nCapturado em: {now()}\nSHA-256 da página: {hashlib.sha256(raw).hexdigest()}\n\nTexto visível da página:\n{text}\n', encoding='utf-8')
    return str(f.relative_to(root))


def rights(license_name, url, evidence, title, artist, source):
    credit = f"'{title}' by {artist} — {license_name}.\n{source}\nLicença: {url}"
    if artist == 'Scott Buckley':
        credit = f"'{title}' by Scott Buckley - released under CC-BY 4.0. www.scottbuckley.com.au\n{source}\nLicença: {url}"
    return {'status': 'verified', 'license': license_name, 'license_url': url, 'commercial': True,
            'advertising': True, 'video': True, 'attribution_required': license_name != 'CC0 1.0',
            'evidence': evidence, 'checked_at': now(), 'credit_text': credit,
            'basis': 'Permissão conferida na página da fonte; autoria declarada pela fonte.'}


def audio_duration(path):
    if not shutil.which('ffprobe'):
        return None
    p = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', str(path)], text=True, capture_output=True, timeout=20)
    try:
        return float(p.stdout.strip())
    except ValueError:
        return None


def collect_loyalty(config, scratch, lib):
    url = config['url']
    label = 'lfm-' + slug(url.rstrip('/').split('/')[-1])
    soup, raw = fetch_html(url, scratch, label)
    text = soup.get_text(' ', strip=True)
    title = next(h.get_text(' ', strip=True) for h in soup.find_all('h1') if 'sr_only' not in h.get('class', []))
    match = re.search(r'By\s*:\s*(.*?)\s*Genre\s*:\s*(.*?)\s*Licence\s*:', text)
    if not match:
        raise ValueError('Metadados de artista/gênero não encontrados.')
    artist, genres = match.groups()
    original = [v.strip() for v in genres.split(',')]
    if 'cover and remix' in original:
        raise ValueError('Álbum com covers/remixes ficou fora da primeira seleção.')
    license_link = soup.find('a', href=re.compile(r'creativecommons.org/publicdomain/zero/1.0'))
    if not license_link:
        raise ValueError('CC0 não confirmada nesta página.')
    dl = soup.find('a', href=re.compile(r'https://loyaltyfreakmusic.com/.*\.zip$'))
    if not dl:
        raise ValueError('Download oficial do álbum não encontrado.')
    download_url = dl['href']
    evidence = [proof(lib.root, label, url, raw, text)]
    bundle = scratch / (label + '.zip')
    if not bundle.exists():
        lib._fetch(download_url, bundle)
    records = []
    with zipfile.ZipFile(bundle) as z:
        files = [i for i in z.infolist() if Path(i.filename).suffix.lower() in ('.mp3', '.wav', '.ogg', '.flac') and not i.filename.startswith('__MACOSX/')]
        for i in sorted(files, key=lambda i: i.filename):
            if i.file_size > 250 * 1024 * 1024:
                continue
            tmp = scratch / ('measure' + Path(i.filename).suffix.lower())
            with z.open(i) as src, tmp.open('wb') as dst:
                shutil.copyfileobj(src, dst)
            measured = audio_duration(tmp)
            tmp.unlink()
            track = Path(i.filename).stem
            track = re.sub(r'^.*? - .*? - \d+ ', '', track)
            track = re.sub(r'^\d+[. _-]+', '', track).strip()
            aid = hashlib.sha256((url + '|' + i.filename).encode()).hexdigest()[:20]
            records.append({'id': aid, 'kind': 'music', 'title': track, 'artist': artist, 'album': title,
                'source_name': 'Loyalty Freak Music', 'source_url': url, 'download_url': download_url,
                'archive_member': i.filename, 'extension': Path(i.filename).suffix.lower(),
                'duration': measured, 'vocals': config.get('vocals'), 'tags': tags(original + config.get('tags', [])),
                'description': config['description'], 'metadata_basis': 'gêneros do álbum declarados pelo artista; duração medida no arquivo',
                'editorial_status': 'candidate', 'rights': rights('CC0 1.0', 'https://creativecommons.org/publicdomain/zero/1.0/', evidence, track, artist, url)})
    return records


def collect_scott(config, scratch, lib):
    url = config['url']
    label = 'sb-' + slug(url.rstrip('/').split('/')[-1])
    soup, raw = fetch_html(url, scratch, label)
    article = soup.find('article')
    if not article:
        raise ValueError('Ficha da faixa não encontrada.')
    title = article.find('h1').get_text(' ', strip=True)
    text = article.get_text(' ', strip=True)
    lic = article.find('a', href=re.compile(r'creativecommons.org/licenses/by/4.0'))
    if not lic or 'commercial' not in text.lower():
        raise ValueError('Permissão comercial CC BY não confirmada.')
    downloads = [a['href'] for a in article.find_all('a', href=True) if a['href'].lower().endswith('.mp3')]
    if not downloads:
        raise ValueError('MP3 oficial não encontrado.')
    original = [c.split('-', 1)[1].replace('-', ' ') for c in article.get('class', []) if c.startswith(('genre-', 'mood-', 'instrumentation-'))]
    paragraphs = [p.get_text(' ', strip=True) for p in article.find_all('p')]
    description = next((p for p in paragraphs if len(p) > 25 and not any(v in p for v in ['license', 'licensed', 'Attribution', 'Patreon', 'Download'])), '')
    evidence = [proof(lib.root, label, url, raw, '\n\n'.join([title, description, text[:text.find('This track was supported') if 'This track was supported' in text else 6000]]))]
    # A tags-only inference is deliberately not treated as proof that a track has no vocals.
    vocals = False if re.search(r'\bsolo piano\b|\binstrumental\b', description, re.I) else None
    aid = hashlib.sha256(url.encode()).hexdigest()[:20]
    return [{'id': aid, 'kind': 'music', 'title': title, 'artist': 'Scott Buckley', 'album': 'Creative Commons Music Library',
            'source_name': 'Scott Buckley', 'source_url': url, 'download_url': downloads[0], 'extension': '.mp3',
            'duration': None, 'vocals': vocals, 'tags': tags(original),
            'description': config.get('description') or description,
            'source_description': description, 'metadata_basis': 'gênero, clima e instrumentos declarados na página da faixa',
            'editorial_status': 'candidate',
            'content_id_note': 'O artista usa Content ID. No YouTube, inclua o crédito na descrição; a página original orienta a liberação de reivindicações.',
            'rights': rights('CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0/', evidence, title, 'Scott Buckley', url)}]


def collect_kenney(config, scratch, lib):
    url = config['url']
    label = 'kenney-interface'
    soup, raw = fetch_html(url, scratch, label)
    if not soup.find('a', href=re.compile(r'creativecommons.org/publicdomain/zero/1.0')):
        raise ValueError('CC0 não confirmada na página do pack.')
    link = soup.find('a', href=re.compile(r'https://kenney.nl/.*\.zip$'))
    if not link:
        raise ValueError('Download oficial não encontrado.')
    bundle = scratch / (label + '.zip')
    if not bundle.exists():
        lib._fetch(link['href'], bundle)
    evidence = [proof(lib.root, label, url, raw, soup.get_text(' ', strip=True))]
    records = []
    with zipfile.ZipFile(bundle) as z:
        for i in z.infolist():
            if Path(i.filename).name.lower() in ('license.txt', 'licence.txt'):
                f = lib.data / 'evidence' / 'kenney-pack-license.txt'
                f.write_bytes(z.read(i))
                evidence.append(str(f.relative_to(lib.root)))
        for i in sorted(z.infolist(), key=lambda i: i.filename):
            if Path(i.filename).suffix.lower() not in ('.ogg', '.wav', '.mp3'):
                continue
            tmp = scratch / ('measure' + Path(i.filename).suffix.lower())
            with z.open(i) as src, tmp.open('wb') as dst:
                shutil.copyfileobj(src, dst)
            measured = audio_duration(tmp)
            tmp.unlink()
            title = Path(i.filename).stem
            family = re.sub(r'\d+$', '', title).strip('_- ')
            aid = hashlib.sha256((url + '|' + i.filename).encode()).hexdigest()[:20]
            records.append({'id': aid, 'kind': 'sfx', 'title': title, 'artist': 'Kenney', 'album': 'Interface Sounds',
                'source_name': 'Kenney', 'source_url': url, 'download_url': link['href'], 'archive_member': i.filename,
                'extension': Path(i.filename).suffix.lower(), 'duration': measured, 'vocals': False,
                'tags': tags(['interface', 'ui', family]), 'description': 'Efeito pontual do pack Interface Sounds. Família indicada pelo nome do arquivo: ' + TRANSLATIONS.get(family, family) + '.',
                'metadata_basis': 'família do arquivo de origem; duração medida no áudio', 'editorial_status': 'candidate',
                'rights': rights('CC0 1.0', 'https://creativecommons.org/publicdomain/zero/1.0/', evidence, title, 'Kenney', url)})
    return records


def collect_oga(config, scratch, lib):
    url = config['url']
    label = 'oga-' + slug(url.rstrip('/').split('/')[-1])
    soup, raw = fetch_html(url, scratch, label)
    content = soup.select_one('.node') or soup
    title_node = content.select_one('h1, h2')
    if not title_node:
        raise ValueError('Título da coleção não encontrado.')
    title = title_node.get_text(' ', strip=True)
    license_field = content.select_one('.field-name-field-art-licenses')
    author_field = content.select_one('.field-name-author-submitter .username')
    if not license_field or not license_field.find('a', href=re.compile(r'creativecommons.org/publicdomain/zero/1.0')):
        raise ValueError('CC0 não confirmada na ficha.')
    if not author_field:
        raise ValueError('Autor não identificado.')
    artist = author_field.get_text(' ', strip=True)
    original = [a.get_text(' ', strip=True) for a in content.select('.field-name-field-art-tags a')]
    evidence = [proof(lib.root, label, url, raw, content.get_text(' ', strip=True))]
    links = content.select('.field-name-field-art-files a[href]')
    records = []
    for link in links:
        download = link['href']
        if not download.lower().endswith('.zip'):
            continue
        pack = scratch / (label + '-' + hashlib.sha256(download.encode()).hexdigest()[:8] + '.zip')
        if not pack.exists():
            lib._fetch(download, pack)
        # Collections often provide two encodings of the same song. Prefer MP3 for broad playback support.
        with zipfile.ZipFile(pack) as z:
            members = [i for i in z.infolist() if Path(i.filename).suffix.lower() in ('.mp3', '.wav', '.ogg') and not i.filename.startswith('__MACOSX/')]
            chosen = {}
            for i in members:
                key = Path(i.filename).stem.lower()
                if key not in chosen or Path(i.filename).suffix.lower() == '.mp3':
                    chosen[key] = i
            for i in sorted(chosen.values(), key=lambda x: x.filename):
                tmp = scratch / ('measure' + Path(i.filename).suffix.lower())
                with z.open(i) as src, tmp.open('wb') as dst:
                    shutil.copyfileobj(src, dst)
                measured = audio_duration(tmp)
                tmp.unlink()
                track = re.sub(r'^\d+[_ -]*(?:holiznacc0[_ -]*)?', '', Path(i.filename).stem, flags=re.I).replace('_', ' ').strip(' -')
                aid = hashlib.sha256((url + '|' + i.filename).encode()).hexdigest()[:20]
                records.append({'id': aid, 'kind': 'music', 'title': track, 'artist': artist, 'album': title,
                    'source_name': 'OpenGameArt / Holizna', 'source_url': url, 'download_url': download,
                    'archive_member': i.filename, 'extension': Path(i.filename).suffix.lower(), 'duration': measured,
                    'vocals': False if 'instrumental' in title.lower() or 'instrumental' in [t.lower() for t in original] else None,
                    'tags': tags(original), 'description': config['description'],
                    'metadata_basis': 'tags da coleção declaradas pelo autor; duração medida no arquivo', 'editorial_status': 'candidate',
                    'rights': rights('CC0 1.0', 'https://creativecommons.org/publicdomain/zero/1.0/', evidence, track, artist, url)})
    if not records:
        raise ValueError('Nenhum arquivo de coleção encontrado.')
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scratch', required=True, help='Pasta para páginas e pacotes de análise, fora da biblioteca.')
    parser.add_argument('--adapter', help='Atualiza apenas uma família de fontes, preservando as demais.')
    args = parser.parse_args()
    scratch = Path(args.scratch).resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    lib = Library()
    configs = json.loads((lib.data / 'sources.json').read_text())
    records, results = [], []
    routes = {'loyalty': collect_loyalty, 'scott': collect_scott, 'kenney': collect_kenney, 'oga': collect_oga}
    if args.adapter:
        configs = [c for c in configs if c['adapter'] == args.adapter]
    for config in configs:
        try:
            batch = routes[config['adapter']](config, scratch, lib)
            records.extend(batch)
            results.append({'url': config['url'], 'assets': len(batch), 'status': 'ok'})
            print(config['url'], len(batch), flush=True)
        except Exception as e:
            results.append({'url': config['url'], 'status': 'failed', 'error': str(e)})
            print('FALHOU', config['url'], str(e), flush=True)
    if not records:
        raise RuntimeError('Nenhuma fonte foi validada; catálogo anterior preservado.')
    with catalog_lock(lib.root):
        unique = {}
        refreshed_urls = {c['url'] for c in configs}
        if (lib.data / 'catalog.json').exists():
            # Revalidate only explicit pages; keep discoveries from the paginated indexes.
            unique.update({r['id']: r for r in json.loads((lib.data / 'catalog.json').read_text())['assets'] if r['source_url'] not in refreshed_urls})
        unique.update({r['id']: r for r in records})
        catalog = {'version': 1, 'collected': now(), 'note': 'Curadoria inicial por fontes; não representa escuta ou aprovação artística.', 'assets': list(unique.values())}
        target = lib.data / 'catalog.json'
        if target.exists():
            shutil.copy2(target, target.with_name('catalog.previous.json'))
        tmp = target.with_suffix('.json.part')
        tmp.write_text(json.dumps(catalog, ensure_ascii=False, indent=2))
        tmp.replace(target)
        (lib.data / 'collection-report.json').write_text(json.dumps({'created': now(), 'sources': results, 'music': sum(a['kind'] == 'music' for a in unique.values()), 'sfx': sum(a['kind'] == 'sfx' for a in unique.values())}, ensure_ascii=False, indent=2))
    print(json.dumps(Library().stats(), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
