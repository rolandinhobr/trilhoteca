"""Explainable scene retrieval from source metadata. No claim of listening or embeddings."""
import math
import re
import unicodedata
from functools import lru_cache


def norm(value):
    value = re.sub(r'([a-z])([A-Z])', r'\1 \2', str(value))
    value = ''.join(c for c in unicodedata.normalize('NFKD', value.lower()) if not unicodedata.combining(c))
    value = re.sub(r'([a-z])([0-9])', r'\1 \2', value)
    value = re.sub(r'([0-9])([a-z])', r'\1 \2', value)
    return re.sub(r'[^a-z0-9]+', ' ', value).strip()


# One concept may have several spellings, but different requested concepts are ANDed.
FACETS = {
 'piano': ('instrumento', 'piano', ['piano', 'keys']),
 'guitarra': ('instrumento', 'guitarra', ['guitarra', 'guitar', 'guitars']),
 'cordas': ('instrumento', 'cordas', ['cordas', 'strings', 'violin', 'cello', 'violino']),
 'baixo': ('instrumento', 'baixo', ['bass', 'baixo']),
 'percussao': ('instrumento', 'percussão', ['percussion', 'percussao', 'drums', 'drum', 'bateria']),
 'flauta': ('instrumento', 'flauta', ['flute', 'flauta']),
 'synth': ('instrumento', 'sintetizador', ['synth', 'synths', 'synthesizer', 'sintetizador']),
 'calmo': ('clima', 'calmo', ['calmo', 'calma', 'calm', 'peaceful', 'relaxing', 'tranquil']),
 'delicado': ('energia', 'delicado', ['delicado', 'delicada', 'gentle', 'soft', 'delicate', 'suave', 'suaves', 'subtle', 'sutil', 'light', 'lighter']),
 'minimalista': ('estilo', 'minimalista', ['minimal', 'minimalist', 'minimalista', 'sparse', 'discreto', 'discreta', 'understated']),
 'suspense': ('clima', 'suspense', ['suspense', 'dark', 'sombrio', 'sombria', 'tense', 'tension', 'tensao', 'mysterious', 'misterioso', 'ominous', 'horror', 'unsettling']),
 'triste': ('clima', 'triste', ['sad', 'triste', 'melancholic', 'melancolico', 'bittersweet', 'melancholy']),
 'emocional': ('clima', 'emocional', ['emotional', 'emocional', 'emotivo', 'touching', 'sentimental']),
 'inspirador': ('clima', 'inspirador', ['uplifting', 'inspiring', 'inspirador', 'hopeful', 'hope', 'inspirational']),
 'alegre': ('clima', 'alegre', ['happy', 'alegre', 'joyful', 'cheerful', 'upbeat']),
 'humor': ('clima', 'humor', ['humor', 'funny', 'quirky', 'silly', 'cute', 'ludico', 'engracado', 'comedy', 'cartoon', 'comico', 'piada']),
 'epico': ('clima', 'épico', ['epic', 'epico', 'dramatic', 'dramatico', 'heroic']),
 'cinematico': ('estilo', 'cinemático', ['cinematic', 'cinematico', 'orchestral', 'orquestral']),
 'eletronica': ('estilo', 'eletrônica', ['electronic', 'eletronica', 'electronica', 'techno', 'edm']),
 'lofi': ('estilo', 'lo-fi', ['lofi', 'lo fi', 'chillhop']),
 'retro': ('estilo', 'retrô', ['retro', '8bit', '8 bit', 'chiptune', 'synthwave', 'bleep']),
 'energico': ('energia', 'energético', ['energetic', 'energico', 'energetico', 'intense', 'intenso', 'intensa', 'aggressive', 'agressivo', 'high energy']),
 'crescendo': ('estrutura', 'crescendo', ['crescendo', 'crescente', 'riser', 'risers', 'build up', 'builds', 'build', 'building', 'swells', 'gradually', 'increasing', 'crescer']),
 'loop': ('estrutura', 'loop', ['loop', 'loops', 'loopable', 'looping']),
 'whoosh': ('efeito', 'whoosh / passagem', ['whoosh', 'whooshes', 'woosh', 'swish', 'swishes', 'swoosh', 'swooshes', 'swhoshes', 'passagem']),
 'impacto': ('efeito', 'impacto', ['impact', 'impacts', 'impacto', 'hit', 'hits', 'punch', 'punches', 'slam', 'bang', 'thud', 'bump', 'batida']),
 'clique': ('efeito', 'clique', ['click', 'clicks', 'clique', 'cliques', 'tick', 'ticks']),
 'interface': ('efeito', 'interface', ['interface', 'ui', 'button', 'buttons', 'botao', 'botoes', 'confirmation', 'confirmacao', 'notification', 'notificacao']),
 'ambiente': ('ambiente', 'ambiente', ['ambient', 'ambience', 'ambiance', 'ambiente', 'atmospheric', 'atmosfera', 'room tone', 'soundscape']),
 'chuva': ('ambiente', 'chuva', ['rain', 'rainy', 'chuva', 'drizzle']),
 'trovao': ('ambiente', 'trovão', ['thunder', 'storm', 'trovao', 'tempestade']),
 'vento': ('ambiente', 'vento', ['wind', 'windy', 'vento', 'breeze']),
 'agua': ('material', 'água', ['water', 'agua', 'splash', 'splashes', 'drip', 'dripping', 'goteira']),
 'mar': ('ambiente', 'mar / praia', ['ocean', 'beach', 'sea', 'waves', 'praia', 'mar', 'ondas']),
 'passaros': ('ambiente', 'pássaros', ['bird', 'birds', 'chirp', 'chirping', 'passaro', 'passaros']),
 'floresta': ('ambiente', 'floresta', ['forest', 'floresta', 'woods', 'jungle', 'selva']),
 'cidade': ('ambiente', 'cidade / trânsito', ['city', 'cidade', 'traffic', 'trafego', 'transito', 'urban', 'street', 'rua']),
 'fogo': ('material', 'fogo', ['fire', 'fireplace', 'campfire', 'crackling', 'fogo', 'fogueira']),
 'passos': ('foley', 'passos', ['footstep', 'footsteps', 'step', 'steps', 'passo', 'passos', 'walking']),
 'porta': ('foley', 'porta', ['door', 'doors', 'porta', 'portas']),
 'papel': ('material', 'papel', ['paper', 'papel', 'page', 'pages', 'pagina', 'paginas']),
 'madeira': ('material', 'madeira', ['wood', 'wooden', 'madeira']),
 'metal': ('material', 'metal', ['metal', 'metallic', 'metalico', 'clang', 'clank']),
 'vidro': ('material', 'vidro', ['glass', 'vidro', 'bottle', 'garrafa']),
 'tecido': ('material', 'tecido', ['cloth', 'clothes', 'clothing', 'fabric', 'tecido', 'roupa']),
 'pedra': ('material', 'pedra / cascalho', ['stone', 'gravel', 'rock', 'pedra', 'cascalho']),
 'terra': ('material', 'terra / areia', ['dirt', 'mud', 'sand', 'grass', 'terra', 'lama', 'areia', 'grama']),
 'folhas': ('material', 'folhas', ['leaves', 'leaf', 'folhas']),
 'explosao': ('efeito', 'explosão', ['explosion', 'explosions', 'explode', 'explosao', 'boom']),
 'alarme': ('efeito', 'alarme', ['alarm', 'alarms', 'alarme', 'siren', 'sirene']),
 'motor': ('foley', 'motor', ['engine', 'motor', 'vehicle', 'car', 'carro', 'mechanic', 'mechanical']),
 'magia': ('efeito', 'magia', ['magic', 'magical', 'magia', 'spell', 'spells', 'feitico']),
 'scifi': ('estilo', 'ficção científica', ['sci fi', 'scifi', 'laser', 'lasers', 'space', 'espacial', 'robot', 'robo']),
 'glitch': ('efeito', 'glitch', ['glitch', 'glitches', 'static', 'estatica', 'interference']),
}

