/* Vice Clips: navegação, início, lives, geração, galeria e configurações. */
const $ = s => document.querySelector(s);
function el(tag, props = {}, ...filhos) {
  const n = Object.assign(document.createElement(tag), props);
  n.append(...filhos.filter(f => f !== null && f !== undefined));
  return n;
}
function svgIcone(d) {
  const t = document.createElement('template');
  t.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${d}</svg>`;
  return t.content.firstChild;
}
const ICONES = {
  inicio: '<path d="M12 22V10"/><path d="M12 10C10 6 6 5 3 7c3 0 6 1 9 3Z"/><path d="M12 10c2-4 6-5 9-3-3 0-6 1-9 3Z"/><path d="M12 10C9 8 5 9 4 13c2-2 5-3 8-3Z"/><path d="M12 10c3-2 7-1 8 3-2-2-5-3-8-3Z"/><path d="M7 22h10"/>',
  lives: '<circle cx="12" cy="12" r="2.5"/><path d="M7.5 7.5a6.5 6.5 0 0 0 0 9M16.5 7.5a6.5 6.5 0 0 1 0 9M4.5 4.5a11 11 0 0 0 0 15M19.5 4.5a11 11 0 0 1 0 15"/>',
  gerar: '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M8.5 7.5 20 18M8.5 16.5 20 6"/>',
  cortes: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M8 4v16M16 4v16M3 9h5M3 15h5M16 9h5M16 15h5"/>',
  editor: '<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>',
  descobrir: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/><path d="M11 8v6M8 11h6"/>',
  referencias: '<path d="M6 3h11a1 1 0 0 1 1 1v17l-6.5-4L5 21V4a1 1 0 0 1 1-1Z"/>',
  producao: '<path d="m12 3 9 4.5-9 4.5-9-4.5Z"/><path d="m3 12 9 4.5 9-4.5"/><path d="m3 16.5 9 4.5 9-4.5"/>',
  config: '<circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 0 0-2-1.2L14 3h-4l-.5 2.6a7 7 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6a7 7 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 2 1.2L10 21h4l.5-2.6a7 7 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2Z"/>',
};
const TELAS = [['inicio', 'Início'], ['descobrir', 'Lives'], ['lives', 'Lives'], ['gerar', 'Gerar Cortes'], ['cortes', 'Meus Cortes'], ['producao', 'Produção'], ['editor', 'Editor'], ['referencias', 'Referências'], ['config', 'Configurações']];
const CORES = { Twitch: 'var(--twitch)', Kick: 'var(--kick)', YouTube: 'var(--youtube)', twitch: 'var(--twitch)', kick: 'var(--kick)' };
const PLATAFORMA = { twitch: 'Twitch', kick: 'Kick' };
const ETAPAS = ['Lendo o áudio', 'Procurando picos', 'Transcrevendo', 'Gerando os cortes'];
const G = { tela: 'inicio', lives: [], tarefas: [], canais: { canais: [], top: [], clips: [], avisos: [] }, filtro: { plataforma: 'Todas', streamer: '', ordem: 'recentes', estado: 'todos' }, visiveis: [], atual: 0, acompanhando: false, cfg: null, abaLives: 'vivo', modoGerar: 'manual' };
const ESTADOS = { pronto: 'Pronto para editar', editando: 'Em edição', exportado: 'Reel exportado' };

function avisar(texto, erro = false) {
  const n = el('div', { className: 'aviso' + (erro ? ' erro' : ''), textContent: texto });
  $('#avisos').append(n);
  setTimeout(() => n.remove(), erro ? 7000 : 4000);
}
async function api(caminho, corpo) {
  const op = corpo === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) };
  let r;
  try { r = await fetch(caminho, op); } catch (e) { $('#desligado').hidden = false; throw e; }
  $('#desligado').hidden = true;
  const d = await r.json().catch(() => ({}));
  if (r.status === 404 && caminho.startsWith('/api/')) throw new Error(PAINEL_VELHO);
  if (!r.ok) throw new Error(d.erro || 'Não consegui completar esse pedido.');
  return d;
}
const PAINEL_VELHO = 'O painel aberto é de uma versão anterior e não tem este recurso. Pare a gravação (se houver), feche a janela preta do painel e abra o abrir_painel.cmd de novo.';
/* A tela é lida do disco a cada carregamento, mas o painel (a janela preta) só muda quando é reaberto: avisa quando os dois não batem. */
async function conferirVersao() {
  try {
    const r = await fetch('/api/descobrir/modelos');
    if (r.status === 404) { const n = el('div', { className: 'aviso erro', textContent: PAINEL_VELHO }); $('#avisos').append(n); }
  } catch { /* painel desligado: o aviso de desligado já aparece */ }
}
const tentar = f => async (...a) => { try { return await f(...a); } catch (e) { avisar(e.message, true); } };
async function aguardarTarefa(id, aoAvancar) {
  for (;;) {
    const t = (await api('/api/tarefas')).find(x => x.id === id);
    if (!t) throw new Error('A tarefa foi perdida.');
    if (aoAvancar) aoAvancar(t);
    if (t.estado === 'ok') return t.resultado;
    if (t.estado === 'erro' || t.estado === 'cancelada') throw new Error(t.mensagem);
    await new Promise(r => setTimeout(r, 700));
  }
}

function irPara(tela, opcoes = {}) {
  if (tela !== G.tela && G.selecao) { G.selecao = null; barraSelecao(); }
  G.tela = tela;
  for (const [id] of TELAS) {
    $(`#tela-${id}`).hidden = id !== tela;
    $(`#nav-${id}`).ariaCurrent = id === tela || (id === 'descobrir' && tela === 'lives') ? 'page' : null;
  }
  if (tela !== 'editor' && window.Editor) Editor.pausar();
  if (tela !== 'descobrir' && window.Descobrir) Descobrir.sair();
  if (tela !== 'referencias' && window.Referencias) Referencias.sair();
  if (tela !== 'producao' && window.Producao) Producao.sair();
  pararEstudio();
  if (opcoes.modo) G.modoGerar = opcoes.modo;
  if (opcoes.aba) G.abaLives = opcoes.aba;
  ({ inicio: desenharInicio, lives: desenharLives, gerar: desenharGerar, cortes: desenharCortes, config: desenharConfig }[tela] || (() => {}))();
  if (tela === 'editor' && window.Editor) Editor.mostrar(opcoes.corte);
  if (tela === 'descobrir' && window.Descobrir) Descobrir.mostrar(opcoes);
  if (tela === 'referencias' && window.Referencias) Referencias.mostrar(opcoes);
  if (tela === 'producao' && window.Producao) Producao.mostrar(opcoes);
  window.scrollTo(0, 0);
}

/* ---------- dados ---------- */
async function carregarLives() { G.lives = await api('/api/lives'); }
const todosCortes = () => G.lives.flatMap(l => l.cortes.map(c => ({ ...c, live: l.titulo, pasta: l.pasta, plataforma: l.plataforma, streamer: l.streamer })));
async function atualizarFundo() {
  try {
    const [tarefas, canais] = await Promise.all([api('/api/tarefas'), api('/api/canais')]);
    const ativas = tarefas.filter(t => t.estado === 'fila' || t.estado === 'rodando');
    G.tarefas = tarefas; G.canais = canais;
    novosAvisos(canais.avisos || []);
    atualizarGravacao();
    $('#menu-fila').hidden = false;
    $('#menu-fila').textContent = ativas.length ? `Atividade · ${ativas.length}` : 'Atividade';
    $('#menu-fila').classList.toggle('ocupado', !!ativas.length || gravando());
    if (GA.dlg) { pintarAtividade(); api('/api/auto').then(r => { GA.auto = r.regras || []; pintarAtividade(); }).catch(() => {}); }
    if (G.tela === 'inicio') desenharPainelVivo();
    if (G.tela === 'lives' && G.abaLives !== 'vod') desenharCanais();
    if (G.tela === 'producao' && window.Producao) Producao.tick();
  } catch { /* o aviso de painel desligado já aparece */ }
  setTimeout(atualizarFundo, 2500);
}

/* ---------- início ---------- */
const CENA = `<svg class="cena" viewBox="0 0 1200 300" preserveAspectRatio="xMidYMid slice" aria-hidden="true"><defs>
<linearGradient id="ceu" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#160a38"/><stop offset=".45" stop-color="#5a1466"/><stop offset=".72" stop-color="#d42a7f"/><stop offset=".9" stop-color="#ff8a4c"/></linearGradient>
<linearGradient id="sol" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffe08a"/><stop offset="1" stop-color="#ff3d94"/></linearGradient>
<linearGradient id="mar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#6d1763"/><stop offset="1" stop-color="#0a0a22"/></linearGradient>
<linearGradient id="sombra" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#090a1e" stop-opacity=".94"/><stop offset=".55" stop-color="#090a1e" stop-opacity=".2"/><stop offset="1" stop-color="#090a1e" stop-opacity="0"/></linearGradient></defs>
<rect width="1200" height="300" fill="url(#ceu)"/><circle cx="850" cy="176" r="92" fill="url(#sol)"/>
<g fill="#5a1466"><rect x="740" y="172" width="220" height="5"/><rect x="740" y="190" width="220" height="7"/><rect x="740" y="209" width="220" height="9"/></g>
<path fill="#1c0d3f" d="M520 232v-44h26v-30h22v30h20v-58h30v58h18v-22h26v40h24v-76h28v76h22v-34h30v34h34v-20h24v20h30v-62h32v62h26v-40h28v40h26v-82h30v82h30v-30h34V232Z"/>
<g fill="#ff5fb0" opacity=".85"><rect x="594" y="142" width="4" height="4"/><rect x="606" y="156" width="4" height="4"/><rect x="694" y="130" width="4" height="4"/><rect x="706" y="148" width="4" height="4"/><rect x="908" y="176" width="4" height="4"/><rect x="1030" y="158" width="4" height="4"/><rect x="1044" y="176" width="4" height="4"/></g>
<g fill="#2de2e6" opacity=".8"><rect x="606" y="172" width="4" height="4"/><rect x="694" y="170" width="4" height="4"/><rect x="920" y="196" width="4" height="4"/><rect x="1030" y="196" width="4" height="4"/></g>
<rect y="232" width="1200" height="68" fill="url(#mar)"/>
<g fill="#ffb36b" opacity=".55"><rect x="790" y="240" width="120" height="3"/><rect x="760" y="254" width="180" height="3"/><rect x="800" y="270" width="100" height="3"/></g>
<g fill="#0a0820"><path d="M1098 300c8-60 10-100 6-150l8 1c6 50 4 90-4 149Z"/><path d="M1108 152c-24-22-58-22-82-2 28-8 54-6 82 2Zm0 0c24-24 58-24 84-6-30-6-56-4-84 6Zm-2 0c-30-6-58 8-70 38 20-20 42-32 70-38Zm4 0c30-4 58 12 68 42-20-22-42-36-68-42Zm-2-2c-8-24-30-36-54-34 22 8 40 18 54 34Zm2 0c10-24 32-34 56-30-24 6-42 16-56 30Z"/></g>
<rect width="1200" height="300" fill="url(#sombra)"/></svg>`;
function desenharInicio() {
  const t = $('#tela-inicio');
  const hero = el('section', { className: 'hero' });
  hero.innerHTML = CENA;
  hero.append(el('div', { className: 'hero-texto' }, el('h1', { textContent: 'Vice Clips' }),
    el('p', { textContent: 'Live ou gravação → escolha o momento → template → edite → exporte o Reel 1080x1920.' }),
    el('div', { className: 'hero-acoes' },
      el('button', { className: 'btn', type: 'button', textContent: 'Escolher momento de uma gravação', onclick: () => irPara('gerar', { modo: 'manual' }) }),
      el('button', { className: 'btn leve', type: 'button', textContent: 'Sugestões automáticas', onclick: () => irPara('gerar', { modo: 'auto' }) }),
      el('button', { className: 'btn leve', type: 'button', textContent: 'Abrir editor', onclick: () => irPara('editor') }),
      el('button', { className: 'btn leve', type: 'button', textContent: 'Lives ao vivo', onclick: () => irPara('descobrir', { aba: 'vivo' }) }),
      el('button', { className: 'btn leve', type: 'button', textContent: 'Clipes em alta', onclick: () => irPara('descobrir', { aba: 'clips' }) }))));
  const vivo = el('section', { className: 'card bloco' },
    el('div', { className: 'topo-linha', style: 'margin-bottom:10px' }, el('h2', { id: 'ini-vivo-tit', className: 'tit', style: 'margin:0', textContent: 'Ao vivo agora' }),
      el('span', { className: 'ferramentas', style: 'margin:0' },
        el('button', { className: 'btn leve mini', type: 'button', textContent: 'Ver todas as lives', onclick: () => irPara('descobrir', { aba: 'vivo' }) }),
        el('button', { className: 'btn leve mini', type: 'button', textContent: 'Clipes em alta', onclick: () => irPara('descobrir', { aba: 'clips' }) }),
        el('button', { className: 'btn leve mini', type: 'button', textContent: 'Favoritos', onclick: () => irPara('descobrir', { aba: 'favoritos' }) }),
        el('button', { className: 'btn leve mini', type: 'button', textContent: 'Monitoramento', onclick: () => irPara('descobrir', { aba: 'monitor' }) }))),
    el('div', { id: 'ini-vivo', className: 'ini-vivo-plats' }, el('p', { className: 'dica', style: 'margin:0', textContent: 'Consultando a Twitch e a Kick...' })));
  const cartaoIni = l => el('div', { className: 'ini-live' },
    el('a', { href: l.link, target: '_blank', rel: 'noopener', title: l.titulo }, l.thumb ? el('img', { src: l.thumb, alt: '', loading: 'lazy' }) : el('span', { className: 'sem-thumb' })),
    el('div', { className: 'ini-live-nome' }, el('b', { textContent: l.nome || l.login }), el('span', { className: 'selo', style: `--cor:${CORES[l.plataforma]}`, textContent: PLATAFORMA[l.plataforma] })),
    el('span', { textContent: `${fmtNum(l.espectadores)} assistindo` }),
    el('button', { className: 'btn leve mini', type: 'button', textContent: l.plataforma === 'kick' ? 'Gravar e clipar' : 'Analisar ao vivo',
      onclick: () => (window.Descobrir ? Descobrir.gravar(l.login, l.nome || l.login, l.inicio, l.plataforma) : irPara('descobrir')) }));
  api('/api/descobrir/estado').then(e => api(`/api/descobrir/lives?idioma=${encodeURIComponent(e.idioma || '')}${e.rp ? '&rp=1' : ''}`)).then(r => {
    if (!$('#ini-vivo')) return;
    $('#ini-vivo-tit').textContent = `Ao vivo agora · ${r.categoria.nome}${r.idioma ? ' · ' + r.idioma.toUpperCase() : ''}`;
    const linha = (rotulo, lives, vazioTxt) => [el('h3', { className: 'ini-plat' }, el('span', { className: 'selo', style: `--cor:${CORES[rotulo.toLowerCase()]}`, textContent: rotulo })),
      el('div', { className: 'ini-vivo' }, ...(lives.length ? lives.slice(0, 5).map(cartaoIni) : [el('p', { className: 'dica', style: 'margin:0', textContent: vazioTxt })]))];
    $('#ini-vivo').replaceChildren(...linha('Twitch', r.lives.map(l => ({ ...l, plataforma: 'twitch' })), 'Nenhuma live da Twitch nesta categoria agora.'),
      ...linha('Kick', r.kick || [], r.kick_erro || 'Nenhuma live da Kick nesta categoria agora.'));
  }).catch(e => { if ($('#ini-vivo')) $('#ini-vivo').replaceChildren(el('p', { className: 'dica', style: 'margin:0', textContent: `${e.message} `}, el('button', { className: 'btn leve mini', type: 'button', textContent: 'Abrir Lives', onclick: () => irPara('descobrir') }))); });
  const gravacao = el('section', { id: 'ini-gravacao', className: 'card bloco', hidden: !gravando() },
    el('div', { className: 'topo-linha', style: 'margin-bottom:10px' }, el('h2', { className: 'tit', style: 'margin:0', textContent: 'Gravando agora' }),
      el('button', { className: 'btn leve mini', type: 'button', textContent: 'Tela cheia', onclick: abrirEstudio })), el('div', { id: 'ini-gravacao-corpo' }));
  t.replaceChildren(hero, el('section', { id: 'numeros', className: 'numeros' }), gravacao, vivo,
    el('div', { className: 'duas' },
      el('section', {}, el('div', { className: 'topo-linha', style: 'margin-bottom:10px' }, el('h2', { className: 'tit', style: 'margin:0', textContent: 'Cortes recentes' }), botaoSelecionar()), el('div', { id: 'recentes', className: 'grade' })),
      el('div', { className: 'coluna' },
        el('section', { className: 'card bloco', style: 'margin:0' }, el('div', { className: 'topo-linha', style: 'margin-bottom:10px' }, el('h2', { className: 'tit', style: 'margin:0', textContent: 'Meus canais · ranking' }),
          el('button', { className: 'btn leve mini', type: 'button', textContent: 'Abrir', onclick: () => irPara('lives', { aba: 'vivo' }) })), el('div', { id: 'ini-canais', className: 'lista' })),
        el('section', { className: 'card bloco', style: 'margin:0' }, el('h2', { className: 'tit', textContent: 'Avisos' }), el('div', { id: 'ini-avisos', className: 'lista' })),
        el('section', { className: 'card bloco', style: 'margin:0' }, el('div', { className: 'topo-linha', style: 'margin-bottom:10px' }, el('h2', { className: 'tit', style: 'margin:0', textContent: 'Atividade' }),
          el('span', { className: 'ferramentas', style: 'margin:0' }, el('button', { className: 'btn leve mini', type: 'button', textContent: 'Por streamer', onclick: () => irPara('producao') }),
            el('button', { className: 'btn leve mini', type: 'button', textContent: 'Ver tudo', onclick: abrirAtividade }))), el('div', { id: 'ini-fila', className: 'lista' })))));
  if (GV.caps.length) pintarEstudio($('#ini-gravacao-corpo'));
  carregarLives().then(() => {
    const cortes = todosCortes();
    G.visiveis = cortes.slice(0, 8);
    $('#recentes').replaceChildren(...(G.visiveis.length ? G.visiveis.map((c, i) => cartao(c, i)) : [el('div', { className: 'vazio', textContent: 'Nenhum corte ainda. Comece em Gerar Cortes.' })]));
    desenharPainelVivo();
  }).catch(() => {});
}
function desenharPainelVivo() {
  if (!$('#numeros')) return;
  const cortes = todosCortes();
  const ativas = G.tarefas.filter(t => t.estado === 'fila' || t.estado === 'rodando');
  const ao = G.canais.canais.filter(c => c.online).length;
  const num = (v, r, c = '') => el('div', { className: 'card numero ' + c }, el('b', { textContent: v }), el('span', { textContent: r }));
  $('#numeros').replaceChildren(num(cortes.length, 'Cortes gerados'), num(cortes.reduce((s, c) => s + c.editados.length, 0), 'Reels editados'),
    num(`${ao}/${G.canais.canais.length}`, 'Lives ao vivo agora', 'ao-vivo'), num(ativas.length, 'Tarefas em andamento'));
  const ordem = [...G.canais.canais].sort((a, b) => (b.online ? 1 : 0) - (a.online ? 1 : 0) || (b.nota || 0) - (a.nota || 0));
  $('#ini-canais').replaceChildren(...(ordem.length ? ordem.slice(0, 6).map(c => el('div', { className: 'linha-item' },
    el('span', { className: 'ponto' + (c.online ? ' on' : '') }),
    el('span', { className: 'nome' }, c.login, el('small', { textContent: c.online ? `${c.nota !== undefined ? `Nota ${c.nota} · ` : ''}${c.jogo || c.titulo || 'Ao vivo'}` : c.online === false ? 'Offline' : (c.erro || 'Aguardando status') })),
    el('span', { className: 'selo', style: `--cor:${CORES[c.plataforma]}`, textContent: PLATAFORMA[c.plataforma] }),
    c.online ? el('span', { className: 'selo live', textContent: fmtNum(c.espectadores) }) : null))
    : [el('p', { className: 'dica', textContent: 'Adicione canais na tela Lives.' })]));
  const avisos = (G.canais.avisos || []).slice(0, 5);
  if ($('#ini-avisos')) $('#ini-avisos').replaceChildren(...(avisos.length ? avisos.map(linhaAviso) : [el('p', { className: 'dica', style: 'margin:0', textContent: 'Canal entrando ao vivo, audiência subindo, chat explodindo e rajada de clipes aparecem aqui.' })]));
  const itens = G.tarefas.slice(0, 5);
  $('#ini-fila').replaceChildren(...(itens.length ? itens.map(linhaTarefa) : [el('p', { className: 'dica', textContent: 'Nenhuma tarefa no momento.' })]));
}
const fmtNum = n => (n >= 1000 ? (n / 1000).toFixed(1).replace('.0', '') + 'k' : String(n || 0));
function linhaTarefa(t) {
  const cor = { ok: 'var(--ok)', erro: 'var(--erro)' }[t.estado] || 'var(--ciano)';
  return el('div', { className: 'linha-item' }, el('span', { className: 'nome' }, t.titulo,
    el('small', { textContent: t.mensagem, style: `color:${cor}` }),
    t.estado === 'rodando' ? el('div', { className: 'barra' }, el('i', { style: `width:${Math.round(t.progresso * 100)}%` })) : null));
}

