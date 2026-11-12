"""Local catalogue, project context and on-demand acquisition for Trilhoteca."""
from __future__ import annotations

import hashlib
import fcntl
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import unicodedata
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parent
LOCKS: dict[str, threading.Lock] = {}
LOCK_GUARD = threading.Lock()
MAX_BYTES = 250 * 1024 * 1024


def now():
    return datetime.now(timezone.utc).isoformat()


def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value).lower()) if not unicodedata.combining(c))


def slug(value):
    return re.sub(r'[^a-z0-9]+', '-', normalize(value)).strip('-')[:80] or 'projeto'


@contextmanager
def catalog_lock(root):
    """Serialize index mutations across panel, discovery worker and MCP processes."""
    with (Path(root) / 'data/.catalog.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


class Library:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.data = self.root / 'data'
        self.data.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data / 'catalog.sqlite'
        with catalog_lock(self.root), self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, name TEXT NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS feedback(asset_id TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS uses(project_id TEXT, asset_id TEXT, created TEXT,
                    PRIMARY KEY(project_id,asset_id));
                CREATE TABLE IF NOT EXISTS downloads(asset_id TEXT PRIMARY KEY, path TEXT, sha256 TEXT, body TEXT);
            ''')
            seed = self.data / 'catalog.json'
            if seed.exists():
                current = json.loads(seed.read_text())['assets']
                current_ids = {a['id'] for a in current}
                for row in db.execute('SELECT id FROM assets').fetchall():
                    if row['id'] not in current_ids:
                        db.execute('DELETE FROM assets WHERE id=?', (row['id'],))
                for asset in current:
                    db.execute('INSERT INTO assets VALUES (?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',
                               (asset['id'], json.dumps(asset, ensure_ascii=False)))

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def projects(self):
        with self.db() as db:
            records = [json.loads(r['body']) for r in db.execute('SELECT body FROM projects ORDER BY rowid DESC')]
        return [p for p in records if not p.get('archived')]

    def project(self, project_id):
        with self.db() as db:
            r = db.execute('SELECT body FROM projects WHERE id=?', (project_id,)).fetchone()
        return json.loads(r['body']) if r else None

    def set_project(self, name, usage=None, monetized=None, sponsored=None, project_id=None):
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ValueError('Informe um nome de projeto com até 200 caracteres.')
        if usage not in (None, 'publicidade', 'proprio'):
            raise ValueError('Uso deve ser publicidade ou proprio.')
        if any(type(v) not in (bool, type(None)) for v in (monetized, sponsored)):
            raise ValueError('Monetização e patrocínio devem ser sim ou não, sem valores presumidos.')
        if project_id and not self.project(project_id):
            raise ValueError('Projeto não encontrado.')
        project = {'id': project_id or uuid.uuid4().hex, 'name': name.strip(),
                   'usage': usage, 'monetized': monetized, 'sponsored': sponsored, 'updated': now()}
        with self.db() as db:
            db.execute('INSERT INTO projects VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,body=excluded.body',
                       (project['id'], project['name'], json.dumps(project, ensure_ascii=False)))
        return {'project': project, **self.context_status(project)}

    def context_status(self, project):
        questions = []
        if not project or project.get('usage') is None:
            questions.append({'field': 'usage', 'question': 'É publicidade ou conteúdo próprio?',
                              'options': ['publicidade', 'proprio']})
        if not project or project.get('monetized') is None:
            questions.append({'field': 'monetized', 'question': 'O vídeo será monetizado?', 'options': [True, False]})
        if not project or project.get('sponsored') is None:
            questions.append({'field': 'sponsored', 'question': 'Tem patrocínio ou parceria comercial?', 'options': [True, False]})
        return {'needs_context': bool(questions), 'questions': questions}

    def asset(self, asset_id):
        with self.db() as db:
            row = db.execute('SELECT body FROM assets WHERE id=?', (asset_id,)).fetchone()
        if not row:
            raise ValueError('Faixa ou efeito não encontrado.')
        return json.loads(row['body'])

    def eligible(self, asset, project):
        if self.context_status(project)['needs_context']:
            return False, 'Preencha a finalidade do projeto.'
        rights = asset.get('rights', {})
        if rights.get('status') != 'verified' or not rights.get('evidence'):
            return False, 'Permissão ainda não conferida.'
        for path in rights['evidence']:
            proof = (self.root / path).resolve()
            if not proof.is_relative_to(self.data / 'evidence') or not proof.is_file():
                return False, 'Comprovante de permissão indisponível.'
        if rights.get('video') is not True:
            return False, 'Uso em vídeo não autorizado.'
        if project['usage'] == 'publicidade' and rights.get('advertising') is not True:
            return False, 'Esta licença não libera publicidade.'
        commercial = project['usage'] == 'publicidade' or project['monetized'] or project['sponsored']
        if commercial and rights.get('commercial') is not True:
            return False, 'Esta licença não libera este uso comercial.'
        if rights.get('share_alike'):
            return False, 'Licença com compartilhamento obrigatório precisa de avaliação adicional.'
        return True, 'Permitida para este projeto.'

    def stats(self):
        with self.db() as db:
            assets = [json.loads(r['body']) for r in db.execute('SELECT body FROM assets')]
            downloads = db.execute('SELECT COUNT(*) FROM downloads').fetchone()[0]
        active = [a for a in assets if not a.get('duplicate_of')]
        return {'music': sum(a['kind'] == 'music' for a in active), 'sfx': sum(a['kind'] == 'sfx' for a in active),
                'duplicate_files':len(assets)-len(active),
                'artists': len(set(a['artist'] for a in assets)), 'downloads': downloads,
                'sources': sorted(set(a['source_name'].replace('OpenGameArt / Holizna', 'OpenGameArt') for a in assets))}

    def details(self, asset_id, project_id=None):
        asset = self.asset(asset_id)
        project = self.project(project_id) if project_id else None
        allowed, reason = self.eligible(asset, project)
        asset['eligible'] = allowed
        asset['eligibility_reason'] = reason
        with self.db() as db:
            feedback = db.execute('SELECT value FROM feedback WHERE asset_id=?', (asset_id,)).fetchone()
            saved = db.execute('SELECT body,path FROM downloads WHERE asset_id=?', (asset_id,)).fetchone()
            asset['use_count'] = db.execute('SELECT COUNT(*) FROM uses WHERE asset_id=?', (asset_id,)).fetchone()[0]
        asset['feedback'] = feedback['value'] if feedback else None
        asset['local'] = bool(saved and Path(saved['path']).is_file())
        if saved and asset['local']:
            asset['audio_info'] = json.loads(saved['body'])
            asset['duration'] = asset['audio_info'].get('duration', asset.get('duration'))
        from search_engine import profile
        asset['scene_profile'] = profile(asset)
        return asset

    def search(self, project_id=None, query='', kind='all', credit='all', favorites=False, limit=100,
               *, function=None, no_voice=None, duration_min=None, duration_max=None,
               scene_seconds=None, exclude=None, allow_unknown=False, _snapshot=None):
        from search_engine import interpret, evaluate
        project = self.project(project_id) if project_id else None
        context = self.context_status(project)
        if context['needs_context']:
            return {**context, 'project': project, 'assets': [], 'message': 'Antes de buscar, confirme a finalidade do vídeo.'}
        if kind not in ('all', 'music', 'sfx') or credit not in ('all', 'no_credit'):
            raise ValueError('Filtro inválido.')
        if type(allow_unknown) is not bool:
            raise ValueError('permitir_desconhecidos precisa ser booleano.')
        request = interpret(query, kind, function, no_voice, duration_min, duration_max, scene_seconds, exclude)
        snapshot = _snapshot if _snapshot is not None else self.search_snapshot()
        matches, alternatives = [], []
        for record in snapshot:
            a = dict(record)
            if a.get('duplicate_of') and a.get('feedback') != 'favorite':
                continue
            if not self.eligible(a, project)[0]:
                continue
            if credit == 'no_credit' and a['rights'].get('attribution_required'):
                continue
            if a['feedback'] == 'dislike' or (favorites and a['feedback'] != 'favorite'):
                continue
            result = evaluate(a, request, allow_unknown)
            if result is None:
                continue
            a['scene_match'] = result
            a['score'] = result['score']
            a['match_reason'] = 'Combina com: ' + ', '.join(result['matched']) if result['matched'] else 'Disponível para este projeto.'
            (alternatives if result['missing'] else matches).append(a)
        def order(a):
            return (-a['score'], a['use_count'], a['artist'], a['title'])
        matches.sort(key=order); alternatives.sort(key=order)
        return {'needs_context': False, 'project': project, 'total': len(matches),
                'assets': matches[:max(1, min(int(limit), 500))],
                'alternatives': alternatives[:5], 'interpreted_request': request,
                'search_method': 'Conceitos de cena e requisitos combinados; evidências por metadados, sem análise perceptual do áudio.',
                'message': 'Nenhum candidato atende todos os conceitos. As alternativas mostram o que falta.' if not matches and alternatives else ''}

    def search_snapshot(self):
        """A single database read for the complete search; shared across a scene batch."""
        with self.db() as db:
            feedback = {r['asset_id']: r['value'] for r in db.execute('SELECT * FROM feedback')}
            uses = {r['asset_id']: r['n'] for r in db.execute('SELECT asset_id,COUNT(*) n FROM uses GROUP BY asset_id')}
            saved = {r['asset_id']: r for r in db.execute('SELECT * FROM downloads')}
            assets = [json.loads(r['body']) for r in db.execute('SELECT body FROM assets')]
        for a in assets:
            a['feedback'] = feedback.get(a['id'])
            a['use_count'] = uses.get(a['id'], 0)
            download = saved.get(a['id'])
            a['local'] = bool(download and Path(download['path']).is_file())
            if a['local']:
                a['audio_info'] = json.loads(download['body'])
                a['duration'] = a['audio_info'].get('duration', a.get('duration'))
        return assets

    def search_scenes(self, project_id, scenes, limit=5):
        context = self.context_status(self.project(project_id) if project_id else None)
        if context['needs_context']:
            return {**context, 'scenes': []}
        if not isinstance(scenes, list) or not 1 <= len(scenes) <= 20 or any(not isinstance(s,dict) for s in scenes):
            raise ValueError('Informe de 1 a 20 cenas, cada uma com nome e pedido.')
        allowed = {'nome','pedido','tipo','funcao','sem_voz','duracao_min','duracao_max','duracao_cena','excluir','permitir_desconhecidos'}
        snapshot = self.search_snapshot(); output=[]
        for s in scenes:
            if set(s) - allowed:
                raise ValueError('Campos desconhecidos na cena: ' + ', '.join(sorted(set(s)-allowed)))
            if not s.get('pedido') and not s.get('funcao'):
                raise ValueError('Cada cena precisa de pedido ou função.')
            result = self.search(project_id, s.get('pedido',''), s.get('tipo','all'), limit=limit,
                function=s.get('funcao'), no_voice=s.get('sem_voz'), duration_min=s.get('duracao_min'),
                duration_max=s.get('duracao_max'), scene_seconds=s.get('duracao_cena'), exclude=s.get('excluir'),
                allow_unknown=s.get('permitir_desconhecidos',False), _snapshot=snapshot)
            output.append({'name': s.get('nome') or s.get('pedido') or s['funcao'], **result})
        return {'needs_context': False, 'scenes': output, 'note':'Candidatos por cena. Alternativas são parciais; conferir prévia e pendências antes de entregar.'}

    def feedback(self, asset_id, value):
        self.asset(asset_id)
        if value not in ('favorite', 'dislike', 'clear'):
            raise ValueError('Avaliação inválida.')
        with self.db() as db:
            if value == 'clear':
                db.execute('DELETE FROM feedback WHERE asset_id=?', (asset_id,))
            else:
                db.execute('INSERT INTO feedback VALUES (?,?) ON CONFLICT(asset_id) DO UPDATE SET value=excluded.value', (asset_id, value))
        return {'saved': True, 'value': value}

    def _fetch(self, url, destination):
        parsed = urllib.parse.urlparse(url)
        allowed = {'loyaltyfreakmusic.com', 'www.scottbuckley.com.au', 'kenney.nl', 'opengameart.org'}
        def check(target):
            p = urllib.parse.urlparse(target)
            if p.scheme != 'https' or p.hostname not in allowed or p.username or p.password or p.port not in (None, 443):
                raise ValueError('Endereço de download fora das fontes cadastradas.')
        check(url)
        class Redirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                check(newurl)
                return super().redirect_request(req, fp, code, msg, headers, newurl)
        opener = urllib.request.build_opener(Redirect())
        request = urllib.request.Request(url, headers={'User-Agent': 'TrilhotecaPersonal/0.1 (+private on-demand catalogue)'})
        try:
            with opener.open(request, timeout=45) as response, destination.open('wb') as out:
                length = int(response.headers.get('Content-Length', '0'))
                if length > MAX_BYTES:
                    raise ValueError('Arquivo excede o limite de 250 MB desta versão.')
                total = 0
                while chunk := response.read(1024 * 128):
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise ValueError('Arquivo excede o limite de 250 MB desta versão.')
                    out.write(chunk)
            if not destination.stat().st_size:
                raise ValueError('A fonte devolveu um arquivo vazio.')
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    def _audio_info(self, path):
        with path.open('rb') as source:
            magic = source.read(16)
        if not (magic.startswith((b'ID3', b'RIFF', b'OggS', b'fLaC')) or (magic[:1] == b'\xff' and len(magic) > 1 and magic[1] & 224 == 224)):
            raise ValueError('O download não parece ser um arquivo de áudio válido.')
        probe = shutil.which('ffprobe')
        if not probe:
            probe = next((str(p) for p in (Path('/opt/homebrew/bin/ffprobe'), Path('/usr/local/bin/ffprobe')) if p.is_file()), None)
        if not probe:
            return {'validation': 'header', 'size': path.stat().st_size}
        r = subprocess.run([probe, '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)], capture_output=True, text=True, timeout=20)
        if r.returncode:
            raise ValueError('O arquivo baixado não passou pela leitura de áudio.')
        info = json.loads(r.stdout)
        streams = [s for s in info['streams'] if s.get('codec_type') == 'audio']
        if not streams:
            raise ValueError('O arquivo não possui áudio.')
        s = streams[0]
        return {'validation': 'ffprobe', 'duration': float(info['format'].get('duration', 0)),
                'sample_rate': int(s.get('sample_rate', 0)), 'channels': s.get('channels'),
                'codec': s.get('codec_name'), 'size': path.stat().st_size,
                'bit_rate': int(info['format'].get('bit_rate', 0))}

    def _acquire(self, asset):
        aid = asset['id']
        with LOCK_GUARD:
            lock = LOCKS.setdefault(aid, threading.Lock())
        with lock:
            with self.db() as db:
                saved = db.execute('SELECT * FROM downloads WHERE asset_id=?', (aid,)).fetchone()
            if saved:
                path = Path(saved['path'])
                if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == saved['sha256']:
                    return path, saved['sha256'], json.loads(saved['body'])
            cache = self.data / 'cache'
            cache.mkdir(exist_ok=True)
            dest = cache / (aid + asset.get('extension', '.mp3'))
            temporary = cache / (aid + '.' + uuid.uuid4().hex + '.part')
            try:
                if asset.get('archive_member'):
                    url = asset['download_url']
                    bundle_id = hashlib.sha256(url.encode()).hexdigest()
                    with LOCK_GUARD:
                        bundle_lock = LOCKS.setdefault(bundle_id, threading.Lock())
                    with bundle_lock:
                        bundle = cache / (bundle_id + '.zip')
                        if bundle.exists() and not zipfile.is_zipfile(bundle):
                            bundle.unlink()
                        if not bundle.exists():
                            bt = cache / (bundle_id + '.' + uuid.uuid4().hex + '.part')
                            try:
                                self._fetch(url, bt)
                                if not zipfile.is_zipfile(bt):
                                    raise ValueError('O pacote recebido não é um ZIP válido.')
                                bt.replace(bundle)
                            finally:
                                bt.unlink(missing_ok=True)
                    with zipfile.ZipFile(bundle) as z:
                        member = z.getinfo(asset['archive_member'])
                        parts = Path(member.filename).parts
                        if Path(member.filename).is_absolute() or '..' in parts or member.file_size > MAX_BYTES or (member.external_attr >> 16) & 0o170000 == 0o120000:
                            raise ValueError('Arquivo inválido dentro do pacote.')
                        with z.open(member) as src, temporary.open('wb') as out:
                            shutil.copyfileobj(src, out)
                else:
                    self._fetch(asset['download_url'], temporary)
                audio = self._audio_info(temporary)
                digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
                temporary.replace(dest)
                with self.db() as db:
                    db.execute('INSERT INTO downloads VALUES (?,?,?,?) ON CONFLICT(asset_id) DO UPDATE SET path=excluded.path,sha256=excluded.sha256,body=excluded.body',
                               (aid, str(dest), digest, json.dumps(audio)))
                return dest, digest, audio
            finally:
                temporary.unlink(missing_ok=True)

    def preview(self, asset_id, project_id):
        a = self.asset(asset_id)
        ok, reason = self.eligible(a, self.project(project_id))
        if not ok:
            raise ValueError(reason)
        path, digest, info = self._acquire(a)
        return {'asset_id': asset_id, 'path': str(path), 'sha256': digest, 'audio_info': info,
                'note': 'Prévia no cache local; a entrega ocorre somente ao escolher Baixar selecionadas.'}

    def deliver(self, asset_ids, project_id, assets_dir=None):
        project = self.project(project_id)
        context = self.context_status(project)
        if context['needs_context']:
            return {**context, 'message': 'Confirme a finalidade antes do download.'}
        if not isinstance(asset_ids, list) or not 1 <= len(asset_ids) <= 50:
            raise ValueError('Selecione de 1 a 50 arquivos.')
        records = [self.asset(aid) for aid in dict.fromkeys(asset_ids)]
        for a in records:
            ok, reason = self.eligible(a, project)
            if not ok:
                raise ValueError(a['title'] + ': ' + reason)
        parent = Path(assets_dir).expanduser().resolve() if assets_dir else self.root / 'entregas' / (slug(project['name']) + '-' + project['id'][:8])
        if parent == Path('/') or parent == Path.home():
            raise ValueError('Escolha uma pasta específica de assets.')
        parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
        delivery = parent / ('trilhoteca-' + stamp)
        staged = parent / ('.trilhoteca-' + uuid.uuid4().hex + '.part')
        staged.mkdir()
        manifest = {'version': 1, 'created': now(), 'project': project, 'assets': []}
        try:
            credits = []
            for a in records:
                path, digest, audio = self._acquire(a)
                filename = slug(a['artist'] + '-' + a['title']) + '-' + a['id'][:10] + a.get('extension', '.mp3')
                shutil.copy2(path, staged / filename)
                item = {'id': a['id'], 'title': a['title'], 'artist': a['artist'], 'file': filename,
                        'source_url': a['source_url'], 'sha256': digest, 'audio_info': audio, 'rights': a['rights']}
                manifest['assets'].append(item)
                credits.append(a['rights'].get('credit_text') or f"{a['title']} — {a['artist']}\n{a['source_url']}\nCC0; crédito opcional.")
                for evidence in a['rights']['evidence']:
                    target = staged / 'licencas' / Path(evidence).name
                    target.parent.mkdir(exist_ok=True)
                    shutil.copy2(self.root / evidence, target)
            (staged / 'CREDITOS.txt').write_text('\n\n'.join(credits) + '\n', encoding='utf-8')
            (staged / 'MANIFESTO.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
            (staged / 'LEIA-ME.txt').write_text('Arquivos originais, sem conversão.\nCREDITOS.txt contém os créditos de publicação.\nMANIFESTO.json registra finalidade, origem, licença e integridade.\nlicencas/ contém os comprovantes capturados na data da coleta.\nA escuta e a escolha artística ficam com o editor.\n', encoding='utf-8')
            staged.rename(delivery)
            with self.db() as db:
                for a in records:
                    db.execute('INSERT OR IGNORE INTO uses VALUES (?,?,?)', (project_id, a['id'], now()))
        except Exception:
            shutil.rmtree(staged, ignore_errors=True)
            raise
        return {'needs_context': False, 'delivery_path': str(delivery), 'count': len(records),
                'files': [str(delivery / a['file']) for a in manifest['assets']], 'credits_path': str(delivery / 'CREDITOS.txt')}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['stats', 'search'])
    parser.add_argument('--project-id')
    parser.add_argument('--query', default='')
    args = parser.parse_args()
    lib = Library()
    print(json.dumps(lib.stats() if args.command == 'stats' else lib.search(args.project_id, args.query), ensure_ascii=False, indent=2))
