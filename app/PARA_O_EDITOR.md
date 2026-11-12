# Usar a Trilhoteca

Use a biblioteca local para buscar música e SFX. Nunca invente respostas de finalidade, permissões ou características sonoras.

Antes da primeira busca em um projeto, obtenha:

**Uso:** publicidade / conteúdo próprio  
**Monetizado:** sim / não  
**Tem patrocínio ou parceria comercial:** sim / não  
**Trilha desejada:** clima, estilo, instrumentos e duração aproximada

Se faltar informação, pergunte. Aceite respostas em linguagem natural. Confira `listar_projetos` para reutilizar a resposta apenas quando se tratar efetivamente do mesmo projeto. Salve o gabarito em `definir_projeto` e use o ID retornado nas buscas, prévias e entregas.

Busque com `buscar_audio`; consulte `consultar_audio` antes de selecionar. Diga claramente quais características vêm da página da fonte ou da coleção. A seleção inicial é de candidatos para escuta, não de faixas aprovadas artisticamente.

Prepare somente as prévias escolhidas com `preparar_previa`. Para apresentar o áudio, use o caminho retornado e o player do seu aplicativo. Não anuncie que o arquivo foi ouvido quando apenas seus metadados foram inspecionados.

Depois da escolha, use `baixar_selecionadas` com a pasta de assets do projeto, quando conhecida. Os arquivos só estão entregues quando a ferramenta devolver `delivery_path` e os caminhos finais. Use o crédito do `CREDITOS.txt` ao publicar, conforme a licença. Preserve `MANIFESTO.json` e `licencas/` no projeto.

Favoritos e rejeições são registrados com `avaliar_audio`. Uma prévia local não representa uso na edição; a entrega registra o histórico de escolha por projeto.

Se publicidade, monetização ou patrocínio mudarem, atualize o gabarito antes de prosseguir. Downloads que falham devem ser relatados; não substitua uma faixa por outro arquivo silenciosamente.

Para ampliar o acervo, use `buscar_novidades`. Para ampliar somente músicas, passe `somente_musicas=true`; para somente efeitos, `somente_sfx=true`. Não combine os dois sinalizadores. Os álbuns novos são indexados pelo manifesto oficial sem baixar os áudios: o download fica para a prévia ou entrega solicitada. Para procurar outros repositórios/artistas, use `buscar_novas_fontes`, explicando que a busca é mais complexa e demorada. Consulte o andamento em `consultar_busca` com intervalos razoáveis. A expansão é global e não exige preencher um projeto; a busca e entrega de áudio continuam exigindo o gabarito.

As fontes externas encontradas são candidatas à integração. Não trate pistas de licença em uma página como autorização para todas as gravações. Se o usuário pedir a integração de uma fonte, confira seu mecanismo de indexação/download e as permissões específicas antes de adicioná-la. As faixas descobertas nos índices já conectados passam pela conferência específica da ficha, mas ainda precisam de seleção artística na escuta.

## Busca por função e por várias cenas

Use `listar_funcoes_de_cena` para consultar os identificadores. `buscar_audio` aceita `funcao`, `sem_voz`, `duracao_min`, `duracao_max`, `duracao_cena` (segundos), `excluir` e `permitir_desconhecidos`. `sem_voz=False` permite voz; não exige que o som seja vocal. Música menor que a cena só passa quando há loop declarado; isso não cria nem garante um loop perfeito.

Para montar a sonorização de uma sequência, use `buscar_por_cena`, com uma lista de até 20 objetos. Cada objeto aceita `nome`, `pedido`, `tipo`, `funcao` e os filtros acima. Exemplo: cena “Fala”, pedido “piano calmo”, tipo “music”, função “narracao”; cena “Corte”, pedido “whoosh”, tipo “sfx”, duração máxima 2; cena “Passos”, pedido “passos madeira”, tipo “sfx”.

`assets` contém candidatos que atendem aos conceitos reconhecidos. `alternatives` contém opções PARCIAIS e não deve ser apresentado como atendimento completo. Em `scene_match`, apresente `matched` (motivos), `missing` (o que falta), `pending` (o que precisa de conferência) e `evidence` (sinais dos metadados). A função editorial é sugestão inferida; não análise perceptual.

Por padrão, voz e duração desconhecidas ficam fora dos filtros correspondentes. Só use `permitir_desconhecidos=true` para uma pesquisa exploratória explicitamente comunicada, mantendo as pendências. Não substitua uma busca vazia por resultados parciais sem explicar. Se um termo ficar sem interpretação, informe a limitação ou traduza o pedido em conceitos mais claros antes de buscar novamente.

Os SFX agora incluem ambientes, passos, materiais, portas, água, fogo, transições, impactos, magia e ficção científica. Há variações de um efeito e gravações que contêm sequências; confira o arquivo original antes de sincronizar. Packs podem conter metadados compartilhados, mas o objeto/material da busca usa o membro/pasta específico quando disponível.
