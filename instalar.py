#!/usr/bin/env python3
"""Install a self-contained runtime and preserve the recipient's other settings."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib

PACKAGE = Path(__file__).resolve().parent


def verify_package(package=PACKAGE):
    manifest = json.loads((package / 'MANIFESTO_SHA256.json').read_text(encoding='utf-8'))
    for name, expected in manifest['files'].items():
        file = (package / name).resolve()
        if not file.is_relative_to(package.resolve()) or not file.is_file():
            raise ValueError(f'Arquivo ausente ou inválido: {name}')
        if hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Arquivo alterado ou incompleto: {name}. Baixe novamente o pacote.')
    return manifest


def save(path, content):
    """Back up changed files, preserve permissions, and replace atomically."""
    path = Path(path)
    data = content.encode('utf-8') if isinstance(content, str) else content
    previous = path.read_bytes() if path.exists() else None
    if previous == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if previous is not None:
        backup = path.with_name(path.name + f'.backup-{time.time_ns()}')
        shutil.copy2(path, backup)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        if path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def codex_config(text, target):
    parsed = tomllib.loads(text)
    # Remove only this server's table and sub-tables; retain all other text/comments.
    lines = text.splitlines(keepends=True)
    output, skip, found = [], False, False
    for line in lines:
        if re.match(r'^\s*\[', line):
            header = line.split('#', 1)[0].strip()
            try:
                table = tomllib.loads(header + '\n__trilhoteca_marker__ = true\n')
                skip = isinstance(table.get('mcp_servers'), dict) and 'trilhoteca' in table['mcp_servers']
            except tomllib.TOMLDecodeError:
                skip = False
            found = found or skip
        if not skip:
            output.append(line)
    if 'trilhoteca' in parsed.get('mcp_servers', {}) and not found:
        raise ValueError('A configuração Codex usa Trilhoteca em tabela inline. A IA deve migrar somente essa entrada, preservando as demais.')
    command = str(target / '.venv/bin/python')
    result = ''.join(output).rstrip() + '\n\n[mcp_servers.trilhoteca]\n'
    result += 'command = ' + json.dumps(command, ensure_ascii=False) + '\n'
    result += 'args = [' + json.dumps(str(target / 'mcp_server.py'), ensure_ascii=False) + ']\n'
    result += 'cwd = ' + json.dumps(str(target), ensure_ascii=False) + '\n'
    result += 'startup_timeout_sec = 60\ntool_timeout_sec = 300\n'
    tomllib.loads(result)
    return result


def configure(home, codex_home, target, clients, package=PACKAGE):
    writes = []
    if 'codex' in clients:
        path = codex_home / 'config.toml'
        writes.append((path, codex_config(path.read_text(encoding='utf-8') if path.exists() else '', target)))
    if 'claude' in clients:
        path = home / '.claude.json'
        config = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        config.setdefault('mcpServers', {})['trilhoteca'] = {
            'type': 'stdio', 'command': str(target / '.venv/bin/python'),
            'args': [str(target / 'mcp_server.py')],
        }
        writes.append((path, json.dumps(config, ensure_ascii=False, indent=2) + '\n'))
    # Parse both configurations before writing either one.
    for path, content in writes:
        save(path, content)
    for client in clients:
        base = home / ('.agents' if client == 'codex' else '.claude') / 'skills' / 'trilhoteca'
        save(base / 'SKILL.md', (package / 'skill/SKILL.md').read_text(encoding='utf-8'))
        save(base / 'PARA_O_EDITOR.md', (package / 'app/PARA_O_EDITOR.md').read_text(encoding='utf-8'))


def copy_runtime(target, package=PACKAGE):
    source = package / 'app'
    incoming = json.loads((source / 'data/catalog.json').read_text(encoding='utf-8'))
    existing = target / 'data/catalog.json'
    if existing.exists():
        current = json.loads(existing.read_text(encoding='utf-8'))
        assets = {a['id']: a for a in current['assets']}
        assets.update({a['id']: a for a in incoming['assets']})
        incoming['assets'] = list(assets.values())
    for file in source.rglob('*'):
        if not file.is_file():
            continue
        relative = file.relative_to(source)
        if relative.as_posix() == 'data/catalog.json':
            save(target / relative, json.dumps(incoming, ensure_ascii=False, indent=2) + '\n')
        elif relative.as_posix() == 'data/sources.json' and (target / relative).exists():
            current = json.loads((target / relative).read_text(encoding='utf-8'))
            added = json.loads(file.read_text(encoding='utf-8'))
            records = {s['url']: s for s in added}
            records.update({s['url']: s for s in current})
            save(target / relative, json.dumps(list(records.values()), ensure_ascii=False, indent=2) + '\n')
        else:
            save(target / relative, file.read_bytes())
    save(target / 'verificar.py', (package / 'verificar.py').read_bytes())
    launcher = '#!/bin/sh\ncd -- ' + shell_quote(str(target)) + '\nexec ' + shell_quote(str(target / '.venv/bin/python')) + ' ' + shell_quote(str(target / 'launch.py')) + '\n'
    save(target / 'Abrir Trilhoteca.command', launcher)
    (target / 'Abrir Trilhoteca.command').chmod(0o755)


def shell_quote(value):
    return "'" + value.replace("'", "'\"'\"'") + "'"


def default_target(home):
    if sys.platform == 'darwin':
        return home / 'Library/Application Support/Trilhoteca'
    return Path(os.environ.get('XDG_DATA_HOME', str(home / '.local/share'))) / 'trilhoteca'


def main():
    parser = argparse.ArgumentParser(description='Instalar Trilhoteca no Claude Code e/ou Codex.')
    parser.add_argument('--cliente', choices=['ambos', 'claude', 'codex'], default='ambos')
    parser.add_argument('--destino', type=Path)
    parser.add_argument('--config-home', type=Path, help='Somente para testes isolados: não altera a conta real.')
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error('Use Python 3.11 ou mais recente.')
    if sys.platform == 'win32':
        parser.error('Este pacote requer macOS ou Linux. Windows nativo ainda não foi validado.')
    manifest = verify_package()
    home = (args.config_home or Path.home()).resolve()
    codex_home = home / '.codex' if args.config_home else Path(os.environ.get('CODEX_HOME', str(home / '.codex'))).expanduser().resolve()
    target = (args.destino or default_target(home)).expanduser().resolve()
    if target == PACKAGE or target.is_relative_to(PACKAGE):
        parser.error('Escolha uma pasta permanente fora da pasta baixada.')
    clients = ['claude', 'codex'] if args.cliente == 'ambos' else [args.cliente]
    # Validate settings early; no mutation of broken or unusual global configuration.
    if 'codex' in clients:
        cfg = codex_home / 'config.toml'
        codex_config(cfg.read_text(encoding='utf-8') if cfg.exists() else '', target)
    if 'claude' in clients and (home / '.claude.json').exists():
        json.loads((home / '.claude.json').read_text(encoding='utf-8'))
    print('Conferência do pacote OK. Preparando instalação permanente...', flush=True)
    copy_runtime(target)
    venv = target / '.venv'
    if not (venv / 'bin/python').exists():
        subprocess.run([sys.executable, '-m', 'venv', str(venv)], check=True)
    python = venv / 'bin/python'
    subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(target / 'requirements.txt')], check=True)
    subprocess.run([str(python), str(target / 'verificar.py')], cwd=target, check=True, timeout=90)
    configure(home, codex_home, target, clients)
    report = {'release': manifest['release'], 'installed': str(target), 'clients': clients, 'verification': 'MCP conectado; catálogo e gabarito conferidos'}
    save(target / 'INSTALACAO.json', json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Instalação concluída. Abra uma nova sessão do Claude Code/Codex para carregar Trilhoteca.')
    print('Pasta permanente:', target)
    print('Painel: abra Abrir Trilhoteca.command nessa pasta, ou peça à IA para abrir launch.py com o Python da instalação.')


if __name__ == '__main__':
    main()