/* ---------- galeria ---------- */
function cartao(c, i, aoAbrir) {
  const selo = el('span', { className: 'selo', textContent: c.plataforma });
  selo.style.setProperty('--cor', CORES[c.plataforma] || 'var(--suave)');
  /* Excluir marca o cartão; dá para marcar vários e excluir todos de uma vez pela barra de baixo. Nada se mexe na tela. */
  const marcado = () => !!(G.selecao && G.selecao.has(c.id));
  const caixa = el('input', { type: 'checkbox', checked: marcado(), onchange: () => marcar() });
  const rotuloCaixa = el('label', { className: 'marcar-corte', title: 'Marcar para excluir', hidden: !G.selecao }, caixa);
  const botaoExcluir = el('button', { className: 'btn leve mini perigo', type: 'button', textContent: marcado() ? 'Desmarcar' : 'Excluir', title: 'Marca para excluir. Marque quantos quiser e use a barra de baixo.', onclick: () => marcar() });
  const art = el('article', { className: 'card corte' + (marcado() ? ' marcado' : '') });
  function marcar() {
    if (!G.selecao) { G.selecao = new Set(); document.querySelectorAll('.marcar-corte').forEach(n => { n.hidden = false; }); }
    if (marcado()) G.selecao.delete(c.id); else G.selecao.add(c.id);
    art.classList.toggle('marcado', marcado()); caixa.checked = marcado(); botaoExcluir.textContent = marcado() ? 'Desmarcar' : 'Excluir';
    barraSelecao();
  }
  art.append(rotuloCaixa,
    el('button', { className: 'capa', type: 'button', ariaLabel: aoAbrir ? `Editar o corte com nota ${c.nota}` : `Assistir ao corte com nota ${c.nota}`, onclick: () => (G.selecao ? marcar() : aoAbrir ? aoAbrir() : abrirCorte(i)) },
      el('img', { src: c.thumb, alt: '', loading: 'lazy' }), c.nota === null || c.nota === undefined ? el('span', { className: 'marca manual', textContent: 'Manual', title: 'Trecho escolhido à mão' })
        : el('span', { className: 'marca', textContent: c.nota, title: 'Estimativa de relevância' }), selo,
      el('span', { className: 'tempo', textContent: `${c.duracao}s` }), c.editados.length ? el('span', { className: 'ed', textContent: `${c.editados.length} editado${c.editados.length > 1 ? 's' : ''}` }) : null),
    el('div', { className: 'corpo' },
      el('span', { className: 'quem', textContent: c.streamer || c.live, title: c.live }),
      el('span', { className: `estado ${c.estado}`, textContent: ESTADOS[c.estado] || '' }),
      el('p', { className: 'motivo', textContent: c.texto && c.manual ? c.texto : (c.motivo || c.texto) }),
      el('div', { className: 'acoes-corte' },
        el('button', { className: 'btn mini', type: 'button', textContent: 'Editar', onclick: () => irPara('editor', { corte: c.id }) }),
        el('a', { className: 'btn leve mini', href: c.url, download: c.arquivo, textContent: 'Baixar' }),
        el('button', { className: 'btn leve mini', type: 'button', textContent: 'Pasta', onclick: tentar(() => api('/api/abrir-pasta', { pasta: c.pasta })) }),
        botaoExcluir)));
  return art;
}
/* Excluir não pergunta: os arquivos vão para a lixeira do Vice Clips e o aviso traz Desfazer. */
function avisoDesfazer(texto, lixeiras) {
  const n = el('div', { className: 'aviso' }, texto, ' ', el('button', { className: 'btn leve mini', type: 'button', textContent: 'Desfazer', onclick: tentar(async () => {
    n.remove(); await api('/api/corte/restaurar', { lixeiras }); avisar('Restaurado.'); await carregarLives(); irPara(G.tela);
  }) }));
  $('#avisos').append(n); setTimeout(() => n.remove(), 10000);
}
const excluirCorte = tentar(async (c, editado) => {
  const r = await api('/api/corte/excluir', { cortes: [c.id], editado: editado || '' });
  if (G.selecao) G.selecao.delete(c.id);
  await carregarLives(); irPara(G.tela);
  avisoDesfazer(editado ? 'Reel excluído.' : 'Corte excluído.', r.lixeiras);
});
const excluirSelecionados = tentar(async () => {
  const ids = [...(G.selecao || [])]; if (!ids.length) return;
  const r = await api('/api/corte/excluir', { cortes: ids });
  G.selecao = null; await carregarLives(); irPara(G.tela); barraSelecao();
  avisoDesfazer(`${r.lixeiras.length} corte(s) excluído(s).${r.erros.length ? ` ${r.erros.length} com erro.` : ''}`, r.lixeiras);
});
/* Seleção em massa: os cartões ganham caixa de marcar e aparece a barra de ações. */
/* Liga ou desliga a seleção sem redesenhar a tela (não perde a rolagem). */
function alternarSelecao(ligar = !G.selecao) {
  G.selecao = ligar ? new Set() : null;
  document.querySelectorAll('.corte.marcado').forEach(n => n.classList.remove('marcado'));
  document.querySelectorAll('.marcar-corte').forEach(n => { n.hidden = !ligar; const i = n.querySelector('input'); if (i) i.checked = false; });
  document.querySelectorAll('.corte .perigo').forEach(b => { if (b.textContent === 'Desmarcar') b.textContent = 'Excluir'; });
  document.querySelectorAll('.botao-selecionar').forEach(b => { b.textContent = ligar ? 'Cancelar seleção' : 'Selecionar vários'; });
  barraSelecao();
}
function botaoSelecionar() { return el('button', { className: 'btn leve mini botao-selecionar', type: 'button', textContent: G.selecao ? 'Cancelar seleção' : 'Selecionar vários', onclick: () => alternarSelecao() }); }
function barraSelecao() {
  let b = $('#barra-selecao');
  if (!G.selecao) { if (b) b.remove(); return; }
  if (!b) { b = el('div', { id: 'barra-selecao', className: 'barra-selecao card' }); document.body.append(b); }
  const visiveis = (G.visiveis || []).map(c => c.id);
  b.replaceChildren(el('b', { textContent: `${G.selecao.size} selecionado(s)` }),
    el('button', { className: 'btn leve mini', type: 'button', textContent: 'Marcar todos da tela', onclick: () => {
      document.querySelectorAll('.corte:not(.marcado) .perigo').forEach(b => { if (b.textContent === 'Excluir') b.click(); });
    } }),
    el('button', { className: 'btn mini perigo-forte', type: 'button', textContent: 'Excluir selecionados', disabled: !G.selecao.size, onclick: excluirSelecionados }),
    el('button', { className: 'btn leve mini', type: 'button', textContent: 'Cancelar', onclick: () => alternarSelecao(false) }));
}
async function desenharCortes() {
  await Promise.all([carregarLives().catch(() => {}), recarregarCanais().catch(() => {})]);
  const f = G.filtro;
  const todos = todosCortes();
  const plataformas = ['Todas', ...new Set(['Twitch', 'Kick', 'YouTube', 'Arquivos', ...todos.map(c => c.plataforma)])];
  const streamers = [...new Set(todos.map(c => c.streamer).filter(Boolean))].sort();
  let lista = todos.filter(c => (f.plataforma === 'Todas' || c.plataforma === f.plataforma) && (!f.streamer || c.streamer === f.streamer) && (f.estado === 'todos' || c.estado === f.estado));
  if (f.ordem === 'nota') lista = [...lista].sort((a, b) => (b.nota ?? -1) - (a.nota ?? -1));
  G.visiveis = lista;
  const soLink = G.canais.clips.filter(c => !c.importado);
  const reels = todos.flatMap(c => c.editados.map(e => ({ ...e, corte: c }))).sort((a, b) => (b.criado || 0) - (a.criado || 0));
  const conta = { todos: todos.length, pronto: 0, editando: 0, exportado: 0, link: soLink.length };
  todos.forEach(c => { conta[c.estado] = (conta[c.estado] || 0) + 1; });
  const seletor = (rotulo, valor, opcoes, mudar) => el('label', {}, rotulo, el('select', { onchange: e => { mudar(e.target.value); desenharCortes(); } },
    ...opcoes.map(([v, t]) => el('option', { value: v, textContent: t, selected: v === valor }))));
  const chips = [['todos', 'Todos'], ['link', 'Clip na Twitch (só link)'], ['pronto', 'Pronto para editar'], ['editando', 'Em edição'], ['exportado', 'Reel exportado']];
  const corpo = [];
  if (f.estado === 'link') {
    corpo.push(soLink.length ? el('div', { className: 'grade' }, ...soLink.map(cartaoClip)) : el('div', { className: 'vazio', textContent: 'Nenhum clip sem arquivo local.' }));
  } else {
    if ((f.estado === 'todos' || f.estado === 'exportado') && reels.length) {
      corpo.push(el('h2', { className: 'tit', textContent: 'Reels exportados' }), el('div', { className: 'grade reels' }, ...reels.slice(0, f.estado === 'exportado' ? 60 : 8).map(cartaoReel)),
        el('h2', { className: 'tit', style: 'margin-top:18px', textContent: 'Cortes' }));
    }
    corpo.push(lista.length ? el('div', { className: 'grade' }, ...lista.map((c, i) => cartao(c, i))) : el('div', { className: 'vazio' }, el('p', { textContent: 'Nenhum corte com esses filtros.' })));
  }
  $('#tela-cortes').replaceChildren(...[
    el('header', { className: 'cabeca topo-linha' }, el('div', {}, el('h1', { textContent: 'Meus Cortes' }), el('p', { textContent: `${todos.length} cortes · ${reels.length} reels exportados · ${soLink.length} clips só com link` })), f.estado === 'link' ? null : botaoSelecionar()),
    el('div', { className: 'filtros' }, ...chips.map(([id, t]) => el('button', { className: 'chip', type: 'button', textContent: `${t} (${conta[id] || 0})`, ariaPressed: String(id === f.estado), onclick: () => { f.estado = id; desenharCortes(); } }))),
    f.estado === 'link' ? null : el('div', { className: 'filtros' }, ...plataformas.map(p => el('button', { className: 'chip', type: 'button', textContent: p, ariaPressed: String(p === f.plataforma), onclick: () => { f.plataforma = p; desenharCortes(); } })),
      seletor('Streamer', f.streamer, [['', 'Todos'], ...streamers.map(s => [s, s])], v => { f.streamer = v; }),
      seletor('Ordenar', f.ordem, [['recentes', 'Mais recentes'], ['nota', 'Maior nota']], v => { f.ordem = v; })),
    ...corpo].filter(Boolean));
}
function cartaoReel(e) {
  const c = e.corte;
  return el('article', { className: 'card corte reel' },
    el('button', { className: 'capa', type: 'button', ariaLabel: 'Assistir ao Reel', onclick: () => verReel(e) }, el('img', { src: e.thumb, alt: '', loading: 'lazy' }),
      el('span', { className: 'tempo', textContent: `${Math.round(e.duracao)}s` }), el('span', { className: 'ed', textContent: 'Reel' })),
    el('div', { className: 'corpo' }, el('span', { className: 'quem', textContent: `${c.streamer || c.live} · ${e.arquivo}` }),
      el('div', { className: 'acoes-corte' },
        el('button', { className: 'btn mini', type: 'button', textContent: 'Assistir', onclick: () => verReel(e) }),
        el('button', { className: 'btn leve mini', type: 'button', textContent: 'Editar', onclick: () => irPara('editor', { corte: c.id }) }),
        el('a', { className: 'btn leve mini', href: e.url, download: e.arquivo, textContent: 'Baixar' }),
        el('button', { className: 'btn leve mini perigo', type: 'button', textContent: 'Excluir', title: 'Exclui só este Reel exportado', onclick: () => excluirCorte(c, e.arquivo) }))));
}
function verReel(e) {
  const d = el('dialog', { className: 'pronto', style: 'width:min(460px,calc(100vw - 32px))' });
  const v = el('video', { src: e.url, controls: true, autoplay: true, playsInline: true });
  d.append(v, el('div', { className: 'acoes', style: 'padding:12px;grid-template-columns:1fr 1fr 1fr 1fr' },
    el('a', { className: 'btn', href: e.url, download: e.arquivo, textContent: 'Baixar' }),
    e.fonte_url ? el('button', { className: 'btn leve', type: 'button', textContent: 'Comparar', onclick: () => { d.close(); compararReel(e); } }) : null,
    el('button', { className: 'btn leve', type: 'button', textContent: 'Pasta', onclick: tentar(() => api('/api/abrir-pasta', { pasta: e.pasta })) }),
    el('button', { className: 'btn leve', type: 'button', textContent: 'Fechar', onclick: () => d.close() })));
  d.addEventListener('close', () => { v.pause(); d.remove(); });
  document.body.append(d); d.showModal();
}
function abrirCorte(i) {
  G.atual = (i + G.visiveis.length) % G.visiveis.length;
  const c = G.visiveis[G.atual];
  $('#tela-video').src = c.url;
  $('#p-nota').textContent = c.nota === null || c.nota === undefined ? 'Corte manual' : `Nota ${c.nota}`;
  $('#p-dados').replaceChildren(...[['Live', c.live], ['Streamer', c.streamer || '-'], ['Momento', c.momento || '-'], ['Duração', `${c.duracao} segundos`]].flatMap(([a, b]) => [el('dt', { textContent: a }), el('dd', { textContent: b })]));
  $('#p-motivo').textContent = c.motivo || '';
  $('#p-fala').textContent = c.texto;
  $('#p-baixar').href = c.url; $('#p-baixar').download = c.arquivo;
  $('#p-editados').replaceChildren(...c.editados.map(e => el('div', { className: 'linha-item' }, el('span', { className: 'nome', textContent: e.arquivo }),
    el('button', { className: 'btn leve mini', type: 'button', textContent: 'Ver', onclick: () => { $('#tela-video').src = e.url; $('#tela-video').play().catch(() => {}); } }),
    el('a', { className: 'btn leve mini', href: e.url, download: e.arquivo, textContent: 'Baixar' }))));
  if (!$('#player').open) $('#player').showModal();
  $('#tela-video').play().catch(() => {});
}

