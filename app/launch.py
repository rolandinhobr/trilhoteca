import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:17846'


def ready():
    try:
        with urllib.request.urlopen(URL + '/api/meta', timeout=2) as response:
            return json.load(response).get('app') == 'trilhoteca'
    except (OSError, ValueError):
        return False


if not ready():
    (ROOT / 'data').mkdir(exist_ok=True)
    with (ROOT / 'data/panel.log').open('ab') as log:
        process = subprocess.Popen([sys.executable, str(ROOT / 'server.py')], cwd=ROOT,
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    for _ in range(40):
        if ready():
            break
        if process.poll() is not None:
            raise SystemExit('Não foi possível abrir o painel. Consulte data/panel.log.')
        time.sleep(.2)
if not ready():
    raise SystemExit('O painel não respondeu. Consulte data/panel.log.')
webbrowser.open(URL)
print('Trilhoteca aberta. Você pode fechar esta janela.')
