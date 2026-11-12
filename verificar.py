"""Verify actual stdio MCP access without creating user projects or downloading audio."""
import asyncio
import json
from pathlib import Path
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent


def payload(result):
    if result.isError:
        raise RuntimeError(str(result.content))
    value = result.structuredContent
    return value if value is not None else json.loads(result.content[0].text)


async def main():
    parameters = StdioServerParameters(command=sys.executable, args=[str(ROOT / 'mcp_server.py')], cwd=str(ROOT))
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            required = {'buscar_audio', 'buscar_por_cena', 'preparar_previa', 'baixar_selecionadas', 'buscar_novidades', 'buscar_novas_fontes'}
            if not required <= tools:
                raise RuntimeError('Interface MCP incompleta.')
            stats = payload(await session.call_tool('resumo_biblioteca', {}))
            if stats['music'] < 5677 or stats['sfx'] < 4389:
                raise RuntimeError('Catálogo inicial incompleto.')
            context = payload(await session.call_tool('buscar_audio', {'pedido': 'piano calmo'}))
            if not context.get('needs_context') or len(context.get('questions', [])) != 3:
                raise RuntimeError('Gabarito de finalidade não está funcionando.')
            from library import Library
            lib = Library(ROOT)
            catalog = json.loads((ROOT / 'data/catalog.json').read_text(encoding='utf-8'))
            for asset in catalog['assets']:
                if asset.get('duplicate_of'):
                    continue
                allowed, reason = lib.eligible(asset, {'usage': 'publicidade', 'monetized': True, 'sponsored': True})
                if not allowed:
                    raise RuntimeError(f"Comprovante inicial inválido: {asset['id']}: {reason}")
            print(json.dumps({'mcp': 'OK', 'tools': len(tools), 'stats': stats, 'gabarito': 'OK', 'license_evidence': 'OK'}, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