/* ---------- lives ---------- */
/* Lives e Descobrir são uma página só: a mesma fila de abas aparece nas duas telas. */
const ABAS_LIVES = [['vivo', 'Ao vivo agora'], ['clips', 'Clipes em alta'], ['favoritos', 'Favoritos'], ['monitor', 'Monitoramento'], ['canais', 'Meus canais'], ['criados', 'Clips criados']];
function abrirAbaLives(id) {
  if (id === 'canais') irPara('lives', { aba: 'vivo' }); else if (id === 'criados') irPara('lives', { aba: 'clips' }); else irPara('descobrir', { aba: id });
}
function abasLives(atual) {
  return el('div', { className: 'filtros', role: 'tablist' }, ...ABAS_LIVES.map(([id, t]) => el('button', { className: 'chip', type: 'button', role: 'tab', textContent: id === 'criados' ? `${t} (${G.canais.clips.length})` : t, ariaPressed: String(id === atual), onclick: () => abrirAbaLives(id) })));
}
function desenharLives() {
  if (G.abaLives === 'vod') G.abaLives = 'vivo';
  const aba = G.abaLives;
  const corpo = el('div', { id: 'lives-corpo' });
  $('#tela-lives').replaceChildren(
    el('header', { className: 'cabeca' }, el('h1', { textContent: 'Lives' }), el('p', { textContent: 'Quem está ao vivo, clipes em alta, seus favoritos, os canais que você acompanha e os clips que você criou.' })),
    abasLives(aba === 'clips' ? 'criados' : 'canais'),
    corpo);
  if (aba === 'vod') { desenharEstudio(corpo); return; }
  if (aba === 'clips') {
    corpo.replaceChildren(el('div', { className: 'tres' },
      el('div', { className: 'card' }, el('h3', { textContent: 'Só link' }), el('p', { textContent: 'Clip existe na Twitch, mas o arquivo não está no PC. Assista pelo player ou abra o link.' })),
      el('div', { className: 'card' }, el('h3', { textContent: 'Baixar arquivo (oficial)' }), el('p', { textContent: 'A Twitch libera o arquivo só ao dono do canal e aos editores nomeados por ele.' })),
      el('div', { className: 'card' }, el('h3', { textContent: 'Importar arquivo autorizado' }), el('p', { textContent: 'Recebeu o arquivo do criador? Escolha o arquivo e ele vira um corte editável.' }))),
      el('div', { id: 'lista-clips', className: 'grade' }));
    desenharCanais();
    return;
  }
  corpo.replaceChildren(
    el('form', { className: 'card bloco add-canal', onsubmit: tentar(async e => {
      e.preventDefault();
      await api('/api/canais/adicionar', { plataforma: $('#novo-plat').value, login: $('#novo-login').value });
      $('#novo-login').value = ''; avisar('Canal adicionado.');
      await recarregarCanais();
    }) },
      el('label', {}, 'Plataforma', el('select', { id: 'novo-plat' }, el('option', { value: 'twitch', textContent: 'Twitch' }), el('option', { value: 'kick', textContent: 'Kick' }))),
      el('label', {}, 'Canal', el('input', { id: 'novo-login', required: true, placeholder: 'nome do canal ou link', autocomplete: 'off' })),
      el('button', { className: 'btn', type: 'submit', textContent: 'Adicionar' })),
    el('div', { className: 'duas', style: 'margin-bottom:16px' },
      el('section', { className: 'card bloco', style: 'margin:0' }, el('h2', { className: 'tit', textContent: 'Top 5 ao vivo agora' }), el('div', { id: 'lista-top', className: 'top-vivo' }),
        el('p', { className: 'dica', textContent: 'Nota de 0 a 100 entre os seus canais ao vivo: audiência, crescimento em ~10 min, mensagens por minuto no chat e clipes dos últimos 30 min. Na Kick a nota usa só audiência e crescimento, porque a API oficial dela não entrega chat nem clipes.' })),
      el('section', { className: 'card bloco', style: 'margin:0' }, el('div', { className: 'topo-linha', style: 'margin-bottom:10px' }, el('h2', { className: 'tit', style: 'margin:0', textContent: 'Avisos' }), botaoNotificar()),
        el('div', { id: 'lista-avisos', className: 'lista' }))),
    el('div', { id: 'lista-canais', className: 'canais' }),
    el('div', { className: 'tres', style: 'margin-top:16px' },
      el('div', { className: 'card' }, el('h3', { textContent: 'Criar clip' }), el('p', { textContent: 'Canal da Twitch ao vivo que permite clips, com sua conta conectada. O clip aparece em Clips criados.' })),
      el('div', { className: 'card' }, el('h3', { textContent: 'Arquivo do clip' }), el('p', { textContent: 'Só sai da Twitch para o dono do canal e editores. Nos demais, o clip fica como link.' })),
      el('div', { className: 'card' }, el('h3', { textContent: 'Depois da live' }), el('p', {}, 'Para cortar a gravação, use ', el('button', { className: 'btn leve mini', type: 'button', textContent: 'Gerar Cortes', onclick: () => irPara('gerar', { modo: 'manual' }) }), ' e cole o link da live encerrada.'))));
  desenharCanais();
}
/* ---------- Atividade: tudo o que o Vice Clips está fazendo, com progresso, cancelar, assistir e excluir ---------- */
const GA = { dlg: null, estrutura: '', recarregou: 0 };
const NOMES_TAREFA = { fila: 'Na fila', rodando: 'Fazendo agora', ok: 'Pronto', erro: 'Erro', cancelada: 'Cancelada' };
function verVideo(url, titulo) {
  const d = el('dialog', { className: 'pronto', style: 'width:min(460px,calc(100vw - 32px))' });
  const v = el('video', { src: url, controls: true, autoplay: true, playsInline: true, title: titulo || '' });
  d.append(v, el('div', { className: 'acoes', style: 'padding:12px' }, el('button', { className: 'btn leve', type: 'button', textContent: 'Fechar', onclick: () => d.close() })));
  d.addEventListener('close', () => { v.pause(); d.remove(); });
  document.body.append(d); d.showModal();
}
const corteDaTarefa = t => { const id = t.resultado && t.resultado.corte; return id ? (todosCortes().find(c => c.id === id) || { id }) : null; };
function itemAtividade(t) {
  const c = corteDaTarefa(t), reel = t.resultado && t.resultado.exportado, pct = Math.round((t.progresso || 0) * 100), andando = t.estado === 'fila' || t.estado === 'rodando';
  const item = el('div', { className: `at-item at-${t.estado}` },
    c && c.thumb ? el('img', { className: 'at-thumb', src: c.thumb, alt: '', loading: 'lazy' }) : el('span', { className: 'at-thumb vazio', textContent: t.estado === 'rodando' ? `${pct}%` : NOMES_TAREFA[t.estado] || '' }),
    el('div', { className: 'at-info' }, el('b', { textContent: t.titulo, title: t.titulo }),
      el('small', { className: 'at-msg', textContent: `${NOMES_TAREFA[t.estado] || t.estado} · ${t.mensagem}${t.estado === 'rodando' ? ` · ${pct}%` : ''}` }),
      andando ? el('div', { className: 'barra' }, el('i', { style: `width:${t.estado === 'rodando' ? pct : 0}%` })) : null,
      t.resultado && t.resultado.aviso ? el('small', { className: 'at-aviso', textContent: t.resultado.aviso }) : null),
    el('div', { className: 'at-acoes' },
      andando && !t.cancelando ? el('button', { className: 'btn leve mini perigo', type: 'button', textContent: 'Cancelar', title: t.estado === 'rodando' ? 'Para na próxima etapa (um download ou render já em andamento termina antes)' : 'Tira da fila',
        onclick: tentar(async () => { await api('/api/tarefas/cancelar', { id: t.id }); avisar('Cancelando.'); }) }) : null,
      c && c.url ? el('button', { className: 'btn leve mini', type: 'button', textContent: 'Assistir', onclick: () => verVideo(c.url, t.titulo) }) : null,
      reel && reel.url ? el('button', { className: 'btn leve mini', type: 'button', textContent: 'Assistir Reel', onclick: () => verVideo(reel.url, t.titulo) }) : null,
      c ? el('button', { className: 'btn mini', type: 'button', textContent: 'Abrir no editor', onclick: () => { if (GA.dlg) GA.dlg.close(); irPara('editor', { corte: c.id }); } }) : null,
      c && c.url ? el('button', { className: 'btn leve mini perigo', type: 'button', textContent: 'Excluir', title: 'Exclui o corte (vai para a lixeira do Vice Clips)',
        onclick: confirmarClique('Confirmar', tentar(async () => { await api('/api/corte/excluir', { cortes: [c.id] }); avisar('Corte excluído.'); await carregarLives(); pintarAtividade(true); })) }) : null));
  item.dataset.id = t.id;
  return item;
}
function itemGravacao(c) {
  const item = el('div', { className: 'at-item at-gravacao' + (vivo(c) ? ' at-rodando' : '') }, el('span', { className: 'at-thumb vazio', textContent: vivo(c) ? 'REC' : '■' }),
    el('div', { className: 'at-info' }, el('b', { textContent: `${vivo(c) ? 'Gravando' : NOMES_CAP[c.estado] || c.estado} ${c.login} (${PLATAFORMA[c.plataforma || 'twitch']})` }),
      el('small', { className: 'at-msg', textContent: resumoCap(c) })),
    el('div', { className: 'at-acoes' },
      vivo(c) ? el('button', { className: 'btn mini', type: 'button', textContent: 'Clipar 30 s', onclick: clipar(c.login, 30) }) : null,
      el('button', { className: 'btn leve mini', type: 'button', textContent: 'Assistir e momentos', onclick: () => { if (GA.dlg) GA.dlg.close(); abrirEstudio(c.login); } }),
      vivo(c) ? el('button', { className: 'btn leve mini perigo', type: 'button', textContent: 'Parar', onclick: pararGravacao(c.login) }) : null));
  item.dataset.login = c.login;
  return item;
}
/* Automáticos: regras que geram conteúdo sozinhas de tempos em tempos (criadas em Clipes em alta → Automático). */
GA.auto = [];
const horaCurta = t => new Date(t * 1000).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
function itemAuto(r) {
  const u = r.ultima, freq = r.a_cada >= 60 ? `${r.a_cada / 60} h` : `${r.a_cada} min`;
  const fazer = acao => tentar(async () => { const x = await api('/api/auto/acao', { id: r.id, acao }); GA.auto = x.regras; pintarAtividade(true); if (acao === 'agora') avisar('Rodando agora: os clipes novos entram em "Fazendo agora".'); });
  const ultima = !u ? 'ainda não rodou' : u.erro ? `última às ${horaCurta(u.quando)}: erro (${u.erro})`
    : `última às ${horaCurta(u.quando)}: ${u.novos ? `${u.novos} clipe${u.novos === 1 ? '' : 's'} novo${u.novos === 1 ? '' : 's'} (${u.clipes.map(c => `${c.views} views`).join(', ')})` : 'nenhum clipe novo acima do mínimo'}`;
  return el('div', { className: 'at-item' + (r.ativo ? ' at-rodando' : ' at-cancelada') }, el('span', { className: 'at-thumb vazio', textContent: r.ativo ? 'AUTO' : 'PAUSADO' }),
    el('div', { className: 'at-info' }, el('b', { textContent: r.nome, title: r.nome }),
      el('small', { textContent: `A cada ${freq} · ${r.quantos} clipes por vez · mínimo de ${r.minimo} visualizações · ${r.n_feitos} clipes já pegos${r.quem === 'comunidade' ? ' · só de espectadores' : r.quem === 'proprio' ? ' · só do próprio streamer' : ''}` }),
      el('small', { className: 'at-msg', textContent: [r.ativo ? `próxima rodada às ${horaCurta(r.proxima)}` : 'pausado', ultima].join(' · ') })),
    el('div', { className: 'at-acoes' },
      el('button', { className: 'btn mini', type: 'button', textContent: 'Rodar agora', onclick: fazer('agora') }),
      el('button', { className: 'btn leve mini', type: 'button', textContent: r.ativo ? 'Pausar' : 'Retomar', onclick: fazer(r.ativo ? 'pausar' : 'retomar') }),
      el('button', { className: 'btn leve mini perigo', type: 'button', textContent: 'Excluir', onclick: confirmarClique('Confirmar', fazer('excluir')) })));
}
/* Análise de uma gravação (ao vivo ou guardada): progresso, momentos pela nota e criar cortes dos melhores. */
const NOMES_ANALISE = { iniciando: 'Começando a análise', rodando: 'Analisando', concluida: 'Análise concluída', parada: 'Análise parada', erro: 'Erro na análise' };
GA.pedidos = {};
/* a: estado de uma análise; c: a gravação dona dela (null para a análise de uma gravação guardada). */
function itensAnalise(a, c) {
  if (!a || !a.arquivo || !a.estado) return [];
  const nomeArq = a.arquivo.split(/[\\/]/).pop(), streamer = nomeArq.split('_')[0];
  const sug = (a.sugestoes || []).map((s, i) => ({ ...s, i })).sort((x, y) => y.nota - x.nota);
  const feitos = (c && c.feitos) || {};
  const corteDe = s => feitos[`analise:${Math.round(s.pico * 10)}`];
  const pedir = async s => { GA.pedidos[`${a.arquivo}:${s.pico}`] = 1;
    await api(c ? '/api/descobrir/aovivo/corte-analise' : '/api/descobrir/analise/corte', c ? { login: c.login, indice: s.i } : { indice: s.i, streamer }); };
  const pedido = s => GA.pedidos[`${a.arquivo}:${s.pico}`];
  const btn = (texto, fn, classe = 'btn leve mini') => el('button', { className: classe, type: 'button', textContent: texto, onclick: tentar(fn) });
  const livres = sug.filter(s => !corteDe(s) && !pedido(s));
  const cab = el('div', { className: 'at-item' + (a.rodando ? ' at-rodando' : '') }, el('span', { className: 'at-thumb vazio', textContent: a.rodando ? 'ANALISANDO' : 'ANÁLISE' }),
    el('div', { className: 'at-info' }, el('b', { textContent: `${NOMES_ANALISE[a.estado] || a.estado} · ${nomeArq}` }),
      el('small', { className: 'at-msg', textContent: [`analisado até ${tempoVivo(a.processado)}`, `${a.janelas || 0} janelas de ${a.janela || 25} s`, `${sug.length} momento${sug.length === 1 ? '' : 's'}`, a.estado === 'erro' ? a.mensagem : ''].filter(Boolean).join(' · ') })),
    el('div', { className: 'at-acoes' },
      livres.length ? btn(livres.length === 1 ? 'Criar corte do melhor' : `Criar cortes dos ${Math.min(5, livres.length)} melhores`, async () => {
        for (const s of livres.slice(0, 5)) await pedir(s);
        avisar('Os melhores momentos estão na fila: acompanhe em "Fazendo agora" e depois em "Prontos".'); G.tarefas = await api('/api/tarefas'); pintarAtividade(true);
      }, 'btn mini') : null,
      a.rodando && !c ? btn('Parar análise', async () => { await api('/api/descobrir/analise/parar', {}); atualizarGravacao(); }, 'btn leve mini perigo') : null));
  const linhas = sug.slice(0, 15).map(s => el('div', { className: 'at-item at-momento' }, el('span', { className: 'dc-nota', textContent: s.nota, title: 'Nota do momento: estimativa de relevância, não prevê alcance' }),
    el('div', { className: 'at-info' }, el('b', { textContent: `${tempoVivo(s.pico)} da gravação · corte de ${Math.round(s.fim - s.inicio)} s` }),
      el('small', { textContent: (s.motivos || []).join(' · ') + (s.fala ? ` · “${s.fala}”` : '') })),
    el('div', { className: 'at-acoes' }, corteDe(s) ? el('button', { className: 'btn mini', type: 'button', textContent: 'Abrir no editor', onclick: () => { if (GA.dlg) GA.dlg.close(); irPara('editor', { corte: corteDe(s) }); } })
      : pedido(s) ? el('span', { className: 'dica', style: 'margin:0', textContent: 'na fila (veja abaixo)' })
      : btn('Criar corte', async () => { await pedir(s); avisar(`Corte de ${tempoVivo(s.pico)} na fila.`); G.tarefas = await api('/api/tarefas'); pintarAtividade(true); }))));
  return [cab, ...linhas];
}
/* Redesenha a lista só quando muda o que há nela; o progresso de cada item é atualizado no lugar (não some o botão no meio do clique). */
function pintarAtividade(forcar = false) {
  const caixa = $('#atividade-corpo');
  if (!caixa) return;
  const ts = G.tarefas || [];
  const faltaCorte = ts.some(t => t.estado === 'ok' && t.resultado && t.resultado.corte && !todosCortes().some(c => c.id === t.resultado.corte));
  if (faltaCorte && Date.now() - GA.recarregou > 5000) { GA.recarregou = Date.now(); carregarLives().then(() => pintarAtividade(true)).catch(() => {}); }
  const an = GV.analise || {}, resumoAn = a => [a.arquivo, a.estado, a.janelas, (a.sugestoes || []).length];
  const estrutura = JSON.stringify([ts.map(t => [t.id, t.estado, !!t.cancelando, !!corteDaTarefa(t), t.resultado && t.resultado.aviso]), G.lives.length, resumoAn(an), Object.keys(GA.pedidos).length,
    GV.caps.map(c => [c.arquivo, vivo(c), resumoAn(c.analise || {}), JSON.stringify(c.feitos || {})]), JSON.stringify(GA.auto)]);
  if (!forcar && estrutura === GA.estrutura) {
    ts.forEach(t => {
      const item = caixa.querySelector(`[data-id="${t.id}"]`);
      if (!item) return;
      const pct = Math.round((t.progresso || 0) * 100), msg = item.querySelector('.at-msg'), barra = item.querySelector('.barra i'), vazio = item.querySelector('.at-thumb.vazio');
      if (msg) msg.textContent = `${NOMES_TAREFA[t.estado] || t.estado} · ${t.mensagem}${t.estado === 'rodando' ? ` · ${pct}%` : ''}`;
      if (barra && t.estado === 'rodando') barra.style.width = `${pct}%`;
      if (vazio && t.estado === 'rodando') vazio.textContent = `${pct}%`;
    });
    caixa.querySelectorAll('.at-gravacao').forEach(g => { const c = capDe(g.dataset.login), m = g.querySelector('.at-msg'); if (c && m) m.textContent = resumoCap(c); });
    return;
  }
  GA.estrutura = estrutura;
  const andando = ts.filter(t => t.estado === 'fila' || t.estado === 'rodando').reverse(), prontos = ts.filter(t => t.estado === 'ok'), outros = ts.filter(t => t.estado === 'erro' || t.estado === 'cancelada');
  const secao = (titulo, itens, vazioTxt) => el('section', { className: 'at-secao' }, el('h3', { className: 'tit', textContent: titulo }),
    ...(itens.length ? itens : [el('p', { className: 'dica', style: 'margin:0', textContent: vazioTxt })]));
  const analises = [...GV.caps.flatMap(c => itensAnalise(c.analise, c)), ...itensAnalise(an, null)];
  caixa.replaceChildren(...[
    secao(`Automáticos (${GA.auto.filter(r => r.ativo).length} ligados)`, GA.auto.map(itemAuto), 'Nenhum automático. Em Lives → Clipes em alta, filtre (canal, período, quem clipou) e clique em Automático para gerar conteúdo sozinho de tempos em tempos.'),
    secao(`Gravações ao vivo (${GV.caps.filter(vivo).length} gravando)`, GV.caps.map(itemGravacao), 'Nada sendo gravado. Para gravar, use Gravar e clipar (Kick) ou Analisar ao vivo (Twitch) em uma live. Dá para gravar até 4 lives juntas.'),
    secao('Momentos encontrados (pela nota)', analises, 'Nenhuma análise. Ela roda junto com cada gravação, ou em Configurações → Espaço em disco → Analisar, numa gravação guardada.'),
    secao(`Fazendo agora e na fila (${andando.length})`, andando.map(itemAtividade), 'Nada em andamento. Downloads de clipes, cortes e renders aparecem aqui com o progresso.'),
    secao(`Prontos (${prontos.length})`, prontos.map(itemAtividade), 'O que ficar pronto aparece aqui para você assistir, abrir no editor ou excluir.'),
    outros.length ? secao(`Com erro ou cancelados (${outros.length})`, outros.map(itemAtividade), '') : null].filter(Boolean));
}
function abrirAtividade() {
  if (GA.dlg) return;
  const d = el('dialog', { className: 'estudio-dlg atividade-dlg' });
  GA.dlg = d; GA.estrutura = '';
  d.append(el('div', { className: 'topo-linha', style: 'padding:12px 16px 0;flex-wrap:wrap' }, el('h2', { className: 'tit', style: 'margin:0', textContent: 'Atividade' }),
    el('span', { className: 'ferramentas', style: 'margin:0' },
      el('button', { className: 'btn mini', type: 'button', textContent: 'Ver por streamer', title: 'Página Produção: cada streamer com os cortes separados por origem e o motivo de cada um', onclick: () => { d.close(); irPara('producao'); } }),
      el('button', { className: 'btn leve mini', type: 'button', textContent: 'Limpar concluídos', title: 'Tira da lista o que já terminou. Os cortes continuam em Meus Cortes.', onclick: tentar(async () => { await api('/api/tarefas/limpar', {}); G.tarefas = await api('/api/tarefas'); pintarAtividade(true); }) }),
      el('button', { className: 'btn leve mini', type: 'button', textContent: 'Espaço em disco', onclick: () => { d.close(); irPara('config'); setTimeout(() => { const s = $('#cfg-espaco'); if (s) s.scrollIntoView({ behavior: 'smooth' }); }, 500); } }),
      el('button', { className: 'btn leve mini', type: 'button', textContent: 'Fechar', onclick: () => d.close() }))),
    el('div', { id: 'atividade-corpo', className: 'atividade' }));
  d.addEventListener('close', () => { d.remove(); GA.dlg = null; });
  document.body.append(d); d.showModal();
  pintarAtividade(true);
  api('/api/auto').then(r => { GA.auto = r.regras || []; pintarAtividade(true); }).catch(() => {});
}
window.abrirAtividade = abrirAtividade;