ROLE_DEFS = {
 'narracao': {'label':'acompanhar narração', 'query':['narracao','narration','voiceover','dialogo','fala','entrevista','dialogue'], 'features':['delicado','minimalista','calmo','lofi','ambiente'], 'kind':'music'},
 'crescimento': {'label':'crescer até a revelação', 'query':['revelacao','revelation','crescer ate','build up'], 'features':['crescendo'], 'kind':'music'},
 'humor': {'label':'pontuar uma piada', 'query':['piada','humor','comedia','comedy','engracado'], 'features':['humor'], 'kind':None},
 'transicao': {'label':'transição', 'query':['transicao','transition','troca de cena','passagem'], 'features':['whoosh','crescendo'], 'kind':'sfx'},
 'impacto': {'label':'pontuar um impacto', 'query':['impacto','impact','punch','batida'], 'features':['impacto','explosao'], 'kind':'sfx'},
 'ambientacao': {'label':'ambientar a cena', 'query':['ambientacao','ambiencia','ambience','ambiance','room tone'], 'features':['ambiente','chuva','vento','mar','passaros','cidade','floresta','fogo'], 'kind':'sfx'},
 'foley': {'label':'acompanhar ação / foley', 'query':['foley','acao cotidiana','movimento do personagem'], 'features':['passos','porta','papel','madeira','metal','vidro','tecido','agua'], 'kind':'sfx'},
 'tensao': {'label':'criar tensão', 'query':['criar tensao','tension','suspense'], 'features':['suspense'], 'kind':None},
 'abertura': {'label':'abrir o vídeo', 'query':['abertura','opening','intro'], 'features':['energico','inspirador','epico','alegre'], 'kind':'music'},
 'encerramento': {'label':'encerrar o vídeo', 'query':['encerramento','ending','outro'], 'features':['emocional','inspirador','calmo'], 'kind':'music'},
}


