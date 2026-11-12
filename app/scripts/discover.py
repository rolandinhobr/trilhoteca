"""Bounded live discovery from registered indexes and external audio directories."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import ipaddress
import json
import re
import shutil
import socket
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from library import Library, ROOT, now, slug
from discovery import DiscoveryJobs, merge_assets
from collect_catalog import collect_scott, collect_loyalty, proof, rights, tags

USER_AGENT = 'TrilhotecaPersonal/0.2 (+private small-batch audio catalogue)'
REGISTERED = {'www.scottbuckley.com.au', 'loyaltyfreakmusic.com', 'opengameart.org', 'kenney.nl'}
DIRECTORIES = [
    'https://www.trustfm.net/ebooks/CCSources.php',
    'https://creativecommons.org/about/program-areas/arts-culture/arts-culture-resources/legalmusicforvideos/',
    'https://github.com/fiehrfly/muses',
]
IGNORED = REGISTERED | {'creativecommons.org', 'www.trustfm.net', 'trustfm.net', 'github.com', 'www.paypal.com', 'paypal.me', 'www.youtube.com', 'youtube.com', 'youtu.be', 'x.com', 'twitter.com', 'www.facebook.com', 'facebook.com', 'www.flickr.com', 'www.ebay.com', 'www.addtoany.com', 'web.archive.org', 'en.wikipedia.org', 'www.amazon.com', 'www.google.com', 'fonts.google.com', 'secure.gravatar.com', 'www.patreon.com', 'ko-fi.com', 'soundcloud.com', 'www.instagram.com', 'instagram.com', 'giving.fundraiseup.com', 'giving.gofundme.com', 'mail.creativecommons.org', 'wordpress.org', 'www.w3.org'}


def validate_public_url(url):
    p = urllib.parse.urlparse(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError('Página deve usar HTTPS público.')
    addresses = socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Endereço local ou reservado não é uma fonte externa.')
    return url


def html(url):
    validate_public_url(url)
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            validate_public_url(newurl)
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    with urllib.request.build_opener(Redirect()).open(urllib.request.Request(url, headers={'User-Agent': USER_AGENT}), timeout=18) as response:
        kind = response.headers.get('Content-Type', '').lower()
        if not any(t in kind for t in ('html', 'xml', 'text/plain')):
            raise ValueError('A fonte não devolveu uma página de informações.')
        raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError('Página excede o limite de leitura.')
    time.sleep(.7)
    return BeautifulSoup(raw, 'html.parser'), raw


def index_urls(soup, base, adapter):
    selectors = {'scott': 'article h1 a, article h2 a', 'loyalty': 'a.tease_thumb', 'oga': '.art-preview-title a'}
    urls = []
    for a in soup.select(selectors[adapter]):
        url = urllib.parse.urljoin(base, a.get('href', '')).split('#')[0].split('?')[0]
        p = urllib.parse.urlparse(url)
        if p.hostname in REGISTERED and url not in urls:
            urls.append(url)
    return urls


def oga_records(soup, raw, url, lib):
    content = soup.select_one('.node')
    if not content:
        raise ValueError('Ficha de música não encontrada.')
    title_node = content.select_one('h1, h2')
    license_field = content.select_one('.field-name-field-art-licenses')
    author_field = content.select_one('.field-name-author-submitter .username')
    if not title_node or not author_field or not license_field or not license_field.find('a', href=re.compile(r'creativecommons.org/publicdomain/zero/1.0')):
        raise ValueError('Autor e permissão CC0 precisam estar explícitos na ficha.')
    title = title_node.get_text(' ', strip=True); artist = author_field.get_text(' ', strip=True)
    field = content.select_one('.field-name-field-art-description')
    description = field.get_text(' ', strip=True) if field else ''
    text = content.get_text(' ', strip=True)
    if re.search(r'\b(suno|udio|ai[- ]generated|generated (?:by|with) ai|cover of|remix of)\b', description, re.I):
        raise ValueError('Geração por IA ou versão de obra alheia declarada; ficou fora desta seleção.')
    original = [a.get_text(' ', strip=True) for a in content.select('.field-name-field-art-tags a')]
    notice_field = content.select_one('.field-name-field-copyright-notice')
    notice = notice_field.get_text(' ', strip=True) if notice_field else ''
    evidence = [proof(lib.root, 'oga-' + slug(url.rstrip('/').split('/')[-1]), url, raw, text)]
    # Index direct audio without transferring it. Archive-only pages remain pending.
    choices = {}
    for a in content.select('.field-name-field-art-files a[href]'):
        download = urllib.parse.urljoin(url, a['href'])
        p = urllib.parse.urlparse(download); filename = urllib.parse.unquote(Path(p.path).name)
        ext = Path(filename).suffix.lower()
        if p.scheme != 'https' or p.hostname != 'opengameart.org' or ext not in ('.mp3', '.ogg', '.wav', '.flac'):
            continue
        key = Path(filename).stem.lower()
        if key not in choices or ext == '.mp3':
            choices[key] = (filename, download, ext)
    if not choices:
        raise ValueError('Página oferece somente pacotes ou formato ainda não integrado; nenhum áudio foi baixado.')
    records = []
    for filename, download, ext in choices.values():
        track = title if len(choices) == 1 else title + ' · ' + Path(filename).stem.replace('_', ' ')
        aid = hashlib.sha256((url + '|' + filename).encode()).hexdigest()[:20]
        r = rights('CC0 1.0', 'https://creativecommons.org/publicdomain/zero/1.0/', evidence, track, artist, url)
        if notice:
            r['source_attribution_notice'] = notice
        records.append({'id': aid, 'kind': 'music', 'title': track, 'artist': artist, 'album': title,
            'source_name': 'OpenGameArt', 'source_url': url, 'download_url': download, 'extension': ext,
            'duration': None, 'vocals': False if any(t.lower() == 'instrumental' for t in original) or re.search(r'\b(?:no vocals|instrumental track)\b', description, re.I) else None,
            'tags': tags(original), 'description': description[:5000], 'source_description': description[:5000],
            'metadata_basis': 'tags e descrição da ficha publicadas pelo autor; duração medida ao preparar a prévia',
            'editorial_status': 'candidate', 'rights': r, 'discovered_at': now()})
    return records


def should_retry(body):
    from datetime import datetime, timezone
    if not body:
        return True
    if body['status'] == 'imported':
        return False
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(body['checked'])).total_seconds()
    return age > (86400 if body['status'] == 'failed' else 7 * 86400)


class Runner:
    def __init__(self, lib, jobs, job):
        self.lib, self.jobs, self.job = lib, jobs, job
        self.valid_pages = 0
        self.scratch = lib.data / 'discovery-research'; self.scratch.mkdir(exist_ok=True)

    def progress(self, **changes):
        self.job = self.jobs.update(self.job['id'], **changes)

    def error(self, url, reason):
        errors = self.job['errors'][-99:] + [{'url': url, 'reason': str(reason)}]
        self.progress(errors=errors)

    def tracks(self):
        from music_index import loyalty_records
        initial = self.lib.stats(); self.progress(before=initial)
        with self.lib.db() as db:
            known = {json.loads(r['body'])['source_url'] for r in db.execute('SELECT body FROM assets')}
            seen = {r['url']: json.loads(r['body']) for r in db.execute('SELECT * FROM discovery_seen')}
        # Distinct cursor because the music index now exposes 144 items per page.
        for adapter in ('scott', 'oga', 'loyalty'):
            cursor_key = 'oga-music-144' if adapter == 'oga' else adapter
            with self.lib.db() as db:
                r = db.execute('SELECT page FROM discovery_cursors WHERE source=?', (cursor_key,)).fetchone()
                old = db.execute("SELECT page FROM discovery_cursors WHERE source='oga'").fetchone()
            cursor = r['page'] if r else max(1, old['page'] // 6) if adapter == 'oga' and old else 1
            pages = list(dict.fromkeys([0] + list(range(cursor, cursor + self.job['pages']))))
            for page in pages:
                if adapter == 'scott':
                    url = 'https://www.scottbuckley.com.au/library/' + (f'page/{page + 1}/' if page else '')
                elif adapter == 'loyalty':
                    url = 'https://loyaltyfreakmusic.com/music/' + (f'page/{page + 1}/' if page else '')
                else:
                    url = 'https://opengameart.org/art-search-advanced?' + urllib.parse.urlencode({'field_art_type_tid[0]': '12', 'field_art_licenses_tid[0]': '4', 'sort_by': 'created', 'sort_order': 'DESC', 'items_per_page': '144', 'page': page})
                self.progress(message=f'Lendo {adapter} · página {page + 1}…')
                try:
                    soup, _ = html(url); self.valid_pages += 1; links = index_urls(soup, url, adapter)
                except Exception as e:
                    if isinstance(e, urllib.error.HTTPError) and e.code == 404 and page:
                        with self.lib.db() as db: db.execute('INSERT OR REPLACE INTO discovery_cursors VALUES (?,?)', (cursor_key, 1))
                        break
                    self.error(url, e); break
                if not links:
                    if page:
                        with self.lib.db() as db: db.execute('INSERT OR REPLACE INTO discovery_cursors VALUES (?,?)', (cursor_key, 1))
                    break
                if page == 0:
                    host = {'scott': 'www.scottbuckley.com.au', 'oga': 'opengameart.org', 'loyalty': 'loyaltyfreakmusic.com'}[adapter]
                    retries = [u for u, state in seen.items() if urllib.parse.urlparse(u).hostname == host and should_retry(state) and u not in known][:12]
                    links = list(dict.fromkeys(retries + links))
                pending = [u for u in links if u not in known and should_retry(seen.get(u))]

                def inspect(detail):
                    try:
                        if adapter == 'scott': records = collect_scott({'url': detail}, self.scratch, self.lib)
                        else:
                            page_soup, raw = html(detail)
                            records = (loyalty_records if adapter == 'loyalty' else oga_records)(page_soup, raw, detail, self.lib)
                        return detail, records, {'status': 'imported', 'reason': '', 'checked': now()}
                    except Exception as e:
                        return detail, [], {'status': 'failed' if isinstance(e, OSError) else 'unsupported', 'reason': str(e), 'checked': now()}

                # Three bounded requests; mutations and per-page merges remain sequential.
                batch, states = [], []
                with ThreadPoolExecutor(max_workers=3) as pool:
                    for detail, records, checked in pool.map(inspect, pending):
                        states.append((detail, checked)); seen[detail] = checked
                        if checked['status'] == 'imported':
                            batch.extend(records); known.add(detail)
                        else:
                            self.progress(skipped=self.job['skipped'] + 1); self.error(detail, checked['reason'])
                        self.progress(checked=self.job['checked'] + 1, message='Conferindo músicas · ' + urllib.parse.unquote(detail.rstrip('/').split('/')[-1]))
                count = merge_assets(self.lib, batch)
                self.progress(added=self.job['added'] + count)
                with self.lib.db() as db:
                    for detail, checked in states: db.execute('INSERT OR REPLACE INTO discovery_seen VALUES (?,?)', (detail, json.dumps(checked)))
                    if page: db.execute('INSERT OR REPLACE INTO discovery_cursors VALUES (?,?)', (cursor_key, page + 1))
        self.progress(after=self.lib.stats())

    def sfx(self):
        from collect_sfx import kenney_records, oga_sfx_records
        if not self.job.get('before'):
            self.progress(before=self.lib.stats())
        with self.lib.db() as db:
            known = {json.loads(r['body'])['source_url'] for r in db.execute('SELECT body FROM assets')}
            seen = {r['url']: json.loads(r['body']) for r in db.execute('SELECT * FROM discovery_seen')}

        def incorporate(detail, adapter):
            if detail in known or not should_retry(seen.get(detail)):
                return
            self.progress(message='Conferindo efeitos · ' + urllib.parse.unquote(detail.rstrip('/').split('/')[-1]))
            try:
                soup, raw = html(detail); self.valid_pages += 1
                records = (kenney_records if adapter == 'kenney' else oga_sfx_records)(soup, raw, detail, self.scratch, self.lib)
                count = merge_assets(self.lib, records)
                self.progress(added=self.job['added'] + count)
                known.add(detail); status, reason = 'imported', ''
            except Exception as e:
                reason = str(e); status = 'failed' if isinstance(e, OSError) else 'unsupported'
                self.progress(skipped=self.job['skipped'] + 1); self.error(detail, e)
            checked = {'status': status, 'reason': reason, 'checked': now()}
            with self.lib.db() as db:
                db.execute('INSERT OR REPLACE INTO discovery_seen VALUES (?,?)', (detail, json.dumps(checked)))
            seen[detail] = checked
            self.progress(checked=self.job['checked'] + 1)

        try:
            soup, _ = html('https://kenney.nl/assets/category:Audio'); self.valid_pages += 1
            packs = list(dict.fromkeys(urllib.parse.urljoin('https://kenney.nl', a['href']) for a in soup.select('a[href]') if re.fullmatch(r'https://kenney.nl/assets/[a-z0-9-]+', a['href'])))
            for detail in packs:
                if 'music-jingles' not in detail and 'voiceover' not in detail:
                    incorporate(detail, 'kenney')
        except Exception as e:
            self.error('https://kenney.nl/assets/category:Audio', e)

        # Environmental and transition recordings supplement the game-oriented indexes.
        curated = ('the-shop', 'rain-loopable', 'swishes-sound-pack', 'storm-siren',
                   'footsteps-0', 'fire-crackling', 'beach-ocean-waves', 'ambient-bird-sounds',
                   'high-traffic-road-sounds', 'various-paper-sound-effects', 'door-open-door-close-set')
        for name in curated:
            incorporate('https://opengameart.org/content/' + name, 'oga')
        for ordering in ('count', 'created'):
            cursor_key = 'oga-sfx-' + ordering
            with self.lib.db() as db:
                row = db.execute('SELECT page FROM discovery_cursors WHERE source=?', (cursor_key,)).fetchone()
            cursor = row['page'] if row else 0
            pages = list(dict.fromkeys([0] + list(range(cursor, cursor + self.job['pages']))))
            for page in pages:
                url = 'https://opengameart.org/art-search-advanced?' + urllib.parse.urlencode({'field_art_type_tid[0]': '13', 'field_art_licenses_tid[0]': '4', 'sort_by': ordering, 'sort_order': 'DESC', 'page': page, 'items_per_page': 24})
                self.progress(message=f'Procurando efeitos no OpenGameArt · {ordering} · página {page + 1}…')
                try:
                    soup, _ = html(url); self.valid_pages += 1; links = index_urls(soup, url, 'oga')
                except Exception as e:
                    self.error(url, e); break
                if not links:
                    with self.lib.db() as db:
                        db.execute('INSERT OR REPLACE INTO discovery_cursors VALUES (?,0)', (cursor_key,))
                    break
                for detail in links:
                    incorporate(detail, 'oga')
                with self.lib.db() as db:
                    db.execute('INSERT OR REPLACE INTO discovery_cursors VALUES (?,?)', (cursor_key, page + 1))
        self.progress(after=self.lib.stats())

    def sources(self):
        self.progress(message='Esta busca é mais demorada: procurando repositórios e conferindo suas páginas. Áudios não são importados nesta etapa.')
        choices = {}; already = {c['domain'] for c in self.jobs.candidates()}
        with self.lib.db() as db:
            previous = {r['url'][7:]: json.loads(r['body']) for r in db.execute("SELECT * FROM discovery_seen WHERE url LIKE 'source:%'")}
        already.update(domain for domain, state in previous.items() if not should_retry(state))
        for directory in DIRECTORIES:
            try:
                soup, raw = html(directory)
                container = soup.select_one('main, article, .markdown-body') or soup
                for a in container.select('a[href]'):
                    url = urllib.parse.urljoin(directory, a['href'])
                    p = urllib.parse.urlparse(url); domain = (p.hostname or '').lower().removeprefix('www.')
                    label = a.get_text(' ', strip=True)
                    if p.scheme != 'https' or not domain or domain in {h.removeprefix('www.') for h in IGNORED} or not label or len(label) > 100 or domain in already:
                        continue
                    if any(v in domain for v in ('githubassets', 'githubusercontent', 'linkedin', 'google', 'gravatar', 'shields.io', 'wikimedia', 'fundraiseup', 'openstreetmap', 'creativecommons')):
                        continue
                    # Directory reference is provenance, never a license approval.
                    choices.setdefault(domain, {'domain': domain, 'url': url, 'reference_url': directory, 'reference_label': label})
            except Exception as e:
                self.error(directory, e)
        # Also follow artist websites explicitly linked from music fiches already indexed.
        with self.lib.db() as db:
            originals = list(dict.fromkeys(json.loads(r['body'])['source_url'] for r in db.execute('SELECT body FROM assets') if json.loads(r['body'])['source_name'] == 'OpenGameArt'))[:8]
        for source in originals:
            try:
                soup, _ = html(source)
                for a in soup.select('.field-name-field-art-description a[href], .field-name-field-copyright-notice a[href]'):
                    p = urllib.parse.urlparse(a['href']); domain = (p.hostname or '').lower().removeprefix('www.')
                    if p.scheme == 'https' and domain and domain not in already and domain not in {h.removeprefix('www.') for h in IGNORED}:
                        choices.setdefault(domain, {'domain': domain, 'url': a['href'], 'reference_url': source, 'reference_label': 'Site citado pelo artista'})
            except Exception as e:
                self.error(source, e)
        # Bound each click; rotate past previously checked references on later runs.
        with self.lib.db() as db:
            r = db.execute("SELECT page FROM discovery_cursors WHERE source='external'").fetchone()
        cursor = r['page'] if r else 0
        pending = list(choices.values()); selected = (pending[cursor:] + pending[:cursor])[:24]
        for c in selected:
            self.progress(message='Conferindo nova fonte · ' + c['domain'])
            try:
                soup, raw = html(c['url'])
                for n in soup.select('script, style, nav, footer, header'):
                    n.decompose()
                text = soup.get_text(' ', strip=True)
                if not re.search(r'\b(music|audio|sound|musique|música|trilha)\b', text, re.I):
                    raise ValueError('A página não apresentou um acervo de áudio identificável.')
                title = soup.title.get_text(' ', strip=True) if soup.title else c['reference_label']
                markers = list(dict.fromkeys(m.group(0) for m in re.finditer(r'CC0|CC[- ]BY(?:[- ]NC|[- ]SA)?(?:\s*\d\.\d)?|Creative Commons|public domain|royalty[- ]free|commercial use', text, re.I)))[:8]
                direct = sum(bool(re.search(r'\.(mp3|wav|ogg|flac)(?:\?|$)', a.get('href',''), re.I)) for a in soup.select('a[href]'))
                c.update(name=title[:180], found=now(), status='pending_review', license_hints=markers,
                         direct_audio_links=direct, excerpt=text[:800], rights_verified=False,
                         next_step='Conferir permissões por faixa e conectar a forma de busca/download antes de importar músicas.')
                c['evidence'] = proof(self.lib.root, 'source-' + slug(c['domain']), c['url'], raw, text[:30000])
                with self.lib.db() as db:
                    db.execute('INSERT OR IGNORE INTO source_candidates VALUES (?,?)', (c['domain'], json.dumps(c, ensure_ascii=False)))
                self.progress(added=self.job['added'] + 1)
                result_status = 'imported'
            except Exception as e:
                self.progress(skipped=self.job['skipped'] + 1); self.error(c['url'], e)
                result_status = 'failed'
            with self.lib.db() as db:
                db.execute('INSERT OR REPLACE INTO discovery_seen VALUES (?,?)', ('source:' + c['domain'], json.dumps({'status': result_status, 'checked': now()})))
            self.progress(checked=self.job['checked'] + 1)
        with self.lib.db() as db:
            db.execute("INSERT OR REPLACE INTO discovery_cursors VALUES ('external',?)", ((cursor + len(selected)) % max(1, len(pending)),))
        self.progress(candidates_total=len(self.jobs.candidates()))

    def run(self):
        self.progress(status='running')
        try:
            if self.job['mode'] in ('tracks', 'music', 'sfx'):
                if self.job['mode'] in ('tracks', 'music'):
                    self.tracks()
                if self.job['mode'] in ('tracks', 'sfx'):
                    self.sfx()
                message=f"Busca concluída: {self.job['added']} novos sons entraram na biblioteca."
            else:
                self.sources(); message=f"Busca concluída: {self.job['added']} novas fontes encontradas para conferência."
            if self.job['errors'] and (self.job['checked'] == 0 or self.job['mode'] in ('tracks','music','sfx') and self.valid_pages == 0):
                self.progress(status='failed', message='As fontes não responderam nesta tentativa. O catálogo anterior foi preservado.', finished=now())
            else:
                self.progress(status='complete', message=message, finished=now())
        except Exception as e:
            self.error('worker', e); self.progress(status='failed', message='A busca parou. Os resultados já incorporados foram preservados.', finished=now())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--job-id', required=True); args = parser.parse_args()
    lib = Library(); jobs = DiscoveryJobs(lib); job = jobs.status(args.job_id)
    if not job:
        raise SystemExit('Busca não encontrada.')
    if (lib.data / 'catalog.json').exists():
        backups = lib.data / 'catalog-backups'; backups.mkdir(exist_ok=True)
        shutil.copy2(lib.data / 'catalog.json', backups / (job['id'] + '.json'))
    Runner(lib, jobs, job).run()