/* ---------- gravação ao vivo: várias lives ao mesmo tempo; barra em todas as telas + estúdio (player, momentos, Clipar agora) ---------- */
const GV = { caps: [], analise: null, vistos: null, barra: null, fechadas: new Set() };
const NOMES_CAP = { conectando: 'Conectando à live', gravando: 'Gravando', encerrada: 'A live acabou ou caiu', parada: 'Gravação parada', erro: 'Erro na gravação' };
const tempoVivo = t => { t = Math.max(0, Math.round(t || 0)); const h = Math.floor(t / 3600), m = Math.floor(t % 3600 / 60), s = t % 60; return `${h ? h + ':' + String(m).padStart(2, '0') : m}:${String(s).padStart(2, '0')}`; };
function avisoComBotao(texto, rotulo, fn) {
  const n = el('div', { className: 'aviso' }, texto, ' ', el('button', { className: 'btn leve mini', type: 'button', textContent: rotulo, onclick: () => { n.remove(); fn(); } }));
  $('#avisos').append(n); setTimeout(() => n.remove(), 15000);
}
async function esperarCorte(t, texto) {
  avisar(`${texto}: na fila. Acompanhe na Atividade.`);
  const r = await aguardarTarefa(t.id);
  avisoComBotao(`${texto}: pronto.`, 'Abrir no editor', () => irPara('editor', { corte: r.corte }));
  atualizarGravacao();
}
const vivo = c => !!(c && c.login && (c.rodando || c.estado === 'conectando'));
const gravando = () => GV.caps.some(vivo);
const capDe = login => GV.caps.find(c => c.login === login);
const clipar = (login, seg) => tentar(async () => esperarCorte(await api('/api/descobrir/aovivo/clipar', { login, segundos: seg }), `Clip de ${login} (últimos ${seg} s)`));
const pararGravacao = login => tentar(async () => { await api('/api/descobrir/aovivo/parar', { login }); atualizarGravacao(); });
const resumoCap = c => c.erro || [PLATAFORMA[c.plataforma || 'twitch'], `${c.minutos} min`, `${c.mb} MB`, c.chat && c.chat.lido ? `chat ${fmtNum(c.chat.msgs_min)}/min` : '',
  `${momentosDe(c).length} momentos`, c.auto ? `clipa sozinho ≥ ${c.auto}` : ''].filter(Boolean).join(' · ');