@lru_cache(maxsize=2048)
def alias_pattern(alias):
    return re.compile(r'(?<![a-z0-9])' + re.escape(norm(alias)) + r'(?![a-z0-9])')


def occurrence(text, aliases):
    for alias in aliases:
        match = alias_pattern(alias).search(text)
        if match:
            # A source saying "no drums" is evidence against percussion.
            if re.search(r'\b(no|not|non|without|sem)\s+(?:any\s+)?$', text[max(0,match.start()-20):match.start()]):
                continue
            return alias
    return None


def profile(asset):
    if asset['kind']=='sfx' and (asset.get('metadata_scope')=='member' or asset.get('archive_member') and 'collection_tags' in asset):
        file_text = asset.get('archive_member') or asset.get('member_text') or asset['title']
        return _member_profile(norm(file_text),norm(asset.get('album','')))
    text = norm(asset.get('search_text') or ' '.join([asset['title'], ' '.join(asset.get('tags',[])), asset.get('description',''), asset.get('source_description','')]))
    return _profile(text, asset['kind'])


@lru_cache(maxsize=12000)
def _member_profile(file_text, context):
    base=_profile(file_text,'sfx'); collection=_profile(context,'sfx')
    features=dict(base['facets']); inherited=collection['facets']
    categories={category:[key for key in inherited if FACETS[key][0]==category] for category in ('material','foley','ambiente','efeito')}
    for key, signal in inherited.items():
        category=FACETS[key][0]
        # A pack named "steps on wood, stone and leaves" describes variants;
        # its members must inherit "steps", never all three surfaces.
        if category in categories:
            if len(categories[category])!=1 or any(FACETS[k][0]==category for k in features):
                continue
            if category=='ambiente' and any(categories[c] for c in ('foley','material')) and key!='ambiente':
                continue
        if key not in features:
            features[key]={**signal,'basis':'família homogênea indicada no título da coleção'}
    roles=[r for r,d in ROLE_DEFS.items() if (not d['kind'] or d['kind']=='sfx') and any(k in features for k in d['features'])]
    return {**base,'facets':features,'scene_roles':[{'id':r,'label':ROLE_DEFS[r]['label']} for r in roles]}


