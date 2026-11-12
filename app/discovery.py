"""Persistent local discovery jobs, shared by panel and MCP. No paid API."""
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from library import Library, now, catalog_lock

ACTIVE = ('starting', 'running')


class DiscoveryJobs:
    def __init__(self, lib):
        self.lib = lib
        with lib.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS discovery_jobs(id TEXT PRIMARY KEY, status TEXT NOT NULL, body TEXT NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS one_discovery_job ON discovery_jobs((1)) WHERE status IN ('starting','running');
                CREATE TABLE IF NOT EXISTS discovery_seen(url TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS discovery_cursors(source TEXT PRIMARY KEY, page INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS source_candidates(domain TEXT PRIMARY KEY, body TEXT NOT NULL);
            ''')

    def update(self, job_id, **changes):
        with self.lib.db() as db:
            row = db.execute('SELECT body FROM discovery_jobs WHERE id=?', (job_id,)).fetchone()
            if not row:
                raise ValueError('Busca não encontrada.')
            job = json.loads(row['body']); job.update(changes); job['updated'] = now()
            db.execute('UPDATE discovery_jobs SET status=?,body=? WHERE id=?', (job['status'], json.dumps(job, ensure_ascii=False), job_id))
        return job

    def status(self, job_id=None):
        with self.lib.db() as db:
            row = db.execute('SELECT body FROM discovery_jobs '+('WHERE id=?' if job_id else 'ORDER BY rowid DESC LIMIT 1'), (job_id,) if job_id else ()).fetchone()
        job = json.loads(row['body']) if row else None
        if job and job['status'] in ACTIVE and job.get('pid'):
            try:
                try:
                    finished, _ = os.waitpid(job['pid'], os.WNOHANG)
                except ChildProcessError:
                    finished = 0
                if finished:
                    raise ProcessLookupError()
                os.kill(job['pid'], 0)
            except ProcessLookupError:
                job = self.update(job['id'], status='interrupted', message='A busca foi interrompida. O que já entrou na biblioteca foi preservado; você pode iniciar outra busca.')
        if job and job['status'] == 'starting' and time.time() - job.get('started_epoch', 0) > 60:
            job = self.update(job['id'], status='interrupted', message='A busca não iniciou. Tente novamente.')
        return job

    def candidates(self):
        with self.lib.db() as db:
            return [json.loads(r['body']) for r in db.execute('SELECT body FROM source_candidates ORDER BY rowid DESC')]

    def start(self, mode='tracks', pages=2):
        if mode not in ('tracks', 'music', 'sfx', 'sources'):
            raise ValueError('Tipo de busca inválido.')
        if type(pages) is not int or not 1 <= pages <= 12:
            raise ValueError('A busca aceita de 1 a 12 páginas por fonte.')
        self.status()
        job = {'id': uuid.uuid4().hex, 'mode': mode, 'status': 'starting', 'created': now(),
               'updated': now(), 'started_epoch': time.time(), 'pages': pages,
               'message': 'Preparando a busca…', 'checked': 0, 'added': 0, 'skipped': 0, 'errors': [], 'pid': None}
        with self.lib.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT body FROM discovery_jobs WHERE status IN ('starting','running')").fetchone()
            if row:
                return {'started': False, 'job': json.loads(row['body']), 'message': 'Já há uma busca em andamento.'}
            db.execute('INSERT INTO discovery_jobs VALUES (?,?,?)', (job['id'], job['status'], json.dumps(job)))
        python = self.lib.root / '.venv/bin/python'
        try:
            with (self.lib.data / 'discovery.log').open('ab') as log:
                p = subprocess.Popen([str(python if python.is_file() else Path(sys.executable)),
                    str(self.lib.root / 'scripts/discover.py'), '--job-id', job['id']],
                    cwd=self.lib.root, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
            job = self.update(job['id'], pid=p.pid)
        except Exception:
            self.update(job['id'], status='failed', message='Não foi possível iniciar a busca. Confira a instalação das dependências.')
            raise
        return {'started': True, 'job': job}


def merge_assets(lib, records):
    with catalog_lock(lib.root):
        return _merge_assets(lib, records)


def _merge_assets(lib, records):
    """Add a validated batch, preserving old entries and all user data."""
    target = lib.data / 'catalog.json'
    catalog = json.loads(target.read_text()) if target.exists() else {'version': 1, 'assets': []}
    unique = {a['id']: a for a in catalog['assets']}
    # The identical source recording exposed twice is kept only once.
    recordings = {(a['download_url'], a.get('archive_member')) for a in unique.values()}
    hashes = {a['indexed_sha256'] for a in unique.values() if a.get('indexed_sha256')}
    added = []
    for a in records:
        key = (a['download_url'], a.get('archive_member'))
        if a['id'] in unique or key in recordings or a.get('indexed_sha256') in hashes:
            continue
        unique[a['id']] = a; recordings.add(key); added.append(a)
        if a.get('indexed_sha256'):
            hashes.add(a['indexed_sha256'])
    if not added:
        return 0
    catalog.update(assets=list(unique.values()), updated=now())
    temporary = target.with_suffix('.discovery.part')
    temporary.write_text(json.dumps(catalog, ensure_ascii=False, indent=2))
    temporary.replace(target)
    with lib.db() as db:
        for a in added:
            db.execute('INSERT INTO assets VALUES (?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body', (a['id'], json.dumps(a, ensure_ascii=False)))
    return len(added)