/* Momentos de uma gravação: do chat (Twitch) e da análise de voz e imagem dela, o mais recente primeiro. */
function momentosDe(c) {
  if (!c || !c.login) return [];
  const chat = ((c.chat || {}).momentos || []).filter(m => m.fim !== undefined).map(m => ({ ...m, fonte: 'chat', criar: () => api('/api/descobrir/aovivo/momento', { login: c.login, indice: m.indice }) }));
  const a = c.analise || {};
  const analise = (a.sugestoes || []).map((s, i) => ({ ...s, fonte: 'analise', corte: (c.feitos || {})[`analise:${Math.round(s.pico * 10)}`],
    criar: () => api('/api/descobrir/aovivo/corte-analise', { login: c.login, indice: i }) }));
  return [...chat, ...analise].sort((x, y) => y.pico - x.pico);
}
function linhaMomento(m) {
  return el('div', { className: 'linha-item' }, el('span', { className: 'dc-nota', textContent: m.nota, title: 'Nota do momento (estimativa, não prevê alcance)' }),
    el('span', { className: 'nome' }, `${tempoVivo(m.pico)} da gravação · ${m.fonte === 'chat' ? 'chat' : 'voz e imagem'}`,
      el('small', { textContent: (m.motivos || []).join(' · ') + (m.fala ? ` · “${m.fala}”` : ''), title: (m.motivos || []).join(' · ') })),
    m.corte ? el('button', { className: 'btn mini', type: 'button', textContent: 'Abrir no editor', onclick: () => irPara('editor', { corte: m.corte }) })
      : m.corte === '' ? el('span', { className: 'dica', style: 'margin:0', textContent: 'criando...' })
      : el('button', { className: 'btn leve mini', type: 'button', textContent: 'Criar corte', onclick: tentar(async ev => { ev.currentTarget.disabled = true; await esperarCorte(await m.criar(), `Corte de ${tempoVivo(m.pico)}`); }) }));
}
/* Barra: uma linha por gravação (as ativas e as que terminaram há pouco). Só é refeita quando muda quem está nela. */
function desenharBarraGravacao() {
  const agora = Date.now() / 1000;
  const visiveis = GV.caps.filter(c => !GV.fechadas.has(c.arquivo) && (vivo(c) || c.estado === 'erro' || (c.terminou && agora - c.terminou < 900)));
  if (!visiveis.length) { if (GV.barra) { GV.barra.remove(); GV.barra = null; } return; }
  const chave = JSON.stringify(visiveis.map(c => [c.arquivo, vivo(c)]));
  if (!GV.barra || GV.barra.dataset.chave !== chave) {
    if (GV.barra) GV.barra.remove();
    GV.barra = el('div', { className: 'barra-gravacao card' }, ...visiveis.map(c => {
      const v = vivo(c);
      const linha = el('div', { className: 'bg-linha' }, el('span', { className: 'ponto' + (v ? ' on' : '') }), el('span', { className: 'nome' }, el('b'), el('small')),
        v ? el('button', { className: 'btn mini', type: 'button', textContent: 'Clipar 30 s', title: 'Corta os últimos 30 s desta gravação e cria o corte', onclick: clipar(c.login, 30) }) : null,
        v ? el('button', { className: 'btn mini', type: 'button', textContent: 'Clipar 60 s', onclick: clipar(c.login, 60) }) : null,
        el('button', { className: 'btn leve mini', type: 'button', textContent: 'Assistir e momentos', onclick: () => abrirEstudio(c.login) }),
        v ? el('button', { className: 'btn leve mini perigo', type: 'button', textContent: 'Parar', onclick: pararGravacao(c.login) })
          : el('button', { className: 'btn leve mini', type: 'button', textContent: 'Fechar', onclick: () => { GV.fechadas.add(c.arquivo); desenharBarraGravacao(); } }));
      linha.dataset.login = c.login;
      return linha;
    }));
    GV.barra.dataset.chave = chave;
    document.body.append(GV.barra);
  }
  GV.barra.querySelectorAll('.bg-linha').forEach(linha => {
    const c = capDe(linha.dataset.login);
    if (!c) return;
    linha.querySelector('b').textContent = `${vivo(c) ? (c.estado === 'conectando' ? 'Conectando à live de' : 'Gravando') : NOMES_CAP[c.estado] || c.estado} ${c.login}`;
    linha.querySelector('small').textContent = resumoCap(c);
  });
}
function abrirEstudio(login) {
  const d = el('dialog', { className: 'estudio-dlg' });
  const caixa = el('div', { id: 'estudio-vivo' });
  if (login) caixa.dataset.escolha = login;
  d.append(el('div', { className: 'topo-linha', style: 'padding:12px 16px 0' }, el('h2', { className: 'tit', style: 'margin:0', textContent: 'Ao vivo no Vice Clips' }),
    el('button', { className: 'btn leve mini', type: 'button', textContent: 'Fechar', onclick: () => d.close() })), caixa);
  d.addEventListener('close', () => d.remove());
  document.body.append(d); d.showModal();
  pintarEstudio(caixa);
}
/* Player da live + controles + momentos de UMA gravação; com várias, abas no topo para trocar. O player só é recriado quando muda a live. */
function pintarEstudio(caixa) {
  const c = capDe(caixa.dataset.escolha) || GV.caps.find(vivo) || GV.caps[0];
  if (!c) { caixa.replaceChildren(el('p', { className: 'dica', textContent: 'Nenhuma live sendo gravada. Em Lives → Ao vivo agora, use Gravar e clipar (Kick) ou Analisar ao vivo (Twitch). Dá para gravar até 4 lives juntas.' })); delete caixa.dataset.arquivo; return; }
  const abasChave = JSON.stringify([GV.caps.map(x => [x.login, vivo(x)]), c.login]);
  if (caixa.dataset.arquivo !== c.arquivo || caixa.dataset.abas !== abasChave) {
    const recriar = caixa.dataset.arquivo !== c.arquivo || !caixa.querySelector('.ev-status');
    caixa.dataset.arquivo = c.arquivo; caixa.dataset.abas = abasChave;
    const abas = GV.caps.length > 1 ? el('div', { className: 'filtros ev-abas' }, ...GV.caps.map(x => el('button', { className: 'chip', type: 'button', ariaPressed: String(x.login === c.login),
      textContent: `${vivo(x) ? '● ' : ''}${x.login} (${PLATAFORMA[x.plataforma || 'twitch']})`, onclick: () => { caixa.dataset.escolha = x.login; pintarEstudio(caixa); } })))
      : el('span', { className: 'ev-abas', hidden: true });
    if (!recriar) caixa.querySelector('.ev-abas').replaceWith(abas);
    else {
      const kick = c.plataforma === 'kick';
      const src = kick ? `https://player.kick.com/${c.login}?muted=true` : `https://player.twitch.tv/?channel=${c.login}&parent=${location.hostname}&muted=true`;
      const auto = el('select', { onchange: tentar(async e => { await api('/api/descobrir/aovivo/auto', { login: c.login, nota: Number(e.target.value) }); atualizarGravacao(); }) },
        ...[['0', 'Clipar sozinho: desligado'], ['60', 'Clipar sozinho: nota ≥ 60'], ['75', 'Clipar sozinho: nota ≥ 75'], ['90', 'Clipar sozinho: nota ≥ 90']].map(([v, t]) => el('option', { value: v, textContent: t, selected: Number(v) === (c.auto || 0) })));
      caixa.className = 'estudio-vivo';
      caixa.replaceChildren(abas,
        el('div', { className: 'ev-player' }, el('iframe', { src, allowFullscreen: true, allow: 'autoplay; fullscreen', title: `Live de ${c.login}` }),
          el('small', { className: 'dica', textContent: kick ? 'Player oficial da Kick.' : `Player oficial da Twitch. Se não carregar, abra o painel em http://localhost:${location.port}.` })),
        el('div', { className: 'ev-lado' },
          el('div', { className: 'ev-status' }, el('b'), el('small')),
          el('div', { className: 'ferramentas', style: 'margin:0' },
            el('button', { className: 'btn mini', type: 'button', textContent: 'Clipar 30 s', onclick: clipar(c.login, 30) }),
            el('button', { className: 'btn mini', type: 'button', textContent: 'Clipar 60 s', onclick: clipar(c.login, 60) }),
            el('button', { className: 'btn leve mini perigo', type: 'button', textContent: 'Parar gravação', onclick: pararGravacao(c.login) })),
          auto,
          el('p', { className: 'dica', style: 'margin:0', textContent: `A gravação guarda tudo, então nenhum momento passa. Momentos vêm da voz, dos gritos, das risadas e das mudanças de cena${kick ? '' : ' e do chat (acelerando, kkkk, pedindo “clipa”)'}. O chat reage uns segundos depois: o corte começa 20 s antes da reação.` }),
          el('h3', { className: 'tit', style: 'margin:6px 0 0', textContent: 'Momentos' }), el('div', { className: 'ev-momentos lista' })));
    }
  }
  caixa.querySelector('.ev-status b').textContent = `${vivo(c) ? 'Gravando' : NOMES_CAP[c.estado] || c.estado} · ${c.login} (${PLATAFORMA[c.plataforma || 'twitch']})`;
  caixa.querySelector('.ev-status small').textContent = c.erro || [`${c.minutos} min gravados`, `${c.mb} MB`, c.qualidade,
    c.chat && c.chat.lido ? `chat ${fmtNum(c.chat.msgs_min)} msgs/min` : c.plataforma === 'kick' ? 'chat da Kick: ainda não lido (momentos pela voz e imagem)' : 'chat: conectando',
    (c.analise || {}).processado ? `analisado até ${tempoVivo(c.analise.processado)}` : 'análise começando'].join(' · ');
  const ms = momentosDe(c), lista = caixa.querySelector('.ev-momentos');
  const marca = JSON.stringify(ms.map(m => [m.pico, m.nota, m.corte, (m.motivos || []).length]));
  if (lista.dataset.marca !== marca) { // só redesenha quando muda: não some o botão no meio do clique
    lista.dataset.marca = marca;
    lista.replaceChildren(...(ms.length ? ms.slice(0, 40).map(linhaMomento) : [el('p', { className: 'dica', style: 'margin:0', textContent: 'Nenhum momento ainda. A análise roda a cada 25 s e o chat precisa de ~1 min para ter a base de comparação.' })]));
  }
}
/* Momento forte novo (de qualquer gravação) vira aviso com Criar corte. */
function novosMomentos() {
  const todos = GV.caps.flatMap(c => momentosDe(c).map(m => ({ m, c }))), chave = ({ m, c }) => `${c.login}:${m.fonte}:${Math.round(m.pico)}`;
  if (GV.vistos === null) { GV.vistos = new Set(todos.map(chave)); return; }
  for (const x of todos) {
    if (GV.vistos.has(chave(x))) continue;
    GV.vistos.add(chave(x));
    if (x.m.nota >= 70 && !x.m.corte) avisoComBotao(`${x.c.login}: momento forte (${x.m.nota}) · ${(x.m.motivos || []).slice(0, 2).join(', ')}`, 'Criar corte',
      tentar(async () => esperarCorte(await x.m.criar(), `Corte de ${x.c.login} em ${tempoVivo(x.m.pico)}`)));
  }
}
async function atualizarGravacao() {
  try {
    const e = await api('/api/descobrir/analise');
    GV.analise = e;
    GV.caps = (e.capturas || (e.captura && e.captura.login ? [e.captura] : [])).filter(c => c && c.login);
  } catch { return; }
  desenharBarraGravacao(); novosMomentos();
  document.querySelectorAll('#estudio-vivo, #ini-gravacao-corpo').forEach(pintarEstudio);
  if ($('#ini-gravacao')) $('#ini-gravacao').hidden = !gravando();
}
window.atualizarGravacao = atualizarGravacao;

