# Instalar a Trilhoteca para este usuário

O usuário pediu uma instalação local e global para pesquisar música e SFX em qualquer projeto do Claude Code/Codex. Este pacote contém o código, catálogo, comprovantes das fontes e instalador. Não exige credenciais.

Localize `instalar.py` ao lado deste documento. Se o usuário só deu o link do repositório, clone-o primeiro numa pasta permanente. Confira o sistema e use um Python **3.11 ou posterior**. Suporte: macOS e Linux; Windows nativo não suportado. Se só houver acesso a uma máquina na nuvem, explique que a instalação precisa ser feita pelo Claude Code/Codex no computador que editará os vídeos.

Execute com o diretório deste pacote como diretório de trabalho:

```sh
python3 instalar.py
```

Se houver apenas um dos aplicativos, pode usar `--cliente claude` ou `--cliente codex`. A instalação padrão configura ambos para que o outro possa ser usado depois. Não altere os parâmetros `--destino` e `--config-home` sem necessidade; o último é reservado a testes isolados. Se faltar Python ou acesso à internet, resolva a dependência dentro da autorização do usuário, sem substituir arquivos pessoais ou solicitar segredos. Python oficial: https://www.python.org/downloads/ . Em Linux pode ser necessário o pacote `python3-venv` do sistema.

O instalador confere hashes, copia o aplicativo para uma pasta permanente, cria um ambiente com dependências, faz uma conexão MCP real e depois adiciona apenas `trilhoteca` às configurações globais. Em macOS, o aplicativo fica em `~/Library/Application Support/Trilhoteca`; em Linux, em `$XDG_DATA_HOME/trilhoteca` ou `~/.local/share/trilhoteca`. Projetos, favoritos, cache e catálogo de uma instalação existente são preservados. Arquivos alterados recebem backups ao lado do original.

Claude Code: entrada em `~/.claude.json` (escopo de usuário) e skill em `~/.claude/skills/trilhoteca`. Codex: entrada em `~/.codex/config.toml` (ou `$CODEX_HOME/config.toml`) e skill em `~/.agents/skills/trilhoteca`. Configurações locais de um projeto podem ter precedência; se houver conflito, identifique-o e ajuste somente o servidor Trilhoteca com a autorização existente. O pacote não configura automaticamente o aplicativo **Claude Desktop**; use Claude Code.

Depois do término, confirme os caminhos registrados e a preservação dos demais servidores. Execute `verificar.py` da pasta instalada com o Python do ambiente instalado caso a verificação tenha sido interrompida. A verificação espera pelo menos 5.677 músicas, 4.389 SFX, 13 ferramentas, comprovantes completos e perguntas de finalidade quando o contexto está ausente; não cria projetos de teste nem baixa áudio.

Peça ao usuário abrir uma **nova sessão** do aplicativo para carregar a configuração. Nessa sessão, confira `resumo_biblioteca` e `listar_funcoes_de_cena`. Antes de buscar áudio, obtenha o gabarito real: publicidade/conteúdo próprio, monetizado sim/não, patrocinado sim/não. Crie o projeto por `definir_projeto` e busque uma música e um SFX com `buscar_por_cena`. Não invente respostas para finalizar a instalação. Diga separadamente o que o instalador verificou e o que foi conferido pelo aplicativo após reinício.

Para abrir o painel, execute `launch.py` com o Python do ambiente instalado. Ele abre http://127.0.0.1:17846 . Não inicie outro painel se já houver uma Trilhoteca ativa nessa porta. O acesso MCP funciona sem abrir o painel.

Referências oficiais verificadas em 30/09/2026: [Codex MCP](https://developers.openai.com/codex/mcp/), [Codex skills](https://developers.openai.com/codex/skills/), [Claude Code MCP](https://code.claude.com/docs/en/mcp), [Claude Code skills](https://code.claude.com/docs/en/skills).