@lru_cache(maxsize=12000)
def _profile(text, kind):
    evidence = {}
    for key, (_, label, aliases) in FACETS.items():
        hit = occurrence(text, aliases)
        if hit:
            evidence[key] = {'label':label, 'signal':hit, 'basis':'metadados da fonte / arquivo'}
    roles = [key for key, d in ROLE_DEFS.items() if (not d['kind'] or d['kind']==kind) and any(k in evidence for k in d['features'])]
    return {'facets': evidence, 'scene_roles': [{'id':r,'label':ROLE_DEFS[r]['label']} for r in roles],
            'basis':'Sugestões por regras sobre metadados; compatibilidade artística depende de escuta.', 'audio_analyzed':False}


def numeric(value, name):
    if value is None:
        return None
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value < 0:
        raise ValueError(name + ' deve ser um número finito positivo.')
    return float(value)


def interpret(query, kind='all', function=None, no_voice=None, duration_min=None, duration_max=None, scene_seconds=None, exclude=None):
    if not isinstance(query,str) or len(query)>5000:
        raise ValueError('Pedido deve ser um texto de até 5000 caracteres.')
    if exclude is not None and (not isinstance(exclude,list) or any(not isinstance(t,str) or not t.strip() for t in exclude)):
        raise ValueError('excluir precisa ser uma lista de características em texto.')
    q = norm(query)
    if function is not None and function not in ROLE_DEFS:
        raise ValueError('Função de cena desconhecida. Consulte listar_funcoes_de_cena.')
    roles = [function] if function else [r for r,d in ROLE_DEFS.items() if occurrence(q,d['query'])]
    negative = set()
    positive = []
    for key, (_,label,aliases) in FACETS.items():
        for alias in aliases:
            if re.search(r'\b(?:sem|without|no|evitar|avoid)\s+' + re.escape(norm(alias)) + r'\b', q):
                negative.add(key)
        if occurrence(q,aliases):
            positive.append(key)
    for word in exclude or []:
        normalized = norm(word)
        negative.add(next((key for key,(_,_,aliases) in FACETS.items() if normalized in [norm(a) for a in aliases]), 'text:' + normalized))
    if no_voice is not None and type(no_voice) is not bool:
        raise ValueError('sem_voz precisa ser sim/não (booleano).')
    if re.search(r'\b(?:sem (?:voz|vocal|vocais)|no vocals|instrumental)\b', q):
        no_voice = True
    implied_kinds = {ROLE_DEFS[r]['kind'] for r in roles if ROLE_DEFS[r]['kind']}
    if kind == 'all' and len(implied_kinds)==1:
        kind = implied_kinds.pop()
    if kind == 'all' and (any(t in q.split() for t in ('trilha','musica')) or any(FACETS[k][0]=='instrumento' for k in positive)):
        kind = 'music'
    if kind == 'all' and ('sfx' in q.split() or 'efeito' in q.split() or any(FACETS[k][0] in ('efeito','foley','material') for k in positive)):
        kind = 'sfx'
    if kind == 'all' and any(k in positive for k in ('chuva','trovao','vento','mar','passaros','floresta','cidade')):
        kind = 'sfx'
    duration_min = numeric(duration_min,'duração mínima'); duration_max = numeric(duration_max,'duração máxima')
    scene_seconds = numeric(scene_seconds,'duração da cena')
    if duration_min is not None and duration_max is not None and duration_min > duration_max:
        raise ValueError('Duração mínima não pode exceder a máxima.')
    amount = re.search(r'\b(\d+(?:[.,]\d+)?)\s*(s|sec|segundo|segundos|seconds|min|minuto|minutos)\b', query.lower())
    if amount and duration_min is None and duration_max is None and scene_seconds is None:
        value = float(amount[1].replace(',','.')) * (60 if amount[2].startswith('min') else 1)
        if kind=='sfx': duration_max=value
        else: scene_seconds=value
    # Retain literal search for titles and artists when no scene vocabulary is used.
    stop = {'quero','uma','um','com','para','que','de','e','a','o','trilha','musica','sem','voz','vocal','vocais','narracao','sob','minha','meu','video','efeito','sonoro','sfx','som','cena','ate','segundos','segundo','s','sec','minutos','minuto','na','no','os','as','por','em','ao','do','da','pelo','pela','acompanhando','acompanhar','pontuar','criar','preciso','encontrar','buscar','pra','desse','dessa','esse','essa'}
    consumed = set()
    for key in positive + list(k for k in negative if k in FACETS):
        for alias in FACETS[key][2]: consumed.update(norm(alias).split())
    for role in roles:
        for phrase in ROLE_DEFS[role]['query']: consumed.update(norm(phrase).split())
    words = norm(query[:amount.start()] + query[amount.end():]).split() if amount else q.split()
    remaining = [t for t in words if t not in stop and t not in consumed and not t.isdigit()]
    return {'kind':kind,'facets':positive,'roles':roles,'excluded':sorted(negative),'no_voice':no_voice,
            'duration_min':duration_min,'duration_max':duration_max,'scene_seconds':scene_seconds,
            'literal_terms':remaining if not positive and not roles else [],
            'uninterpreted_terms':remaining if positive or roles else [],
            'description':'Busca de cena por conceitos e evidências nos metadados; sem análise perceptual do áudio.'}