/* ---------- ranking e avisos dos canais ao vivo ---------- */
const ROTULO_AVISO = { online: 'Entrou ao vivo', subindo: 'Audiência subindo', chat: 'Chat explodindo', clipes: 'Clipes saindo' };
const linkCanal = c => (c.plataforma === 'kick' ? `https://kick.com/${c.login}` : `https://www.twitch.tv/${c.login}`);
function chipsMetricas(c) {
  const chip = (texto, classe = '', title = '') => el('span', { className: 'met ' + classe, textContent: texto, title });
  const m = [chip(`${fmtNum(c.espectadores)} assistindo`)];
  m.push(c.crescimento === null || c.crescimento === undefined ? chip('crescimento: medindo', 'fraco', 'Precisa de ~10 min de amostras com o painel aberto.')
    : chip(`${c.crescimento > 0 ? '+' : ''}${c.crescimento}% em 10 min`, c.crescimento >= 10 ? 'sobe' : c.crescimento <= -10 ? 'desce' : ''));
  if (c.plataforma === 'twitch') {
    m.push(c.chat_min === null || c.chat_min === undefined ? chip('chat: medindo', 'fraco', 'O primeiro minuto de chat ainda está sendo contado.') : chip(`${fmtNum(c.chat_min)} msgs/min`));
    m.push(c.clipes_30 === null || c.clipes_30 === undefined ? chip('clipes: medindo', 'fraco', 'A contagem de clipes roda a cada 2 min.')
      : chip(`${c.clipes_30} clipe${c.clipes_30 === 1 ? '' : 's'} em 30 min`, '', c.clipes_views ? `${fmtNum(c.clipes_views)} visualizações somadas` : ''));
  } else m.push(chip('chat e clipes: sem API', 'fraco', 'A API oficial da Kick não entrega mensagens do chat nem clipes.'));
  return m;
}
function linhaTop(c, i) {
  return el('div', { className: 'top-item' },
    el('span', { className: 'pos', textContent: i + 1 }),
    c.thumb ? el('img', { src: `${c.thumb}${c.thumb.includes('?') ? '&' : '?'}t=${Math.floor(Date.now() / 60000)}`, alt: '', loading: 'lazy' }) : el('span', { className: 'sem-thumb' }),
    el('div', { className: 'top-info' },
      el('div', { className: 'topo-linha' }, el('b', { textContent: c.nome || c.login }), el('span', { className: 'selo', style: `--cor:${CORES[c.plataforma]}`, textContent: PLATAFORMA[c.plataforma] })),
      el('small', { textContent: [c.titulo, c.jogo].filter(Boolean).join(' · '), title: c.titulo || '' }),
      el('div', { className: 'metricas' }, ...chipsMetricas(c))),
    el('div', { className: 'top-nota', title: `Nota calculada com: ${(c.nota_com || []).join(', ')}` }, el('b', { textContent: c.nota }), el('small', { textContent: 'nota' }),
      el('a', { className: 'btn leve mini', href: linkCanal(c), target: '_blank', rel: 'noopener', textContent: 'Assistir' }),
      c.plataforma === 'twitch' ? el('button', { className: 'btn mini', type: 'button', textContent: 'Criar clip', onclick: () => criarClip(c.login) }) : null));
}
function linhaAviso(a) {
  return el('div', { className: 'linha-item' },
    el('span', { className: 'selo', style: `--cor:${CORES[a.plataforma]}`, textContent: PLATAFORMA[a.plataforma] }),
    el('span', { className: 'nome' }, `${a.login} · ${ROTULO_AVISO[a.tipo] || 'Aviso'}`, el('small', { textContent: `${a.texto} · ${new Date(a.quando * 1000).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`, title: a.texto })),
    a.plataforma === 'twitch' && a.tipo !== 'online' ? el('button', { className: 'btn mini', type: 'button', textContent: 'Criar clip', onclick: () => criarClip(a.login) })
      : el('a', { className: 'btn leve mini', href: linkCanal(a), target: '_blank', rel: 'noopener', textContent: 'Assistir' }));
}
/* Aviso novo vira um balão no painel e, se permitido, notificação do Windows quando o painel está em segundo plano. */
function novosAvisos(lista) {
  const ultimo = G.ultimoAviso;
  G.ultimoAviso = Math.max(ultimo || 0, ...lista.map(a => a.quando));
  if (ultimo === undefined) return; // primeira leitura: não repete avisos antigos
  for (const a of lista.filter(a => a.quando > ultimo).reverse()) {
    const texto = `${a.login} (${PLATAFORMA[a.plataforma]}): ${ROTULO_AVISO[a.tipo] || 'Aviso'} · ${a.texto}`;
    avisar(texto);
    if (document.hidden && 'Notification' in window && Notification.permission === 'granted') new Notification('Vice Clips', { body: texto, tag: `${a.tipo}:${a.login}` });
  }
}
function botaoNotificar() {
  if (!('Notification' in window) || Notification.permission !== 'default') return null;
  const b = el('button', { className: 'btn leve mini', type: 'button', textContent: 'Avisar no Windows', title: 'Mostra os avisos como notificação do Windows quando o painel está em segundo plano',
    onclick: async () => { await Notification.requestPermission(); b.remove(); } });
  return b;
}
async function recarregarCanais() { G.canais = await api('/api/canais'); if (G.tela === 'lives') desenharCanais(); }
const criarClip = tentar(async (login, duracao = 30) => { await api('/api/twitch/clip', { login, duracao }); avisar('Clip solicitado. Ele aparece em Clips criados assim que a Twitch confirmar.'); });
function desenharCanais() {
  const { canais, clips, avisos = [], top = [] } = G.canais;
  if ($('#lista-clips')) $('#lista-clips').replaceChildren(...(clips.length ? clips.slice(0, 24).map(cartaoClip) : [el('div', { className: 'vazio', textContent: 'Os clips criados por aqui aparecem nesta lista.' })]));
  if (!$('#lista-canais')) return;
  const ranking = top.map(t => canais.find(c => c.plataforma === t.plataforma && c.login === t.login)).filter(Boolean);
  $('#lista-top').replaceChildren(...(ranking.length ? ranking.map(linhaTop)
    : [el('p', { className: 'dica', style: 'margin:0', textContent: canais.length ? 'Nenhum dos seus canais está ao vivo agora.' : 'Adicione canais acima para ver o ranking.' })]));
  $('#lista-avisos').replaceChildren(...(avisos.length ? avisos.slice(0, 8).map(linhaAviso)
    : [el('p', { className: 'dica', style: 'margin:0', textContent: 'Os avisos aparecem aqui com o painel aberto: canal que entra ao vivo, audiência subindo, chat explodindo e rajada de clipes (esses dois só na Twitch).' })]));
  const posicao = new Map(ranking.map((c, i) => [`${c.plataforma}:${c.login}`, i + 1]));
  const ordem = [...canais].sort((a, b) => (b.online ? 1 : 0) - (a.online ? 1 : 0) || (b.nota || 0) - (a.nota || 0));
  $('#lista-canais').replaceChildren(...(ordem.length ? ordem.map(c => {
    const selo = c.online ? el('span', { className: 'selo live', textContent: posicao.has(`${c.plataforma}:${c.login}`) ? `AO VIVO · #${posicao.get(`${c.plataforma}:${c.login}`)}` : 'AO VIVO' }) : null;
    return el('article', { className: 'card canal' },
      el('div', { className: 'foto' }, c.online && c.thumb ? el('img', { src: `${c.thumb}${c.thumb.includes('?') ? '&' : '?'}t=${Math.floor(Date.now() / 60000)}`, alt: '' }) : el('span', { textContent: c.online === false ? 'Offline' : 'Sem status' }), selo),
      el('div', { className: 'info' },
        el('div', { className: 'topo-linha' }, el('h3', { textContent: c.nome || c.login }), el('span', { className: 'selo', style: `--cor:${CORES[c.plataforma]}`, textContent: PLATAFORMA[c.plataforma] })),
        el('p', { className: 'sub', textContent: c.online ? [c.titulo, c.jogo].filter(Boolean).join(' · ') : (c.erro || 'Fora do ar no momento.') }),
        c.online ? el('div', { className: 'metricas' }, ...chipsMetricas(c), c.nota !== undefined ? el('span', { className: 'met nota', textContent: `nota ${c.nota}` }) : null) : null,
        el('div', { className: 'ctrl' },
          c.online === null && c.erro ? el('button', { className: 'btn mini', type: 'button', textContent: 'Configurar', onclick: () => irPara('config') }) : null,
          c.plataforma === 'twitch' && c.online ? el('button', { className: 'btn mini', type: 'button', textContent: 'Criar clip', onclick: () => criarClip(c.login) }) : null,
          c.online ? el('a', { className: 'btn leve mini', href: linkCanal(c), target: '_blank', rel: 'noopener', textContent: 'Assistir' }) : null,
          c.online && window.Descobrir ? el('button', { className: 'btn mini', type: 'button', textContent: c.plataforma === 'kick' ? 'Gravar e clipar' : 'Gravar', title: 'Grava a live no PC, marca os momentos e libera o Clipar agora', onclick: () => Descobrir.gravar(c.login, c.nome || c.login, c.inicio, c.plataforma) }) : null,
          el('button', { className: 'btn leve mini perigo', type: 'button', textContent: 'Remover', onclick: tentar(async () => { await api('/api/canais/remover', { plataforma: c.plataforma, login: c.login }); await recarregarCanais(); }) }))));
  }) : [el('div', { className: 'vazio', textContent: 'Nenhum canal adicionado.' })]));
}

/* ---------- escolher o momento: gravação da Twitch/Kick ou arquivo do PC ---------- */
const E = { f: null, player: null, laco: 0, trecho: false, alvo: null };
function hms(t) {
  t = Math.max(0, t || 0);
  const h = Math.floor(t / 3600), m = Math.floor(t % 3600 / 60), s = t % 60;
  return `${h}:${String(m).padStart(2, '0')}:${s.toFixed(1).padStart(4, '0')}`;
}
function lerHms(txt) {
  const p = String(txt || '').trim().replace(',', '.').split(':');
  if (!p[0] || p.length > 3 || p.some(x => x === '' || isNaN(Number(x)))) return null;
  return p.reduce((a, v) => a * 60 + Number(v), 0);
}
const twTempo = t => `${Math.floor(t / 3600)}h${Math.floor(t % 3600 / 60)}m${Math.floor(t % 60)}s`;
function carregarScript(src) {
  return new Promise((ok, falha) => {
    if (window.Twitch && window.Twitch.Player) return ok();
    const s = el('script', { src }); s.onload = ok; s.onerror = () => falha(new Error('Não consegui carregar o player oficial da Twitch.'));
    document.head.append(s);
  });
}
async function playerTwitch(caixa, video, inicio) {
  await carregarScript('https://player.twitch.tv/js/embed/v1.js');
  const id = `tw-${Date.now()}`;
  caixa.replaceChildren(el('div', { id, className: 'tw-player' }));
  const pl = new Twitch.Player(id, { width: '100%', height: '100%', video, parent: [location.hostname], autoplay: false, time: twTempo(inicio || 0) });
  // O player da Twitch só aceita seek depois que a reprodução começa: guarda o pedido e aplica no PLAYING.
  const st = { iniciado: false, pendente: null };
  pl.addEventListener(Twitch.Player.PLAYING, () => { st.iniciado = true; if (st.pendente !== null) { const t = st.pendente; st.pendente = null; pl.seek(t); pl.pause(); } });
  const ir = t => { t = Math.max(0, t); if (st.iniciado) pl.seek(t); else { st.pendente = t; pl.setMuted(true); pl.play(); } };
  return { tempo: () => (st.pendente !== null ? st.pendente : pl.getCurrentTime() || 0), ir, tocar: () => { pl.setMuted(false); pl.play(); }, pausar: () => pl.pause(), pausado: () => pl.isPaused(), destruir: () => caixa.replaceChildren() };
}
function playerLocal(caixa, url) {
  const v = el('video', { src: url, controls: true, playsInline: true, preload: 'metadata' });
  caixa.replaceChildren(v);
  return { tempo: () => v.currentTime, ir: t => { v.currentTime = Math.max(0, t); }, tocar: () => v.play().catch(() => {}), pausar: () => v.pause(), pausado: () => v.paused,
    destruir: () => { v.pause(); v.removeAttribute('src'); v.load(); } };
}
function pararEstudio() { clearInterval(E.laco); if (E.player) { try { E.player.pausar(); } catch { /* player já saiu da tela */ } } }
async function abrirFonte(o) {
  let f;
  if (o.arquivo) {
    f = await api('/api/arquivo/abrir', o.caminho ? { caminho: o.caminho } : {});
    if (f.cancelado) return;
  } else {
    avisar('Consultando a gravação...');
    f = await api('/api/vod/abrir', { url: o.url });
  }
  pararEstudio(); if (E.player) E.player.destruir(); E.player = null;
  E.f = f; E.trecho = false;
  desenharEstudio(E.alvo);
}
function desenharEstudio(alvo) {
  if (!alvo) return;
  E.alvo = alvo;
  const f = E.f;
  const recentes = el('div', { className: 'recentes' });
  api('/api/vod/recentes').then(lista => recentes.replaceChildren(...(lista.length ? [el('span', { className: 'dica', style: 'margin:0', textContent: 'Abertos recentemente:' })] : []),
    ...lista.slice(0, 8).map(r => el('button', { className: 'chip', type: 'button', title: r.link || r.caminho, textContent: `${r.plataforma === 'Arquivos' ? 'PC' : r.plataforma} · ${(r.titulo || r.id).slice(0, 38)}`,
      onclick: tentar(() => abrirFonte(r.tipo === 'arquivo' ? { arquivo: true, caminho: r.caminho } : { url: r.link })) })))).catch(() => {});
  const abrir = el('form', { className: 'card bloco', onsubmit: tentar(async ev => { ev.preventDefault(); await abrirFonte({ url: $('#es-url').value }); }) },
    el('div', { className: 'linha-link' },
      el('label', {}, 'Link da gravação (live encerrada) da Twitch ou da Kick', el('input', { id: 'es-url', required: true, placeholder: 'https://www.twitch.tv/videos/123456789', autocomplete: 'off', value: (f && f.link) || '' })),
      el('button', { className: 'btn', type: 'submit', textContent: 'Abrir gravação' }),
      el('button', { className: 'btn leve', type: 'button', textContent: 'Arquivo do PC', onclick: tentar(() => abrirFonte({ arquivo: true })) })),
    el('p', { className: 'dica', textContent: 'Arquivos MP4, MOV e MKV funcionam sempre, mesmo quando a plataforma não libera o download. Nos links, só o trecho escolhido é processado.' }),
    recentes);
  alvo.replaceChildren(...[abrir, f ? painelFonte(f) : null].filter(Boolean));
  if (f) ligarPlayer(f);
}
function painelFonte(f) {
  const link = f.tipo !== 'arquivo';
  const dur = f.duracao ? hms(f.duracao).replace(/\.\d$/, '') : '';
  const meta = [f.plataforma === 'Arquivos' ? 'Arquivo do PC' : f.plataforma, f.canal, dur && `duração ${dur}`, f.w ? `${f.w}x${f.h}` : '', f.origem_dados].filter(Boolean).join(' · ');
  const botao = (t, fn, titulo) => el('button', { className: 'btn leve mini', type: 'button', textContent: t, title: titulo || t, onclick: fn });
  const pulo = d => () => { if (E.player) E.player.ir(E.player.tempo() + d); };
  return el('section', { className: 'card bloco fonte-aberta' },
    el('div', { className: 'fonte-cab' }, f.thumb ? el('img', { src: f.thumb, alt: '' }) : null,
      el('div', {}, el('h2', { textContent: f.titulo || 'Vídeo' }), el('small', { textContent: meta }),
        f.aviso ? el('p', { className: 'dica erro', textContent: f.aviso }) : null,
        f.silenciado ? el('p', { className: 'dica', textContent: 'Esta gravação tem trechos silenciados pela Twitch.' }) : null)),
    el('div', { className: 'estudio' },
      el('div', { id: 'es-player', className: 'es-player' }),
      el('div', { className: 'es-ctrl' },
        el('div', { className: 'es-agora' }, el('span', { textContent: 'Agora' }), el('b', { id: 'es-agora', textContent: E.player ? '' : '—' })),
        el('div', { className: 'ferramentas', style: 'margin:0' }, botao('−10s', pulo(-10)), botao('−1s', pulo(-1)), botao('▶ / ❚❚', () => { if (E.player) (E.player.pausado() ? E.player.tocar() : E.player.pausar()); }, 'Reproduzir ou pausar'), botao('+1s', pulo(1)), botao('+10s', pulo(10))),
        el('div', { id: 'es-barra', className: 'es-barra', title: 'Clique para ir a este ponto' }, el('i', { id: 'es-sel' }), el('i', { id: 'es-agulha' })),
        el('form', { className: 'grupo', style: 'grid-template-columns:minmax(0,1fr) auto;align-items:end', onsubmit: ev => { ev.preventDefault(); const t = lerHms($('#es-ir').value); if (t !== null && E.player) E.player.ir(t); } },
          el('label', {}, 'Ir para (h:mm:ss)', el('input', { id: 'es-ir', placeholder: '1:23:45', autocomplete: 'off' })), el('button', { className: 'btn leve mini', style: 'height:38px', type: 'submit', textContent: 'Ir' })),
        el('div', { className: 'grupo marcas' },
          el('label', {}, 'Início do corte', el('input', { id: 'es-ini', placeholder: '0:00:00.0', autocomplete: 'off', oninput: atualizarSel })),
          el('label', {}, 'Fim do corte', el('input', { id: 'es-fim', placeholder: '0:00:00.0', autocomplete: 'off', oninput: atualizarSel })),
          el('button', { className: 'btn mini', type: 'button', textContent: 'Marcar início (I)', onclick: () => marcar('ini') }),
          el('button', { className: 'btn mini', type: 'button', textContent: 'Marcar fim (O)', onclick: () => marcar('fim') })),
        el('div', { className: 'topo-linha' }, el('span', { id: 'es-dur', className: 'dica', style: 'margin:0' }), botao('Tocar o trecho', tocarTrecho)),
        el('label', {}, 'Formato do vídeo final (dá para trocar depois no editor)', el('select', { id: 'es-formato' },
          el('option', { value: '9:16', textContent: '9:16 — TikTok / Reels / Shorts (1080x1920)' }), el('option', { value: '16:9', textContent: '16:9 — horizontal (1920x1080)' }), el('option', { value: '1:1', textContent: '1:1 — quadrado (1080x1080)' }))),
        el('div', { className: 'grupo' },
          el('label', { className: 'todo' }, 'Título do corte (opcional, vai para a faixa)', el('input', { id: 'es-tit', autocomplete: 'off', maxLength: 200 })),
          el('label', { className: 'todo' }, 'Streamer', el('input', { id: 'es-streamer', value: f.canal || '', autocomplete: 'off' }))),
        link ? el('label', { className: 'marcar autoriza' }, el('input', { id: 'es-aut', type: 'checkbox' }),
          'Tenho autorização para usar este trecho (meu canal, permissão do criador ou conteúdo liberado para cortes).') : null,
        el('button', { id: 'es-criar', className: 'btn', type: 'button', textContent: 'Criar corte e escolher o template', onclick: criarCorteEstudio }),
        el('div', { id: 'es-prog', className: 'dica', style: 'margin:0' }),
        link ? el('p', { className: 'dica', style: 'margin:0', textContent: `Só o trecho marcado, com ${f.margem || 12} s de folga antes e depois, é processado. Se a plataforma recusar o acesso, nada é contornado: o aviso aparece aqui.` })
          : el('button', { className: 'btn leve mini', type: 'button', textContent: 'Sugerir cortes automaticamente neste arquivo', onclick: tentar(async () => {
            await api('/api/gerar', { video: f.caminho, qtd: 5, dur_min: 15, dur_max: 60, modelo: 'medium' });
            G.acompanhando = true; irPara('gerar', { modo: 'auto' }); acompanhar();
          }) }))));
}
async function ligarPlayer(f) {
  const caixa = $('#es-player');
  try {
    if (f.player.tipo === 'twitch') E.player = await playerTwitch(caixa, f.player.video, 0);
    else if (f.player.tipo === 'local') E.player = playerLocal(caixa, f.url);
    else {
      E.player = null;
      caixa.replaceChildren(el('div', { className: 'sem-player' }, f.thumb ? el('img', { src: f.thumb, alt: '' }) : null,
        el('p', { textContent: f.plataforma === 'Kick' ? 'A Kick não oferece player oficial para gravações fora do site. Assista na Kick, anote os horários e digite o início e o fim ao lado. No editor, a timeline mostra 30 s de folga para o ajuste fino.'
          : (f.aviso || 'Este vídeo não abre no navegador. Digite os tempos ao lado.') }),
        f.link ? el('a', { className: 'btn mini', href: f.link, target: '_blank', rel: 'noopener', textContent: `Assistir na ${f.plataforma}` }) : null));
    }
  } catch (e) { caixa.replaceChildren(el('p', { className: 'dica erro', textContent: e.message })); }
  clearInterval(E.laco);
  E.laco = setInterval(() => {
    if (!E.player || !$('#es-agora')) return;
    const t = E.player.tempo();
    $('#es-agora').textContent = hms(t);
    if (E.f.duracao) $('#es-agulha').style.left = `${t / E.f.duracao * 100}%`;
    const fim = lerHms($('#es-fim').value);
    if (E.trecho && fim !== null && t >= fim) { E.player.pausar(); E.trecho = false; }
  }, 200);
  $('#es-barra').onclick = ev => { if (!E.player || !E.f.duracao) return; const r = ev.currentTarget.getBoundingClientRect(); E.player.ir((ev.clientX - r.left) / r.width * E.f.duracao); };
  atualizarSel();
}
function marcar(qual) {
  if (!E.player) { avisar('Sem player: digite o horário no campo.', true); return; }
  const t = Math.round(E.player.tempo() * 10) / 10;
  $(qual === 'ini' ? '#es-ini' : '#es-fim').value = hms(t);
  if (qual === 'ini' && lerHms($('#es-fim').value) === null) $('#es-fim').value = hms(t + 30);
  atualizarSel();
}
function atualizarSel() {
  const a = lerHms($('#es-ini')?.value), b = lerHms($('#es-fim')?.value), d = $('#es-dur');
  if (!d) return;
  d.textContent = a !== null && b !== null ? (b > a ? `Duração do corte: ${(b - a).toFixed(1)} s` : 'O fim precisa vir depois do início.') : 'Marque o início e o fim do corte.';
  const sel = $('#es-sel');
  if (sel && E.f && E.f.duracao && a !== null && b > a) sel.style.cssText = `left:${a / E.f.duracao * 100}%;width:${Math.max(0.3, (b - a) / E.f.duracao * 100)}%`;
}
function tocarTrecho() {
  const a = lerHms($('#es-ini').value);
  if (!E.player || a === null) { avisar('Marque o início primeiro.', true); return; }
  E.player.ir(a); E.player.tocar(); E.trecho = true;
}
const criarCorteEstudio = tentar(async () => {
  const f = E.f, ini = lerHms($('#es-ini').value), fim = lerHms($('#es-fim').value), link = f.tipo !== 'arquivo';
  if (ini === null || fim === null || fim - ini < 1) throw new Error('Marque o início e o fim do corte (pelo menos 1 segundo).');
  if (link && !$('#es-aut').checked) throw new Error('Confirme que você tem autorização para usar este trecho.');
  const b = $('#es-criar'); b.disabled = true;
  try {
    const t = await api('/api/vod/corte', { tipo: link ? 'link' : 'arquivo', link: f.link, id: f.id, inicio: ini, fim, titulo: $('#es-tit').value,
      streamer: $('#es-streamer').value, formato: $('#es-formato').value, autorizado: link ? $('#es-aut').checked : false, duracao: f.duracao, titulo_live: f.titulo });
    const r = await aguardarTarefa(t.id, x => { const n = $('#es-prog'); if (n) n.textContent = `${x.mensagem} (${Math.round(x.progresso * 100)}%)`; });
    if (r.aviso) avisar(r.aviso, true);
    pararEstudio();
    irPara('editor', { corte: r.corte });
  } catch (e) { const n = $('#es-prog'); if (n) { n.textContent = e.message; n.className = 'dica erro'; } throw e; }
  finally { b.disabled = false; }
});
addEventListener('keydown', ev => {
  if (!E.f || !$('#es-ini') || !['gerar', 'lives'].includes(G.tela) || /INPUT|TEXTAREA|SELECT/.test(ev.target.tagName)) return;
  if (ev.key.toLowerCase() === 'i') marcar('ini');
  if (ev.key.toLowerCase() === 'o') marcar('fim');
});

