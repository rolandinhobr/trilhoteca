const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {token:null, projects:[], project:null, kind:'all', favorites:false, selected:new Map(), assets:[], alternatives:[], playing:null, editing:null, seq:0};
let toastTimer, searchTimer;
function toast(message, error=false, undo=null) {
  clearTimeout(toastTimer); const t=$('#toast'); t.textContent=message; t.className='toast'+(error?' error':''); t.hidden=false;
  if(undo){const b=document.createElement('button');b.textContent='Desfazer';b.onclick=()=>{undo();t.hidden=true};t.append(b)}
  toastTimer=setTimeout(()=>t.hidden=true,error?9000:5500);
}
async function api(path, body) {
 const request=()=>fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json','X-Trilhoteca-Token':state.token},body:JSON.stringify(body)}:{});
 let r=await request();
 if(body&&r.status===403){const meta=await fetch('/api/meta').then(x=>x.json());state.token=meta.token;r=await request();}
 const data=await r.json();if(!r.ok)throw new Error(data.error||'Não foi possível concluir.');return data;
}
const caught = fn => (...args)=>Promise.resolve(fn(...args)).catch(e=>toast(e.message,true));
function duration(sec){if(!sec)return '—';if(sec<10)return sec.toFixed(2).replace('.',',')+' s';const rounded=Math.round(sec);return `${Math.floor(rounded/60)}:${String(rounded%60).padStart(2,'0')}`}
function updateSelection(){ $('#selected-count').textContent=state.selected.size;$('#delivery-open').disabled=!state.selected.size; }
function setCurrent(project){
  state.project=project;state.selected.clear();updateSelection();$('#audio').pause();state.playing=null;
  $('#project-select').value=project?.id||'';
  $('#context-label').textContent=project ? `${project.usage==='publicidade'?'Publicidade':'Conteúdo próprio'} · ${project.monetized?'monetizado':'sem monetização'} · ${project.sponsored?'com parceria':'sem parceria'}`:'Responda o gabarito para começar.';
}
function projectOptions(){ $('#project-select').innerHTML='<option value="">Escolha um projeto</option>'+state.projects.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');$('#project-select').value=state.project?.id||''; }
function projectDialog(project=null){
 state.editing=project?.id||null;const form=$('#project-form');form.reset();form.elements.name.value=project?.name||'';
 for(const field of ['usage','monetized','sponsored'])if(project?.[field]!=null){const v=String(project[field]);form.querySelector(`input[name="${field}"][value="${v}"]`).checked=true;}
 $('#project-cancel').hidden=false;$('#project-cancel').textContent=state.project?'Cancelar':'Depois';$('#project-dialog').showModal();
}
async function search(){
 const seq=++state.seq;
 if(!state.project){$('#results').innerHTML='<div class="empty"><strong>Primeiro, conte sobre o projeto.</strong>O gabarito ajuda a escolher os sons permitidos para o seu vídeo.</div>';$('#result-count').textContent='Sua biblioteca está pronta para explorar.';return}
 $('#results').innerHTML='<div class="loading-state">Buscando sons para a sua cena…</div>';
 const params=new URLSearchParams({project_id:state.project.id,query:$('#search').value,kind:state.kind,credit:$('#no-credit').checked?'no_credit':'all',favorites:String(state.favorites),function:$('#scene-function').value,no_voice:String($('#no-voice').checked),duration_max:$('#duration-max').value,allow_unknown:String($('#allow-unknown').checked)});
 const data=await api('/api/search?'+params);
 if(seq!==state.seq)return;
 if(data.needs_context){projectDialog(state.project);return}
 state.assets=data.assets;state.alternatives=data.alternatives||[];
 $('#search-explanation').textContent=data.message|| (data.interpreted_request?.uninterpreted_terms?.length?'Ainda precisa de conferência: '+data.interpreted_request.uninterpreted_terms.join(', ')+'.':'Características combinadas. As indicações vêm da fonte e dos nomes dos arquivos; ouça para confirmar.');
 $('#catalog-title').textContent=state.favorites?'Seus favoritos':($('#search').value?'Sons para a sua busca':'Encontre o som da cena');
 $('#result-count').textContent=`${data.total>data.assets.length?'Mostrando '+data.assets.length+' de ':''}${data.total} ${data.total===1?'som disponível':'sons disponíveis'} para ${state.project.name}`;
 render();
}
function trackHTML(a){
 const match=a.scene_match;const pending=[...(match?.missing||[]).map(x=>'Falta: '+x),...(match?.pending||[])];
 return `<article class="track ${state.selected.has(a.id)?'selected':''}" data-id="${esc(a.id)}">
 <input type="checkbox" class="select-track" aria-label="Selecionar ${esc(a.title)}" ${state.selected.has(a.id)?'checked':''}>
 <button class="play" data-action="play" aria-label="Ouvir ${esc(a.title)}">${state.playing===a.id&&!$('#audio').paused?'Ⅱ':'▶'}</button>
 <div><button class="track-title" data-action="details">${esc(a.title)}</button><div class="track-artist">${esc(a.artist)} · ${esc(a.album||'Música independente')}</div><div class="tags">${a.tags.slice(0,4).map(t=>`<span class="tag">${esc(t)}</span>`).join('')}</div>${match?.matched?.length?`<p class="match-reason">${esc(match.matched.join(' · '))}</p>`:''}${pending.length?`<p class="match-pending">${esc(pending.join(' · '))}</p>`:''}</div>
 <div class="rights-label">${a.rights.attribution_required?'Crédito obrigatório':'Uso amplo'}<small>${esc(a.rights.license)}</small></div><span class="duration">${duration(a.duration)}</span>
 <div class="track-actions"><button class="favorite ${a.feedback==='favorite'?'on':''}" data-action="favorite" aria-label="${a.feedback==='favorite'?'Remover favorito':'Favoritar'} ${esc(a.title)}">${a.feedback==='favorite'?'♥':'♡'}</button><button class="info" data-action="details" aria-label="Detalhes de ${esc(a.title)}">i</button></div></article>`;
}
function render(){
 $('#results').innerHTML=state.assets.length?state.assets.map(trackHTML).join(''):'<div class="empty"><strong>Nenhum som atende a todos os requisitos ainda.</strong>Confira as alternativas abaixo, ajuste o pedido ou amplie a biblioteca.</div>';
 $('#alternatives').hidden=!state.alternatives.length;
 $('#alternative-results').innerHTML=state.alternatives.map(trackHTML).join('');
}
function findTrack(id){return [...state.assets,...state.alternatives].find(a=>a.id===id)}
async function play(a,button){
 const audio=$('#audio');
 if(state.playing===a.id&&audio.src){if(audio.paused)await audio.play();else audio.pause();render();return}
 button.disabled=true;button.classList.add('loading');button.textContent='…';
 $('#playing-title').textContent='Preparando prévia…';$('#playing-artist').textContent=a.archive_member?'O álbum é baixado na primeira escuta.':'Baixando o arquivo escolhido.';
 try{
  const prepared=await api('/api/preview',{asset_id:a.id,project_id:state.project.id});
  state.playing=a.id;audio.src=`/api/audio/${a.id}?project_id=${state.project.id}`;audio.volume=.55;
  $('#playing-title').textContent=a.title;$('#playing-artist').textContent=a.artist;
  a.duration=prepared.audio_info.duration||a.duration;a.local=true;
  try{await audio.play()}catch{toast('Prévia pronta. Aperte play no reprodutor para ouvir.')}
 }finally{button.disabled=false;button.classList.remove('loading');render()}
}
async function details(a){
 const data=await api(`/api/asset/${a.id}?project_id=${state.project.id}`);const r=data.rights;
 $('#detail-content').innerHTML=`<p class="eyebrow">${data.kind==='sfx'?'EFEITO SONORO':'MÚSICA INDEPENDENTE'}</p><h2>${esc(data.title)}</h2><p class="dialog-intro">${esc(data.artist)}${data.album?' · '+esc(data.album):''}</p><p class="detail-description">${esc(data.description)}</p><div class="tags">${data.tags.map(t=>`<span class="tag">${esc(t)}</span>`).join('')}</div><div class="detail-meta">Duração: ${duration(data.duration)}<br>Voz: ${data.vocals===false?'sem voz, conforme a fonte':data.vocals===true?'com voz':'a conferir na escuta'}<br>Características: ${esc(data.metadata_basis||'informações da fonte')}<br>Funções sugeridas: ${esc((data.scene_profile?.scene_roles||[]).map(r=>r.label).join(', ')||'a conferir')}<br>${a.scene_match?.missing?.length?'Pedido: faltam '+esc(a.scene_match.missing.join(', '))+'<br>':''}Fonte: ${esc(data.source_name)}<br>Licença: ${esc(r.license)} · ${r.attribution_required?'crédito obrigatório':'crédito opcional'}<br>Uso: ${esc(data.eligibility_reason)}<br>Usada em ${data.use_count} ${data.use_count===1?'projeto':'projetos'} nesta biblioteca.</div>${data.content_id_note?`<p class="detail-warning">${esc(data.content_id_note)}</p>`:''}<a class="detail-source" href="${esc(data.source_url)}" target="_blank" rel="noopener noreferrer">Ver página original ↗</a><label class="field">Crédito de publicação<textarea class="credits" readonly>${esc(r.credit_text||`${data.title} — ${data.artist}\n${data.source_url}\nCC0; crédito opcional.`)}</textarea></label><button class="secondary" id="copy-credit">Copiar crédito</button> <button class="secondary" id="reject">Não combina comigo</button>`;
 $('#copy-credit').onclick=caught(async()=>{await navigator.clipboard.writeText($('#detail-content textarea').value);toast('Crédito copiado.')});
 $('#reject').onclick=caught(async()=>{await api('/api/feedback',{asset_id:a.id,value:'dislike'});state.selected.delete(a.id);updateSelection();$('#detail-dialog').close();await search();toast('Esse som foi retirado das próximas buscas.',false,caught(async()=>{await api('/api/feedback',{asset_id:a.id,value:'clear'});await search()}))});
 $('#detail-dialog').showModal();
}
function deliveryDialog(){
 $('#delivery-selection').innerHTML=Array.from(state.selected.values()).map(a=>`<div class="selection-item"><div>${esc(a.title)}<small>${esc(a.artist)}</small></div><button data-remove="${a.id}" aria-label="Remover ${esc(a.title)}">×</button></div>`).join('');
 $('#delivery-result').innerHTML='';$('#deliver').disabled=!state.selected.size;$('#delivery-dialog').showModal();
}
$('#project-form').onsubmit=caught(async e=>{
 e.preventDefault();const f=new FormData(e.currentTarget);
 const data=await api('/api/project',{name:f.get('name'),usage:f.get('usage'),monetized:f.get('monetized')==='true',sponsored:f.get('sponsored')==='true',project_id:state.editing});
 state.projects=state.projects.filter(p=>p.id!==data.project.id);state.projects.unshift(data.project);setCurrent(data.project);projectOptions();$('#project-dialog').close();await search();
});
// The gabarito may be deferred to explore expansion; audio search still requires it.
$('#project-cancel').onclick=()=>$('#project-dialog').close();
$('#new-project').onclick=()=>projectDialog();$('#edit-project').onclick=()=>projectDialog(state.project);
$('#project-select').onchange=caught(async e=>{const p=state.projects.find(p=>p.id===e.target.value);if(!p){projectDialog();return}setCurrent(p);await search()});
$('#search').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(caught(search),250)};
$('#no-credit').onchange=caught(search);
for(const id of ['scene-function','no-voice','duration-max','allow-unknown'])$('#'+id).onchange=caught(search);
document.querySelectorAll('[data-query]').forEach(b=>b.onclick=caught(async()=>{$('#search').value=b.dataset.query;$('#scene-function').value=b.dataset.function||'';if(b.dataset.kindHint){state.kind=b.dataset.kindHint;document.querySelectorAll('[data-kind]').forEach(x=>x.classList.toggle('active',x.dataset.kind===state.kind));}await search()}));
document.querySelectorAll('[data-kind]').forEach(b=>b.onclick=caught(async()=>{state.kind=b.dataset.kind;document.querySelectorAll('[data-kind]').forEach(x=>x.classList.toggle('active',x===b));await search()}));
$('#nav-all').onclick=caught(async()=>{state.favorites=false;$('#nav-all').classList.add('active');$('#nav-favorites').classList.remove('active');await search()});
$('#nav-favorites').onclick=caught(async()=>{state.favorites=true;$('#nav-favorites').classList.add('active');$('#nav-all').classList.remove('active');await search()});
for(const region of ['#results','#alternative-results'])$(region).addEventListener('change',e=>{if(!e.target.matches('.select-track'))return;const a=findTrack(e.target.closest('.track').dataset.id);if(e.target.checked)state.selected.set(a.id,a);else state.selected.delete(a.id);updateSelection();render()});
for(const region of ['#results','#alternative-results'])$(region).addEventListener('click',caught(async e=>{const b=e.target.closest('[data-action]');if(!b)return;const a=findTrack(b.closest('.track').dataset.id);if(b.dataset.action==='play')await play(a,b);if(b.dataset.action==='details')await details(a);if(b.dataset.action==='favorite'){const value=a.feedback==='favorite'?'clear':'favorite';await api('/api/feedback',{asset_id:a.id,value});a.feedback=value==='clear'?null:value;render();if(state.favorites)await search()}}));
$('#audio').addEventListener('play',render);$('#audio').addEventListener('pause',render);$('#audio').addEventListener('ended',render);
$('#delivery-open').onclick=deliveryDialog;
$('#delivery-selection').onclick=e=>{const b=e.target.closest('[data-remove]');if(!b)return;state.selected.delete(b.dataset.remove);updateSelection();render();$('#delivery-dialog').close();deliveryDialog()};
$('#deliver').onclick=caught(async()=>{
 const button=$('#deliver');button.disabled=true;button.textContent='Preparando os arquivos e as licenças…';
 try{const result=await api('/api/deliver',{asset_ids:Array.from(state.selected.keys()),project_id:state.project.id,assets_dir:$('#assets-dir').value.trim()});
 if(result.needs_context){$('#delivery-dialog').close();projectDialog(state.project);return}
 $('#delivery-result').innerHTML=`<div class="delivery-success"><strong>Entrega pronta · ${result.count} ${result.count===1?'arquivo':'arquivos'}</strong><br>Áudio original, créditos e licenças salvos.<code>${esc(result.delivery_path)}</code></div>`;state.selected.clear();updateSelection();render();await search();
 }finally{button.textContent='Baixar e preparar entrega →';button.disabled=!state.selected.size}
});
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>$('#'+b.dataset.close).close());
caught(async()=>{const meta=await api('/api/meta');state.token=meta.token;state.projects=meta.projects;$('#stats').textContent=`${meta.stats.music} músicas · ${meta.stats.sfx} efeitos`;
 const existing=state.projects.find(p=>p.usage!=null&&p.monetized!=null&&p.sponsored!=null);
 if(existing)setCurrent(existing);projectOptions();await search();await pollDiscovery();if(!existing)projectDialog();
})();