def evaluate(asset, request, allow_unknown=False):
    if request['kind'] != 'all' and asset['kind'] != request['kind']:
        return None
    p = profile(asset); features = p['facets']; matched=[]; missing=[]; pending=[]; evidence=[]
    text = norm(asset.get('search_text') or ' '.join([asset['title'],asset['artist'],asset.get('description',''),' '.join(asset.get('tags',[]))]))
    for key in request['excluded']:
        if key in features or key.startswith('text:') and key[5:] in text:
            return None
    if request['no_voice'] is True:
        if asset.get('vocals') is True: return None
        if asset.get('vocals') is not False:
            if not allow_unknown: return None
            pending.append('Presença de voz ainda não conferida.')
        else: matched.append('sem voz conforme a fonte')
    duration = asset.get('duration')
    bounds = request['duration_min'] is not None or request['duration_max'] is not None or request['scene_seconds'] is not None
    if bounds and duration is None:
        if not allow_unknown: return None
        pending.append('Duração ainda não medida; conferir antes de usar nesta cena.')
    elif bounds:
        if request['duration_min'] is not None and duration < request['duration_min']: return None
        if request['duration_max'] is not None and duration > request['duration_max']: return None
        if request['scene_seconds'] is not None and duration < request['scene_seconds'] and 'loop' not in features: return None
        matched.append('duração suficiente / loop declarado' if request['scene_seconds'] else 'duração dentro do intervalo')
    for key in request['facets']:
        label = FACETS[key][1]
        if key in features:
            matched.append(label); evidence.append(features[key])
        else: missing.append(label)
    for role in request['roles']:
        d = ROLE_DEFS[role]
        if d['kind'] and d['kind'] != asset['kind']: missing.append(d['label']); continue
        hits = [k for k in d['features'] if k in features]
        if hits:
            matched.append('candidato para ' + d['label']); evidence.extend(features[k] for k in hits)
        else: missing.append(d['label'])
        if role=='narracao' and asset.get('vocals') is None and not any('voz' in s for s in pending):
            pending.append('Presença de voz ainda não conferida; ouvir junto à narração.')
    for term in request['literal_terms']:
        if occurrence(text + ' ' + norm(asset['artist']), [term]): matched.append(term)
        else: missing.append(term)
    if request['uninterpreted_terms']:
        pending.append('Termos ainda sem interpretação: ' + ', '.join(request['uninterpreted_terms']))
    # Never use unrelated audio as a fallback for a nonempty brief.
    if (request['facets'] or request['roles'] or request['literal_terms']) and not any(x for x in matched if x not in ('sem voz conforme a fonte','duração dentro do intervalo','duração suficiente / loop declarado')):
        return None
    score = len(matched)*10 - len(missing)*12 - len(pending)*2
    score += 2 if asset.get('feedback')=='favorite' else 0
    score += 4 if 'narracao' in request['roles'] and asset.get('vocals') is False else 0
    score -= min(asset.get('use_count',0),5)*.2
    return {'score':score,'matched':list(dict.fromkeys(matched)),'missing':list(dict.fromkeys(missing)),
            'pending':pending,'evidence':evidence,'profile':p,
            'fit':'partial' if missing else 'candidate', 'listening_required':True}


def functions():
    return [{'id':k,'label':d['label'],'tipo_sugerido':d['kind']} for k,d in ROLE_DEFS.items()]