/* ---------- clips da Twitch ---------- */
function estadoClip(c) {
  if (c.estado === 'processando') return ['proc', 'Processando na Twitch', 'A Twitch leva até 1 minuto para confirmar o clip.'];
  if (c.estado === 'falhou') return ['erro', 'Não confirmado', 'A Twitch não confirmou o clip em 1 minuto. O canal pode ter recusado.'];
  if (c.importado) return ['ok', 'Arquivo local · editável', 'O arquivo está neste PC e abre no editor.'];
  return ['link', 'Só link · sem arquivo local', c.acesso === 'so_link' || !c.meu_canal
    ? `A Twitch só entrega o arquivo ao dono do canal (${c.login}) e aos editores dele. Assista pelo link ou importe um arquivo autorizado.`
    : 'Você é dono do canal: baixe o arquivo pelo endpoint oficial.'];
}
function abrirClip(c) {
  const d = el('dialog', { className: 'clip-dlg' });
  d.append(el('iframe', { src: `https://clips.twitch.tv/embed?clip=${encodeURIComponent(c.id)}&parent=${location.hostname}&autoplay=true`, allowFullscreen: true, title: c.titulo || 'Clip da Twitch' }),
    el('div', { className: 'topo-linha', style: 'padding:10px 12px' }, el('span', { className: 'nome', textContent: c.titulo || c.id }),
      el('a', { className: 'btn leve mini', href: c.url, target: '_blank', rel: 'noopener', textContent: 'Abrir na Twitch' }),
      el('button', { className: 'btn leve mini', type: 'button', textContent: 'Fechar', onclick: () => d.close() })));
  d.addEventListener('close', () => d.remove());
  document.body.append(d); d.showModal();
}
function cartaoClip(c) {
  const [classe, rotulo, explica] = estadoClip(c);
  return el('article', { className: 'card clip' },
    el('button', { className: 'capa-clip', type: 'button', ariaLabel: 'Assistir ao clip', onclick: () => (c.url ? abrirClip(c) : null) },
      c.thumb ? el('img', { src: c.thumb, alt: '', loading: 'lazy' }) : el('span', { textContent: 'Sem miniatura ainda' }), el('span', { className: `estado ${classe}`, textContent: rotulo })),
    el('div', { className: 'corpo' }, el('span', { className: 'quem', textContent: `${c.login} · ${c.duracao ? Math.round(c.duracao) + ' s' : ''}` }),
      el('p', { className: 'motivo', textContent: c.titulo || c.id }), el('small', { className: 'dica', style: 'margin:0', textContent: explica }),
      el('div', { className: 'ferramentas', style: 'margin:0' },
        c.url ? el('button', { className: 'btn leve mini', type: 'button', textContent: 'Assistir', onclick: () => abrirClip(c) }) : null,
        c.url ? el('a', { className: 'btn leve mini', href: c.url, target: '_blank', rel: 'noopener', textContent: 'Link' }) : null,
        c.importado ? el('button', { className: 'btn mini', type: 'button', textContent: 'Editar', onclick: () => irPara('editor', { corte: c.importado }) }) : null,
        !c.importado && c.estado === 'pronto' && c.acesso !== 'so_link' ? el('button', { className: 'btn mini', type: 'button', textContent: c.meu_canal ? 'Baixar arquivo (oficial)' : 'Tentar baixar (oficial)', title: 'Endpoint oficial da Twitch: só funciona para o dono do canal e editores', onclick: tentar(async () => {
          const t = await api('/api/twitch/importar-clip', { id: c.id });
          try { const r = await aguardarTarefa(t.id); avisar('Clip importado.'); irPara('editor', { corte: r.corte }); } finally { await recarregarCanais(); }
        }) }) : null,
        !c.importado && c.estado === 'pronto' ? el('button', { className: 'btn leve mini', type: 'button', textContent: 'Importar arquivo autorizado', onclick: tentar(async () => {
          const t = await api('/api/clip/anexar', { id: c.id });
          if (t.cancelado) return;
          const r = await aguardarTarefa(t.id); await recarregarCanais(); irPara('editor', { corte: r.corte });
        }) }) : null)));
}
function compararReel(e) {
  const d = el('dialog', { className: 'comparar' });
  const orig = el('video', { src: e.fonte_url, muted: true, playsInline: true, preload: 'auto' });
  const fim = el('video', { src: e.url, playsInline: true, preload: 'auto', controls: true });
  const sinc = () => { if (Math.abs(orig.currentTime - (e.inicio + fim.currentTime)) > 0.15) orig.currentTime = e.inicio + fim.currentTime; };
  fim.addEventListener('play', () => { sinc(); orig.play().catch(() => {}); });
  fim.addEventListener('pause', () => orig.pause());
  fim.addEventListener('seeked', sinc);
  fim.addEventListener('timeupdate', sinc);
  orig.addEventListener('loadedmetadata', () => { orig.currentTime = e.inicio; });
  d.append(el('div', { className: 'comparar-grade' },
    el('figure', {}, el('figcaption', { textContent: 'Original (horizontal)' }), orig),
    el('figure', {}, el('figcaption', { textContent: 'Composição final (MP4 exportado)' }), fim)),
  el('div', { className: 'topo-linha', style: 'padding:10px 12px' }, el('span', { className: 'dica', style: 'margin:0', textContent: 'Os dois vídeos andam juntos. Use os controles do vídeo final.' }),
    el('button', { className: 'btn leve mini', type: 'button', textContent: 'Fechar', onclick: () => d.close() })));
  d.addEventListener('close', () => { orig.pause(); fim.pause(); d.remove(); });
  document.body.append(d); d.showModal();
}

