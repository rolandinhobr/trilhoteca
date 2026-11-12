"""MCP stdio interface using the official Python SDK (tested 1.30.0)."""
from mcp.server.fastmcp import FastMCP
from library import Library
from discovery import DiscoveryJobs

lib = Library()
discovery = DiscoveryJobs(lib)
mcp = FastMCP('Trilhoteca', instructions='Biblioteca privada de música e SFX para edição. Antes de buscar ou baixar, confirme publicidade ou conteúdo próprio, monetização e patrocínio. Nunca presuma as respostas. Crie o projeto com definir_projeto e reutilize seu ID até o contexto mudar. Para várias cenas use buscar_por_cena. A busca combina requisitos e funções por evidências de metadados; não é análise perceptual. assets contém candidatos, alternatives contém opções PARCIAIS: informe missing e pending e nunca trate essas alternativas como atendendo ao pedido. Campos de voz/duração desconhecidos não satisfazem filtros estritos; permitir_desconhecidos é uma escolha explícita para pesquisa exploratória. Confira prévias antes da escolha artística. Entregue créditos e licenças junto com o áudio.')


@mcp.tool()
def listar_projetos() -> list[dict]:
    """Consulta os projetos e as finalidades já respondidas, sem criar valores padrão."""
    return lib.projects()


@mcp.tool()
def definir_projeto(nome: str, uso: str | None = None, monetizado: bool | None = None,
                    patrocinado: bool | None = None, projeto_id: str | None = None) -> dict:
    """Salva o gabarito. uso=publicidade ou proprio. Campos ausentes geram perguntas; não assuma respostas."""
    return lib.set_project(nome, uso, monetizado, patrocinado, projeto_id)


@mcp.tool()
def buscar_audio(projeto_id: str | None = None, pedido: str = '', tipo: str = 'all',
                 sem_credito_obrigatorio: bool = False, favoritos: bool = False, limite: int = 30,
                 funcao: str | None = None, sem_voz: bool | None = None,
                 duracao_min: float | None = None, duracao_max: float | None = None,
                 duracao_cena: float | None = None, excluir: list[str] | None = None,
                 permitir_desconhecidos: bool = False) -> dict:
    """Busca música/SFX combinando requisitos. tipo=all/music/sfx; durações em segundos. Consulte scene_match: matched/evidence, missing, pending. alternatives são PARCIAIS. Sem contexto retorna perguntas. sem_voz=True exige fonte confirmada; False não restringe voz. duracao_cena pede música suficiente ou loop declarado, sem recortar áudio."""
    return lib.search(projeto_id, pedido, tipo, 'no_credit' if sem_credito_obrigatorio else 'all', favoritos, limite,
        function=funcao, no_voice=sem_voz, duration_min=duracao_min, duration_max=duracao_max,
        scene_seconds=duracao_cena, exclude=excluir, allow_unknown=permitir_desconhecidos)


@mcp.tool()
def listar_funcoes_de_cena() -> list[dict]:
    """Funções editoriais aceitas (narração, revelação, humor, transição, impactos, ambiente, foley etc.). Sugestões por metadados, não garantia artística."""
    from search_engine import functions
    return functions()


@mcp.tool()
def buscar_por_cena(projeto_id: str | None, cenas: list[dict], limite_por_cena: int = 5) -> dict:
    """Busca até 20 cenas em uma chamada. Cada cena aceita nome, pedido, tipo(all/music/sfx), funcao, sem_voz, duracao_min/max/cena em segundos, excluir(lista) e permitir_desconhecidos(bool, padrão False). Devolve candidatos e alternativas parciais separados por cena. Ex.: [{"nome":"Narração","pedido":"piano calmo","tipo":"music","funcao":"narracao"},{"nome":"Corte","pedido":"whoosh","tipo":"sfx","duracao_max":2}]. Não baixa nada."""
    return lib.search_scenes(projeto_id, cenas, limite_por_cena)


@mcp.tool()
def consultar_audio(audio_id: str, projeto_id: str | None = None) -> dict:
    """Mostra origem, licença, crédito, características declaradas e medições disponíveis."""
    return lib.details(audio_id, projeto_id)


@mcp.tool()
def preparar_previa(audio_id: str, projeto_id: str) -> dict:
    """Baixa apenas o áudio escolhido (ou seu pacote de origem) no cache e retorna o caminho para ouvir."""
    return lib.preview(audio_id, projeto_id)


@mcp.tool()
def baixar_selecionadas(audio_ids: list[str], projeto_id: str, pasta_assets: str | None = None) -> dict:
    """Entrega os originais, créditos, licenças e manifesto na pasta de assets ou nas entregas locais."""
    return lib.deliver(audio_ids, projeto_id, pasta_assets)


@mcp.tool()
def avaliar_audio(audio_id: str, avaliacao: str) -> dict:
    """avaliacao=favorite/dislike/clear. Favoritos sobem na busca e rejeitados deixam de aparecer."""
    return lib.feedback(audio_id, avaliacao)


@mcp.tool()
def resumo_biblioteca() -> dict:
    """Quantidade de músicas, efeitos, fontes e arquivos preparados localmente."""
    return lib.stats()


@mcp.tool()
def buscar_novidades(somente_sfx: bool = False, somente_musicas: bool = False) -> dict:
    """Amplia músicas e efeitos, ou apenas o tipo escolhido. Confere licenças e lê manifestos de álbuns sem transferir as músicas; arquivos permanecem sob demanda. Pacotes de efeitos são inspecionados para identificar membros/durações."""
    if somente_sfx and somente_musicas:
        raise ValueError('Escolha somente músicas, somente SFX ou ambos.')
    return discovery.start('sfx' if somente_sfx else 'music' if somente_musicas else 'tracks')


@mcp.tool()
def buscar_novas_fontes() -> dict:
    """Busca externa mais demorada em diretórios e sites citados pelos artistas. Retorna fontes para revisão, sem presumir licença ou importar áudios."""
    return discovery.start('sources')


@mcp.tool()
def consultar_busca() -> dict:
    """Consulta andamento e resultados da expansão. Chamadas espaçadas; novas fontes precisam de verificação e integração."""
    return {'job': discovery.status(), 'sources': discovery.candidates(), 'stats': lib.stats()}


if __name__ == '__main__':
    mcp.run(transport='stdio')
