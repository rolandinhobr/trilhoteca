# Trilhoteca

Música e efeitos sonoros gratuitos (CC0 e CC BY) para edição, pesquisáveis pelo Claude Code e pelo Codex.

## 🤖 Para a IA que recebeu este link

O usuário quer instalar a Trilhoteca no computador dele. Faça assim, sem pedir mais nada:

1. Clone este repositório numa pasta permanente (ex.: `~/Trilhoteca`) com `git clone` usando a URL deste repositório.
2. Leia `INSTALAR_PARA_IA.md` na pasta clonada e siga-o: ele instala o MCP e a skill globalmente no Claude Code e no Codex, preservando as configurações existentes.
3. Confirme o funcionamento do MCP, do catálogo e das buscas de música e SFX, e avise o usuário para abrir uma nova sessão.

Requisitos: macOS ou Linux, Python 3.11+, git e internet. Sem chave de API nem login. Windows nativo não é suportado. Se você roda só na nuvem e não alcança o computador do usuário, diga isso a ele: a instalação precisa ser feita pelo Claude Code/Codex local.

## 👤 Para quem recebeu o link

Cole o link deste repositório no seu Claude Code ou Codex (rodando no seu computador) e peça: **"Instale a Trilhoteca deste link."** Depois abra uma nova sessão e peça, por exemplo: *"Use a Trilhoteca: quero piano calmo para uma cena de 40 segundos e um whoosh curto para o corte. É conteúdo próprio, monetizado, sem patrocínio."*

---


Uma biblioteca pessoal de música e efeitos sonoros gratuitos para edição, pesquisável pelo Claude Code e pelo Codex. Comece em **COMECE_AQUI.txt**: basta pedir à IA local para ler as instruções e instalar.

Esta edição inclui **5.677 músicas e 4.389 SFX**, com 108 cópias exatas ocultadas da busca. O catálogo contém links, características, créditos e evidências de licença; os arquivos de áudio ficam sob demanda. Cada pessoa tem seu próprio catálogo, projetos, favoritos e cache. Novas descobertas no computador de uma pessoa não sincronizam automaticamente para os demais.

Você pode pedir por clima, estilo, instrumentos, duração e função de cena, ou enviar várias cenas de uma vez. A ferramenta sugere candidatos a partir de metadados; a escolha artística depende da escuta. Há busca de novidades nas fontes integradas e busca de novas fontes, mais demorada e com revisão antes de integração.

O gabarito antes da busca é: **publicidade ou conteúdo próprio; monetizado sim/não; patrocinado sim/não**. Se faltar informação, a IA pergunta. CC0 e CC BY estão incluídas; faixas CC BY exigem crédito. Preserve o `CREDITOS.txt`, `MANIFESTO.json` e os comprovantes que acompanham as entregas. O código do aplicativo tem licença MIT; as músicas, efeitos, textos das fontes e metadados mantêm as condições de seus respectivos autores.

Instalação local em **macOS e Linux**, com Python 3.11+ e internet para instalar dependências e baixar os áudios. Validado em macOS; Linux não foi executado nesta entrega. Windows nativo não suportado. FFmpeg/ffprobe é opcional para medir características de novos arquivos; sem ele, algumas durações permanecerão desconhecidas e serão excluídas de filtros estritos. Claude Code e Codex devem estar instalados e configurados com a conta do próprio usuário. Nenhuma chave de API de terceiros é necessária para esta biblioteca.

O instalador registra o MCP e orientações de uso globalmente para futuros projetos. Abra uma nova sessão depois de instalar. O painel é opcional e funciona no próprio computador; o MCP atende mesmo com o painel fechado. Um chat na nuvem que não acessa seu computador não consegue instalar a biblioteca nele.

Para atualizar, baixe uma edição nova e peça à IA para repetir a instalação. Seu banco de projetos/favoritos/cache fica preservado; os itens adicionais do seu catálogo também. Guarde backups até verificar o resultado. Para desativar, peça à IA para remover somente a entrada `trilhoteca` nas configurações dos aplicativos e as skills `trilhoteca`; mantenha a pasta de dados se quiser preservar seu histórico.