let discoveryTimer, discoveryJobId=null, discoveryCompleted=null, sourceCandidates=[];
function renderSourceCandidates(){
 $('#source-list').innerHTML=sourceCandidates.length?sourceCandidates.map(c=>`<article class="source-card"><span class="source-status">Permissões e conexão a conferir</span><h3>${esc(c.name)}</h3><p>${esc(c.domain)}<br>${c.license_hints.length?'Referências encontradas: '+esc(c.license_hints.join(', ')):'Nenhuma licença identificada na página consultada.'}<br>Essas referências não confirmam a licença das faixas.</p><a href="${esc(c.url)}" target="_blank" rel="noopener noreferrer">Ver fonte ↗</a> · <a href="${esc(c.reference_url)}" target="_blank" rel="noopener noreferrer">Onde foi encontrada ↗</a><br><button class="secondary" data-integrate="${esc(c.domain)}">Copiar pedido de integração</button></article>`).join(''):'<p class="dialog-intro">Ainda não há fontes novas. Use “Buscar novas fontes” para procurar outros acervos.</p>';
}
function showSourceCandidates(){renderSourceCandidates();$('#sources-dialog').showModal()}
async function pollDiscovery(){
 clearTimeout(discoveryTimer);
 const result=await api('/api/discovery');sourceCandidates=result.candidates;if($('#sources-dialog').open)renderSourceCandidates();
 $('#source-count').textContent=sourceCandidates.length;
 $('#stats').textContent=`${result.stats.music} músicas · ${result.stats.sfx} efeitos`;
 const job=result.job;const active=job&&['starting','running'].includes(job.status);
 $('#discover-tracks').disabled=!!active;$('#discover-sources').disabled=!!active;
 if(job){
  discoveryJobId=job.id;$('#discovery-status').hidden=false;$('#discovery-status').className='discovery-status'+(active?' running':['failed','interrupted'].includes(job.status)?' failed':'');
  $('#discovery-message').textContent=job.message;
  const label=job.mode==='sources'?'fontes encontradas':'sons adicionados';
  $('#discovery-detail').textContent=`${job.checked} fichas/páginas conferidas · ${job.added} ${label}${job.skipped?' · '+job.skipped+' páginas não incorporadas nesta etapa':''}${active?' · Pode continuar usando o painel.':''}`;
  if(!active&&discoveryCompleted!==job.id){discoveryCompleted=job.id;if(state.project)await search()}
 }
 if(active)discoveryTimer=setTimeout(caught(pollDiscovery),3000);
}
async function startDiscovery(mode){
 $('#discover-tracks').disabled=true;$('#discover-sources').disabled=true;
 try{const result=await api('/api/discovery/start',{mode});if(!result.started)toast(result.message);await pollDiscovery()}
 catch(e){$('#discover-tracks').disabled=false;$('#discover-sources').disabled=false;throw e}
}
$('#discover-tracks').onclick=caught(()=>startDiscovery($('#discovery-kind').value));
$('#discover-sources').onclick=caught(()=>startDiscovery('sources'));
$('#show-sources').onclick=showSourceCandidates;
$('#source-list').onclick=caught(async e=>{const button=e.target.closest('[data-integrate]');if(!button)return;const source=sourceCandidates.find(c=>c.domain===button.dataset.integrate);await navigator.clipboard.writeText(`Integre esta fonte na Trilhoteca: ${source.url}. Confira autoria, licença por faixa para vídeo comercial/publicidade e a forma de busca/download. A página foi descoberta em ${source.reference_url}. Preserve o catálogo e os assets existentes.`);toast('Pedido copiado. Cole aqui ou no Claude Code para integrar essa fonte.')});
