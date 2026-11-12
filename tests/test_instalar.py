import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer', PACKAGE / 'instalar.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallationTests(unittest.TestCase):
    def test_codex_preserves_other_servers_and_settings(self):
        source = 'model = "existing"\n\n[mcp_servers.other]\ncommand = "other"\n[mcp_servers."trilhoteca"]\ncommand = "old"\n[mcp_servers."trilhoteca".env]\nOLD = "value"\n[profiles.personal]\nmodel = "personal"\n'
        result = installer.codex_config(source, Path('/a path/App'))
        cfg = tomllib.loads(result)
        self.assertEqual(cfg['model'], 'existing')
        self.assertEqual(cfg['mcp_servers']['other']['command'], 'other')
        self.assertEqual(cfg['profiles']['personal']['model'], 'personal')
        self.assertEqual(cfg['mcp_servers']['trilhoteca']['command'], '/a path/App/.venv/bin/python')
        self.assertNotIn('env', cfg['mcp_servers']['trilhoteca'])
        self.assertEqual(result, installer.codex_config(result, Path('/a path/App')))

    def test_invalid_other_configuration_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / '.codex').mkdir()
            config = home / '.codex/config.toml'
            config.write_text('broken = [')
            with self.assertRaises(tomllib.TOMLDecodeError):
                installer.configure(home, home / '.codex', home / 'app', ['codex', 'claude'])
            self.assertEqual(config.read_text(), 'broken = [')
            self.assertFalse((home / '.claude.json').exists())

    def test_claude_preserves_projects_and_other_servers_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            original = {'projects': {'/project': {'allowedTools': ['tool']}}, 'mcpServers': {'other': {'command': 'other'}}, 'preference': True}
            path = home / '.claude.json'
            path.write_text(json.dumps(original))
            installer.configure(home, home / '.codex', home / 'app', ['claude', 'codex'])
            cfg = json.loads(path.read_text())
            self.assertEqual(cfg['projects'], original['projects'])
            self.assertEqual(cfg['mcpServers']['other'], original['mcpServers']['other'])
            self.assertTrue(cfg['preference'])
            self.assertEqual(len(list(home.glob('.claude.json.backup-*'))), 1)
            installer.configure(home, home / '.codex', home / 'app', ['claude', 'codex'])
            self.assertEqual(len(list(home.glob('.claude.json.backup-*'))), 1)
            self.assertTrue((home / '.agents/skills/trilhoteca/SKILL.md').is_file())
            self.assertTrue((home / '.claude/skills/trilhoteca/PARA_O_EDITOR.md').is_file())

    def test_update_preserves_catalog_projects_favorites_and_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'app'
            installer.copy_runtime(target)
            sys.path.insert(0, str(target))
            try:
                from library import Library
                lib = Library(target)
                project = lib.set_project('Existing user project', 'proprio', True, False)['project']
                catalog = json.loads((target / 'data/catalog.json').read_text())
                first = catalog['assets'][0]['id']
                lib.feedback(first, 'favorite')
                extra = dict(catalog['assets'][0], id='custom-item')
                catalog['assets'].append(extra)
                (target / 'data/catalog.json').write_text(json.dumps(catalog))
                cache = target / 'data/cache/preserved.txt'
                cache.parent.mkdir(parents=True)
                cache.write_text('user cache')
                installer.copy_runtime(target)
                refreshed = Library(target)
                self.assertEqual(refreshed.project(project['id'])['name'], 'Existing user project')
                self.assertEqual(refreshed.details(first, project['id'])['feedback'], 'favorite')
                self.assertEqual(refreshed.asset('custom-item')['id'], 'custom-item')
                self.assertEqual(cache.read_text(), 'user cache')
            finally:
                sys.path.pop(0)

    def test_integrity_detects_changed_code(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory)
            (package / 'code.py').write_text('modified')
            (package / 'MANIFESTO_SHA256.json').write_text(json.dumps({'files': {'code.py': 'invalid'}}))
            with self.assertRaises(ValueError):
                installer.verify_package(package)


if __name__ == '__main__':
    unittest.main()