/* ---------- configurações ---------- */
/* ---------- espaço em disco: gravações ao vivo, clipes baixados e lixeira ---------- */
const fmtMb = mb => (mb >= 1024 ? `${(mb / 1024).toFixed(1).replace('.', ',')} GB` : `${mb} MB`);
const confirmarClique = (texto, fn) => ev => { // ação destrutiva pede um segundo clique em até 4 s
  const b = ev.currentTarget;
  if (b.dataset.armado) { fn(ev); return; }
  const antes = b.textContent; b.dataset.armado = '1'; b.textContent = texto;
  setTimeout(() => { if (b.isConnected) { delete b.dataset.armado; b.textContent = antes; } }, 4000);
};
async function desenharEspaco(caixa) {
  if (!caixa) return;
  caixa.replaceChildren(el('h2', { className: 'tit', textContent: 'Espaço em disco' }), el('p', { className: 'dica', style: 'margin:0', textContent: 'Conferindo gravações, clipes baixados e lixeira...' }));
  let r;
  try { r = await api('/api/armazenamento'); } catch (e) { caixa.append(el('p', { className: 'dica erro', textContent: e.message })); return; }
  const fazer = (rota, dados, msg) => tentar(async () => { await api(rota, dados); avisar(msg); desenharEspaco(caixa); });
  const quando = t => new Date(t * 1000).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  const linhaGrav = g => el('div', { className: 'linha-item' }, el('span', { className: 'ponto' + (g.gravando ? ' on' : '') }),
    el('span', { className: 'nome' }, g.nome, el('small', { textContent: [fmtMb(g.mb), g.gravando ? (g.painel ? 'gravando agora (barra de gravação)' : 'gravando sem controle: ficou de quando o painel foi fechado no meio') : `parada · ${quando(g.modificado)}`,
      g.analisando ? 'analisando agora (veja na Atividade)' : ''].filter(Boolean).join(' · ') })),
    g.analisando ? el('button', { className: 'btn leve mini', type: 'button', textContent: 'Ver momentos', onclick: abrirAtividade })
      : el('button', { className: 'btn mini', type: 'button', textContent: 'Analisar', title: 'Procura os melhores momentos (voz, gritos, risadas, mudanças de cena) e dá nota a cada um. Funciona até numa gravação que ainda cresce.',
        onclick: confirmarClique('Confirmar: gravação autorizada', tentar(async () => { await api('/api/armazenamento/analisar', { nome: g.nome, autorizado: true }); avisar('Análise começou. Os momentos aparecem na Atividade.'); abrirAtividade(); desenharEspaco(caixa); })) }),
    g.gravando ? el('button', { className: 'btn leve mini perigo', type: 'button', textContent: 'Parar gravação', onclick: fazer('/api/armazenamento/parar', { nome: g.nome }, 'Gravação parada.') })
      : el('button', { className: 'btn leve mini perigo', type: 'button', textContent: 'Excluir', title: 'Apaga o vídeo bruto da gravação de vez. Os cortes já criados dela continuam.',
        onclick: confirmarClique('Confirmar exclusão', fazer('/api/armazenamento/excluir', { nome: g.nome }, `${g.nome} excluída.`)) }));
  const soma = r.gravacoes.reduce((s, g) => s + g.mb, 0);
  caixa.replaceChildren(
    el('div', { className: 'topo-linha', style: 'margin-bottom:10px' }, el('h2', { className: 'tit', style: 'margin:0', textContent: 'Espaço em disco' }),
      el('span', { className: 'dica', style: 'margin:0', textContent: `${String(r.livre_gb).replace('.', ',')} GB livres de ${r.total_gb} GB · ${r.pasta}` })),
    el('h3', { className: 'esp-sub', textContent: `Gravações ao vivo · ${fmtMb(soma)}` }),
    el('div', { className: 'lista' }, ...(r.gravacoes.length ? r.gravacoes.map(linhaGrav) : [el('p', { className: 'dica', style: 'margin:0', textContent: 'Nenhuma gravação guardada.' })])),
    el('p', { className: 'dica', textContent: 'Cada Gravar e clipar ou Analisar ao vivo gera um vídeo aqui (~1,5 GB por hora em 720p). Excluir apaga só esse vídeo bruto: os cortes e Reels feitos dele ficam em Meus Cortes.' }),
    el('h3', { className: 'esp-sub', textContent: 'Outros arquivos' }),
    el('div', { className: 'lista' },
      el('div', { className: 'linha-item' }, el('span', { className: 'nome' }, 'Clipes baixados', el('small', { textContent: `${r.clipes.n} arquivo${r.clipes.n === 1 ? '' : 's'} · ${fmtMb(r.clipes.mb)} · só a origem: os cortes criados deles continuam` })),
        r.clipes.n ? el('button', { className: 'btn leve mini perigo', type: 'button', textContent: 'Limpar', onclick: confirmarClique('Confirmar', fazer('/api/armazenamento/limpar-clipes', {}, 'Clipes baixados apagados.')) }) : null),
      el('div', { className: 'linha-item' }, el('span', { className: 'nome' }, 'Lixeira do Vice Clips', el('small', { textContent: `${r.lixeira.n} exclus${r.lixeira.n === 1 ? 'ão' : 'ões'} · ${fmtMb(r.lixeira.mb)} · cortes e Reels excluídos ficam aqui para o Desfazer` })),
        r.lixeira.n ? el('button', { className: 'btn leve mini perigo', type: 'button', textContent: 'Esvaziar', onclick: confirmarClique('Confirmar: apaga de vez', fazer('/api/armazenamento/esvaziar-lixeira', {}, 'Lixeira esvaziada.')) }) : null)));
}
async function desenharConfig() {
  const c = G.cfg = await api('/api/config');
  const tw = c.twitch, kk = c.kick;
  const pend = tw.pendente;
  const salvar = tentar(async dados => { G.cfg = await api('/api/config', dados); avisar('Configuração salva.'); desenharConfig(); });
  $('#tela-config').replaceChildren(
    el('header', { className: 'cabeca' }, el('h1', { textContent: 'Configurações' }), el('p', { textContent: 'As credenciais ficam só neste PC.' })),
    el('section', { id: 'cfg-espaco', className: 'card bloco' }),
    el('section', { className: 'card bloco' }, el('h2', { className: 'tit', textContent: 'Twitch' }),
      el('p', { className: tw.conectado ? 'estado-ok' : 'estado-falta', textContent: tw.conectado ? `Conectado como ${tw.login}.` : 'Conta ainda não conectada. Sua senha nunca é digitada aqui.' }),
      tw.conectado ? null : el('ol', { className: 'passos' },
        el('li', {}, 'Ative a verificação em duas etapas na sua conta da Twitch.'),
        el('li', {}, 'Abra ', el('a', { href: 'https://dev.twitch.tv/console/apps/create', target: '_blank', rel: 'noopener', textContent: 'o console da Twitch' }), ' e registre um aplicativo com qualquer nome.'),
        el('li', {}, 'Em URL de redirecionamento, use ', el('code', { textContent: 'http://localhost' }), '. Em categoria, ', el('code', { textContent: 'Application Integration' }), '. Em tipo de cliente, ', el('code', { textContent: 'Público' }), '.'),
        el('li', { textContent: 'Copie o Client ID para o campo abaixo e clique em Salvar.' }),
        el('li', { textContent: 'Clique em Conectar conta e confirme o código no site da Twitch.' })),
      el('div', { className: 'linha-link', style: 'grid-template-columns:minmax(0,1fr) auto auto' },
        el('label', {}, 'Client ID', el('input', { id: 'tw-id', value: tw.client_id, autocomplete: 'off' })),
        el('button', { className: 'btn leve', type: 'button', textContent: 'Salvar', onclick: () => salvar({ twitch_client_id: $('#tw-id').value }) }),
        tw.conectado ? el('button', { className: 'btn leve perigo', type: 'button', textContent: 'Desconectar', onclick: tentar(async () => { await api('/api/twitch/desconectar', {}); desenharConfig(); }) })
          : el('button', { className: 'btn', type: 'button', textContent: 'Conectar conta', disabled: !tw.client_id, onclick: tentar(async () => { await api('/api/twitch/conectar', {}); desenharConfig(); setTimeout(vigiarLogin, 2500); }) })),
      pend && pend.codigo ? el('div', { className: 'codigo' }, el('span', { textContent: 'Digite este código no site da Twitch' }), el('b', { textContent: pend.codigo }),
        el('a', { className: 'btn mini', href: pend.url, target: '_blank', rel: 'noopener', textContent: 'Abrir a Twitch' }), pend.erro ? el('p', { className: 'erro', textContent: pend.erro }) : null) : null,
      el('table', { className: 'permissoes' }, el('thead', {}, el('tr', {}, el('th', { textContent: 'Ação' }), el('th', { textContent: 'O que precisa' }))),
        el('tbody', {}, ...[
          ['Ver quem está ao vivo', 'Conta conectada'],
          ['Criar um clip', 'Conta conectada, canal ao vivo e clips liberados pelo canal'],
          ['Baixar o arquivo do clip', 'Ser o dono do canal ou editor nomeado pelo streamer'],
          ['Editar o clip na Twitch', 'Ter criado o clip com a sua conta'],
          ['Editar o clip no Vice Clips', 'Ter o arquivo baixado, então vale a mesma regra do download'],
        ].map(([a, b]) => el('tr', {}, el('td', { textContent: a }), el('td', { textContent: b })))))),
    el('section', { className: 'card bloco' }, el('h2', { className: 'tit', textContent: 'Kick' }),
      el('p', { id: 'kk-estado', className: kk.conectado ? 'estado-ok' : 'estado-falta', textContent: kk.conectado ? 'Credenciais salvas e aceitas pela Kick.' : 'Credenciais ainda não configuradas. Estar logado no site não basta.' }),
      el('ol', { className: 'passos' },
        el('li', {}, 'Ative a verificação em duas etapas na sua conta da Kick. Ela é obrigatória para criar o aplicativo.'),
        el('li', {}, 'Abra ', el('a', { href: 'https://kick.com/settings/developer', target: '_blank', rel: 'noopener', textContent: 'a aba Developer da Kick' }), ' e crie um aplicativo com qualquer nome.'),
        el('li', {}, 'Em Redirect URL, use ', el('code', { textContent: 'http://localhost' }), '.'),
        el('li', { textContent: 'Copie o Client ID e o Client Secret para os campos abaixo e clique em Salvar e testar.' })),
      el('div', { className: 'grupo' },
        el('label', {}, 'Client ID', el('input', { id: 'kk-id', value: kk.client_id, autocomplete: 'off' })),
        el('label', {}, 'Client Secret', el('input', { id: 'kk-sec', type: 'password', placeholder: kk.tem_segredo ? 'Salvo neste PC' : '', autocomplete: 'new-password' }))),
      el('button', { id: 'kk-testar', className: 'btn', style: 'margin-top:10px', type: 'button', textContent: 'Salvar e testar', onclick: tentar(async () => {
        await api('/api/config', { kick_client_id: $('#kk-id').value, kick_client_secret: $('#kk-sec').value });
        const n = $('#kk-estado');
        try { const r = await api('/api/kick/testar', {}); n.className = 'estado-ok'; n.textContent = r.mensagem; avisar(r.mensagem); $('#kk-sec').value = ''; $('#kk-sec').placeholder = 'Salvo neste PC'; }
        catch (e) { n.className = 'estado-falta'; n.textContent = e.message; }
      }) }),
      el('p', { className: 'dica', textContent: 'A Kick informa quem está ao vivo, título, categoria e espectadores. A API oficial não cria nem baixa clips, então os cortes vêm do link da gravação em Gerar Cortes.' })),
    el('section', { className: 'card bloco' }, el('h2', { className: 'tit', textContent: 'Armazenamento' }), el('p', { className: 'dica', style: 'margin:0', textContent: `Vídeos, modelos e configurações ficam em ${c.dados}.` })));
  desenharEspaco($('#cfg-espaco'));
}
async function vigiarLogin() {
  if (G.tela !== 'config') return;
  const c = await api('/api/config').catch(() => null);
  if (!c) return;
  if (c.twitch.conectado) { avisar('Conta da Twitch conectada.'); desenharConfig(); return; }
  if (c.twitch.pendente && c.twitch.pendente.erro) { desenharConfig(); return; }
  setTimeout(vigiarLogin, 2500);
}

/* ---------- gerar ---------- */
function desenharGerar() {
  const m = G.modoGerar;
  $('#gerar-modos').replaceChildren(...[['manual', 'Escolher o momento (manual)'], ['auto', 'Sugestões automáticas com nota']].map(([id, t]) =>
    el('button', { className: 'chip', type: 'button', textContent: t, ariaPressed: String(id === m), onclick: () => { pararEstudio(); G.modoGerar = id; desenharGerar(); } })));
  $('#modo-auto').hidden = m !== 'auto';
  $('#modo-manual').hidden = m !== 'manual';
  if (m === 'manual') desenharEstudio($('#modo-manual'));
}
function mostrarEstado(e) {
  const passos = e.linhas.map(l => /^(\d)\/4 /.exec(l)).filter(Boolean);
  const etapa = passos.length ? Number(passos.at(-1)[1]) : 0;
  $('#etapas').replaceChildren(...ETAPAS.map((t, i) => el('div', { className: 'etapa ' + (i + 1 < etapa || (!e.rodando && e.codigo === 0) ? 'feita' : i + 1 === etapa && e.rodando ? 'agora' : ''), textContent: t })));
  $('#log').textContent = e.linhas.join('\n');
  $('#parar').hidden = !e.rodando;
  $('#gerar').disabled = e.rodando;
  $('#status').className = !e.rodando && e.codigo ? 'erro' : '';
  $('#status').textContent = e.rodando ? (etapa ? ETAPAS[etapa - 1] : 'Abrindo a live') : e.codigo === 0 ? (e.linhas.at(-1) || 'Pronto').split('. Pasta')[0] : (e.linhas.at(-1) || 'O corte foi interrompido.');
}
async function acompanhar() {
  const e = await api('/api/estado');
  if (e.rodando || G.acompanhando) { $('#progresso').hidden = false; mostrarEstado(e); }
  if (e.rodando) { G.acompanhando = true; setTimeout(acompanhar, 1500); return; }
  if (!G.acompanhando) return;
  G.acompanhando = false;
  if (e.codigo === 0) irPara('cortes');
}

/* ---------- início do app ---------- */
function iniciar() {
  if (location.protocol === 'file:') return;
  $('#nav').replaceChildren(...TELAS.map(([id, nome]) => {
    const b = el('button', { id: `nav-${id}`, className: 'nav-item', type: 'button', hidden: id === 'lives', onclick: () => irPara(id) });
    b.append(svgIcone(ICONES[id]), el('span', { textContent: nome }));
    return b;
  }));
  $('#p-fechar').onclick = () => $('#player').close();
  $('#p-anterior').onclick = () => abrirCorte(G.atual - 1);
  $('#p-proximo').onclick = () => abrirCorte(G.atual + 1);
  $('#p-pasta').onclick = tentar(() => api('/api/abrir-pasta', { pasta: G.visiveis[G.atual].pasta }));
  $('#p-editar').onclick = () => { const c = G.visiveis[G.atual]; $('#player').close(); irPara('editor', { corte: c.id }); };
  $('#player').addEventListener('click', ev => { if (ev.target === $('#player')) $('#player').close(); });
  $('#player').addEventListener('close', () => { const v = $('#tela-video'); v.pause(); v.removeAttribute('src'); v.load(); });
  $('#parar').onclick = tentar(() => api('/api/parar', {}));
  $('#escolher').onclick = tentar(async () => { const r = await api('/api/escolher-arquivo', {}); if (r.caminho) $('#video').value = r.caminho; });
  $('#form').addEventListener('submit', async ev => {
    ev.preventDefault();
    const aviso = $('#aviso');
    aviso.className = 'dica';
    try {
      await api('/api/gerar', Object.fromEntries(['video', 'qtd', 'dur_min', 'dur_max', 'inicio', 'minutos', 'modelo'].map(k => [k, $('#' + k).value])));
      G.acompanhando = true;
      acompanhar();
    } catch (erro) { aviso.className = 'dica erro'; aviso.textContent = erro.message; }
  });
  irPara('inicio');
  $('#menu-fila').onclick = abrirAtividade;
  $('#menu-fila').title = 'Tudo o que o Vice Clips está baixando, gravando e gerando';
  atualizarFundo();
  conferirVersao();
  acompanhar().catch(() => {});
}
document.addEventListener('DOMContentLoaded', iniciar);
