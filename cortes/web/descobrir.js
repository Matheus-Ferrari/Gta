/* Tela Descobrir: lives ao vivo, clipes em alta, criadores favoritos e monitoramento, pela API oficial da Twitch. */
(() => {
  const D = { aba: 'vivo', est: null, gen: 0, timers: [], criadores: null, candidatos: {}, contaAberta: '', editando: '', ultimoMonitor: '',
    vivo: { cat: '', nome: '', rp: null, idioma: '' }, clips: { origem: 'categoria', criador: '', canal: '', nome: '', intervalo: '7d', ranking: 'vistos', cat: '', idioma: null },
    fav: { criador: '', plataforma: 'todas', intervalo: '24h' }, revisao: 'pendente', cortes: {} };
  const ABAS = [['vivo', 'Ao vivo agora'], ['clips', 'Clipes em alta'], ['favoritos', 'Favoritos'], ['monitor', 'Monitoramento']];
  const INTERVALOS = [['1h', '1 hora'], ['6h', '6 horas'], ['24h', '24 horas'], ['7d', '7 dias']];
  const SEG = { '1h': 3600, '6h': 21600, '24h': 86400, '7d': 604800 };
  const PERIODO = { '1h': 'na última hora', '6h': 'nas últimas 6 horas', '24h': 'nas últimas 24 horas', '7d': 'nos últimos 7 dias' };
  const POR_PAGINA = 24;
  const RANKINGS = [['vistos', 'Mais vistos'], ['recentes', 'Mais recentes'], ['crescendo', 'Crescendo mais rápido']];
  const PLAT = { twitch: 'Twitch', kick: 'Kick', youtube: 'YouTube', outra: 'Outra' };
  const IDIOMAS = [['', 'Todos'], ['pt', 'Português'], ['en', 'Inglês'], ['es', 'Espanhol']];
  const WEBCAMS = [['', 'Não informar'], ['inferior-direito', 'Inferior direita'], ['inferior-esquerdo', 'Inferior esquerda'], ['superior-direito', 'Superior direita'], ['superior-esquerdo', 'Superior esquerda']];

  /* ---------- utilidades ---------- */
  const tela = () => $('#tela-descobrir');
  const ativa = g => g === D.gen && G.tela === 'descobrir'; // resposta antiga não redesenha outra aba
  const agendar = (fn, ms) => D.timers.push(setTimeout(fn, ms));
  const parar = () => { D.timers.forEach(clearTimeout); D.timers = []; };
  const qs = o => { const p = new URLSearchParams(); Object.entries(o).forEach(([k, v]) => { if (v !== '' && v !== null && v !== undefined && v !== false) p.set(k, v === true ? '1' : v); }); const s = p.toString(); return s ? `?${s}` : ''; };
  const segs = v => (typeof v === 'number' ? v : Date.parse(v) / 1000) || 0;
  const hoje = t => new Date(t * 1000).toDateString() === new Date().toDateString();
  const hora = t => new Date(t * 1000).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) + (hoje(t) ? '' : ` de ${new Date(t * 1000).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })}`);
  const dataHora = v => new Date(segs(v) * 1000).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  function ha(v) {
    const s = Math.max(0, Date.now() / 1000 - segs(v));
    if (!segs(v)) return '';
    if (s < 60) return 'agora';
    if (s < 3600) return `há ${Math.round(s / 60)} min`;
    if (s < 86400) return `há ${Math.floor(s / 3600)} h`;
    return `há ${Math.floor(s / 86400)} d`;
  }
  const relogio = t => { t = Math.max(0, Math.round(t)); const h = Math.floor(t / 3600), m = Math.floor(t % 3600 / 60), s = t % 60; return `${h ? h + ':' + String(m).padStart(2, '0') : m}:${String(s).padStart(2, '0')}`; };
  const chip = (texto, ligado, clique, extra = {}) => el('button', { className: 'chip', type: 'button', textContent: texto, ariaPressed: String(!!ligado), onclick: clique, ...extra });
  const botao = (texto, fn, classe = 'btn leve mini', extra = {}) => el('button', { className: classe, type: 'button', textContent: texto, onclick: fn, ...extra });
  const link = (texto, href, classe = 'btn leve mini') => el('a', { className: classe, href, target: '_blank', rel: 'noopener', textContent: texto });
  const vazio = (texto, ...extra) => el('div', { className: 'vazio' }, el('p', { textContent: texto }), ...extra);
  const rotulo = texto => el('span', { className: 'dc-rot', textContent: texto });
  function selo(plat) { const s = el('span', { className: 'selo', textContent: PLAT[plat] || plat }); s.style.setProperty('--cor', CORES[plat] || 'var(--suave)'); return s; }
  function canalUrl(k) {
    if (k.plataforma === 'twitch') return `https://www.twitch.tv/${k.login}`;
    if (k.plataforma === 'kick') return `https://kick.com/${k.login}`;
    if (k.plataforma === 'youtube') return k.login.startsWith('@') ? `https://www.youtube.com/${k.login}` : /^UC[\w-]{20,}$/.test(k.id || '') ? `https://www.youtube.com/channel/${k.id}` : '';
    return /^https?:\/\//.test(k.login) ? k.login : '';
  }
  // Desliga o botão enquanto o pedido roda e mostra o erro sem travar a tela.
  const acao = fn => async ev => {
    const b = ev && ev.currentTarget;
    if (ev && ev.type === 'submit') ev.preventDefault();
    if (b && 'disabled' in b) b.disabled = true;
    try { await fn(ev); } catch (e) { avisar(e.message, true); } finally { if (b && 'disabled' in b && b.isConnected) b.disabled = false; }
  };
  // Ação destrutiva pede um segundo clique em até 4 s, sem janela de confirmação.
  const confirmar = (texto, fn) => ev => {
    const b = ev.currentTarget;
    if (b.dataset.armado) { fn(ev); return; }
    const antes = b.textContent; b.dataset.armado = '1'; b.textContent = texto;
    setTimeout(() => { if (b.isConnected) { delete b.dataset.armado; b.textContent = antes; } }, 4000);
  };
  const limiteTxt = l => (l && l.restante !== null && l.restante !== undefined ? `limite da Twitch: ${l.restante}/${l.limite} pontos` : '');
  function caixaErro(msg) {
    const configurar = /Configura|Conecte|Client ID|credenciais|conectada/i.test(msg) || (D.est && !D.est.twitch.conectado);
    return el('div', { className: 'card bloco dc-erro' }, el('p', { className: 'erro', textContent: msg }),
      configurar ? botao('Abrir Configurações', () => irPara('config'), 'btn mini') : null);
  }
  function faixaConexao() {
    const e = D.est;
    if (!e || e.twitch.conectado) return null;
    return el('section', { className: 'card bloco dc-aviso' },
      el('div', {}, el('h3', { textContent: 'Twitch não conectada' }),
        el('p', { textContent: e.twitch.client_id ? 'Conecte sua conta da Twitch para listar lives e clipes. A API oficial exige um token mesmo para dados públicos.'
          : 'Informe o Client ID gratuito da Twitch e conecte a conta. A API oficial exige isso mesmo para dados públicos.' })),
      botao('Abrir Configurações', () => irPara('config'), 'btn'));
  }

  // O que cada ação exige, conferido na referência oficial da API da Twitch.
  const PERMISSOES = [
    ['Lives ao vivo (GET /streams)', 'Conta conectada (token de usuário ou de app). Filtra por categoria (game_id) e idioma. Não filtra por tag: o filtro GTA RP é feito aqui, nas tags e no título.'],
    ['Categorias (GET /games, GET /search/categories)', 'Conta conectada.'],
    ['Clipes em alta (GET /clips)', 'Conta conectada. Exige categoria (game_id) ou canal (broadcaster_id), intervalo em started_at/ended_at, até 100 por página, do mais visto para o menos visto.'],
    ['Buscar IDs (GET /search/channels, GET /users)', 'Conta conectada. A busca casa logins e nomes que começam com o termo; o login exato vem de GET /users.'],
    ['Importar (oficial) (GET /clips/downloads)', 'Escopo editor:manage:clips (ou channel:manage:clips) e ser o dono do canal ou editor dele. Sem isso a Twitch responde 403 e o clipe fica como Só link. Os links de download são temporários.'],
    ['Importar arquivo autorizado', 'Arquivo do PC que você tem direito de usar (enviado pelo criador, por exemplo). Nada é baixado da Twitch.'],
    ['Vídeo da live ao vivo', 'Nenhuma API de listagem dá acesso. A análise em janelas só usa um arquivo seu (a gravação do OBS).'],
    ['Kick: lives, status e IDs', 'API oficial da Kick (Client ID e Client Secret em Configurações). Lista as lives por categoria e idioma, das mais assistidas para as menos.'],
    ['Kick: clipes', 'A API oficial da Kick não tem clipes. O Vice Clips usa os endereços públicos do site da Kick: 20 clipes por consulta, sem paginação (junta os mais vistos e os mais recentes do período). O clipe não informa o idioma: vale o das lives do canal já vistas.'],
    ['Kick: criar clip', 'Não existe API para criar clipe na Kick. Use Gravar e clipar: a live é gravada no seu PC e Clipar agora corta os últimos 30 ou 60 s.'],
    ['Limite de pedidos', 'Balde de pontos por app e usuário (cabeçalhos Ratelimit-*). Listas ficam 2 min em cache e o trabalho de fundo recua quando sobram menos de 100 pontos.'],
  ];
  const permissoes = () => el('details', { className: 'card dc-permissoes' }, el('summary', { textContent: 'O que cada ação exige (Twitch e Kick)' }),
    el('table', { className: 'permissoes' }, el('tbody', {}, ...PERMISSOES.map(([a, b]) => el('tr', {}, el('td', { textContent: a }), el('td', { textContent: b }))))));

  /* ---------- tela ---------- */
  async function mostrar(opcoes = {}) {
    if (opcoes.aba && ABAS.some(([id]) => id === opcoes.aba)) D.aba = opcoes.aba;
    try { D.est = await api('/api/descobrir/estado'); } catch { D.est = null; }
    if (D.vivo.rp === null) Object.assign(D.vivo, { cat: (D.est && D.est.atual) || '', rp: !!(D.est && D.est.rp), idioma: (D.est && D.est.idioma) || '' });
    if (G.tela === 'descobrir') desenhar();
  }
  function sair() { parar(); D.gen++; }
  function desenhar() {
    parar();
    const g = ++D.gen;
    const corpo = el('div', { id: 'dc-corpo' });
    tela().replaceChildren(...[
      el('header', { className: 'cabeca' }, el('h1', { textContent: 'Lives' }),
        el('p', { textContent: 'Lives e clipes em alta da Twitch e da Kick, seus criadores favoritos, as lives que você monitora e a gravação ao vivo. Nada é baixado sem você pedir.' })),
      faixaConexao(), permissoes(),
      el('div', { className: 'filtros', role: 'tablist' }, ...ABAS.map(([id, t]) => chip(t, id === D.aba, () => { D.aba = id; desenhar(); }, { role: 'tab' })),
        chip('Meus canais', false, () => irPara('lives', { aba: 'vivo' }), { role: 'tab' }), chip('Clips criados', false, () => irPara('lives', { aba: 'clips' }), { role: 'tab' })),
      corpo].filter(Boolean));
    ({ vivo: abaVivo, clips: abaClips, favoritos: abaFavoritos, monitor: abaMonitor })[D.aba](corpo, g);
  }

  /* ---------- eventos online/offline ---------- */
  function linhaEvento(e) {
    const on = e.tipo === 'online';
    const lacuna = e.desde_ultima && e.detectado - e.desde_ultima > 600; // painel fechado entre duas conferências
    const quando = on ? `entrou no ar às ${hora(e.quando)}` : lacuna ? `saiu do ar entre ${hora(e.desde_ultima)} e ${hora(e.detectado)}` : `saiu do ar às ${hora(e.detectado)}`;
    return el('div', { className: 'linha-item' }, el('span', { className: 'ponto' + (on ? ' on' : '') }),
      el('span', { className: 'nome' }, e.nome || e.login, el('small', { textContent: [quando, e.jogo, e.titulo].filter(Boolean).join(' · ') })), selo(e.plataforma));
  }

  /* ---------- aba: ao vivo agora ---------- */
  function abaVivo(corpo, g) {
    const v = D.vivo;
    const cats = el('div', { className: 'filtros dc-cats' });
    const lista = el('div', { className: 'dc-lives' }, vazio('Carregando as lives...'));
    const rodape = el('p', { className: 'dica', style: 'margin:8px 0 0' });
    const listaKick = el('div', { className: 'dc-lives' }, vazio('Carregando as lives da Kick...'));
    const rodapeKick = el('p', { className: 'dica', style: 'margin:8px 0 0' });
    const salvar = el('span');
    const favs = el('div', { className: 'lista' }), eventos = el('div', { className: 'lista' });
    const opcoes = el('datalist', { id: 'dc-cats-sug' });
    const busca = el('input', { placeholder: 'Outra categoria (ex.: Minecraft)', autocomplete: 'off', ariaLabel: 'Buscar categoria' });
    busca.setAttribute('list', 'dc-cats-sug');
    let espera;
    busca.oninput = () => {
      clearTimeout(espera);
      const t = busca.value.trim();
      if (t.length >= 2) espera = setTimeout(() => api('/api/descobrir/categorias/buscar' + qs({ q: t })).then(r => opcoes.replaceChildren(...r.map(c => el('option', { value: c.nome })))).catch(() => {}), 450);
    };
    function desenharCats(atual) {
      const salvas = (D.est && D.est.categorias) || [];
      cats.replaceChildren(rotulo('Categoria'), ...salvas.map(c => el('span', { className: 'dc-chip-cat' },
        chip(c.nome, atual ? c.id === atual.id || c.nome === atual.nome : c.id === v.cat || c.nome === v.cat, () => { v.cat = c.id || c.nome; desenhar(); }),
        botao('×', acao(async () => { await api('/api/descobrir/categorias', { acao: 'remover', id: c.id || c.nome }); D.est = await api('/api/descobrir/estado'); desenharCats(atual); }), 'dc-x', { title: `Tirar ${c.nome} das categorias salvas`, ariaLabel: `Tirar ${c.nome} das categorias salvas` }))),
      el('form', { className: 'dc-busca', onsubmit: ev => { ev.preventDefault(); if (busca.value.trim()) { v.cat = busca.value.trim(); busca.value = ''; carregar(); } } }, busca, opcoes,
        el('button', { className: 'btn leve mini', type: 'submit', textContent: 'Ver lives' })));
    }
    corpo.replaceChildren(cats,
      el('div', { className: 'filtros' },
        chip('Só GTA RP (por tag ou título)', v.rp, () => { v.rp = !v.rp; desenhar(); },
          { title: 'A API da Twitch não filtra por tag na consulta. O Vice Clips olha até 300 lives da categoria, das mais assistidas para as menos, e mantém as que têm tag RP, GTARP ou Roleplay, ou "RP" no título.' }),
        el('label', {}, 'Idioma', el('select', { onchange: e => { v.idioma = e.target.value; desenhar(); } }, ...IDIOMAS.map(([id, t]) => el('option', { value: id, textContent: t, selected: id === v.idioma })))),
        botao('Atualizar agora', acao(() => carregar(true))), salvar),
      el('h2', { className: 'tit dc-tit-plat' }, 'Top 5 por espectadores · ', selo('twitch')), lista, rodape,
      el('h2', { className: 'tit dc-tit-plat', style: 'margin-top:18px' }, 'Top 5 por espectadores · ', selo('kick')), listaKick, rodapeKick,
      el('div', { className: 'dc-duas' },
        el('section', { className: 'card bloco' }, el('h2', { className: 'tit', textContent: 'Favoritos ao vivo' }), favs),
        el('section', { className: 'card bloco' }, el('h2', { className: 'tit', textContent: 'Entradas e saídas do ar' }), eventos)));
    desenharCats(null);

    async function carregar(forcar = false) {
      try {
        const r = await api('/api/descobrir/lives' + qs({ categoria: v.cat, rp: v.rp, idioma: v.idioma, forcar }));
        if (!ativa(g)) return;
        Object.assign(v, { cat: r.categoria.id, nome: r.categoria.nome });
        desenharCats(r.categoria);
        lista.replaceChildren(...(r.lives.length ? r.lives.map((l, i) => cartaoLive(l, i, () => carregar()))
          : [vazio(r.rp ? `Nenhuma live com tag ou título de RP entre as ${r.analisadas} mais assistidas de ${r.categoria.nome}.` : `Ninguém ao vivo em ${r.categoria.nome} agora.`)]));
        rodape.textContent = [`${r.categoria.nome}: ${r.analisadas} lives consultadas em GET /streams`, r.rp && 'filtro GTA RP feito pelo Vice Clips nas tags e no título',
          `atualizado às ${hora(r.atualizado)}`, `próxima atualização automática às ${hora(r.proxima)}`, limiteTxt(r.limite)].filter(Boolean).join(' · ');
        const kick = r.kick || [];
        listaKick.replaceChildren(...(kick.length ? kick.map((l, i) => cartaoLive(l, i, () => carregar()))
          : [r.kick_erro ? caixaErro(r.kick_erro) : vazio(r.rp ? `Nenhuma live da Kick com tag ou título de RP entre as ${r.kick_analisadas} mais assistidas.` : `Ninguém ao vivo na Kick em ${r.categoria.nome} agora.`)]));
        rodapeKick.textContent = r.kick_erro ? '' : `Kick: ${r.kick_analisadas} lives consultadas na API oficial (GET /livestreams), mesma categoria e idioma · na Kick não existe criar clip: use Gravar e clipar`;
        salvar.replaceChildren(r.salva ? '' : botao(`Salvar “${r.categoria.nome}”`, acao(async () => {
          await api('/api/descobrir/categorias', { acao: 'salvar', id: r.categoria.id });
          D.est = await api('/api/descobrir/estado'); salvar.replaceChildren(); desenharCats(r.categoria); avisar('Categoria salva.');
        })));
        agendar(() => carregar(), Math.max(15, r.proxima - r.agora + 1) * 1000);
      } catch (e) {
        if (!ativa(g)) return;
        lista.replaceChildren(caixaErro(e.message)); rodape.textContent = ''; listaKick.replaceChildren(); rodapeKick.textContent = '';
        agendar(() => carregar(), 120000);
      }
    }
    async function carregarFavs() {
      try {
        const r = await api('/api/descobrir/criadores');
        if (!ativa(g)) return;
        D.criadores = r;
        const on = r.criadores.flatMap(c => c.contas.filter(k => k.status && k.status.online).map(k => ({ c, k })));
        favs.replaceChildren(...(on.length ? on.map(({ c, k }) => el('div', { className: 'linha-item' }, el('span', { className: 'ponto on' }),
          el('span', { className: 'nome' }, `${c.nome} · ${k.login}`, el('small', { textContent: [k.status.jogo, `${fmtNum(k.status.espectadores)} assistindo`, k.status.inicio && `no ar desde ${hora(segs(k.status.inicio))}`].filter(Boolean).join(' · ') })),
          selo(k.plataforma), link('Abrir', k.status.link || canalUrl(k))))
          : [el('p', { className: 'dica', style: 'margin:0', textContent: r.criadores.some(c => c.contas.length) ? 'Nenhum favorito ao vivo agora. O status é conferido a cada 90 s.' : 'Associe as contas dos seus criadores na aba Favoritos para ver quem está ao vivo.' })]));
        eventos.replaceChildren(...(r.eventos.length ? r.eventos.slice(0, 8).map(linhaEvento)
          : [el('p', { className: 'dica', style: 'margin:0', textContent: 'Quando um favorito ou uma live monitorada entra ou sai do ar, o horário aparece aqui.' })]));
        agendar(carregarFavs, 30000);
      } catch (e) { if (ativa(g)) favs.replaceChildren(el('p', { className: 'dica erro', style: 'margin:0', textContent: e.message })); }
    }
    carregar(); carregarFavs();
  }
  function cartaoLive(l, i, recarregar) {
    const rp = l.rp ? (l.rp.startsWith('tag') ? `RP pela ${l.rp}` : `RP pelo ${l.rp}`) : '';
    const plat = l.plataforma || 'twitch', kick = plat === 'kick';
    return el('article', { className: 'card canal dc-live' },
      el('a', { className: 'foto', href: l.link, target: '_blank', rel: 'noopener', title: `Abrir a live na ${PLAT[plat]}` },
        l.thumb ? el('img', { src: `${l.thumb}${l.thumb.includes('?') ? '&' : '?'}t=${Math.floor(Date.now() / 120000)}`, alt: '', loading: 'lazy' }) : null,
        el('span', { className: 'selo live', textContent: `AO VIVO · ${fmtNum(l.espectadores)}` }), el('span', { className: 'dc-pos', textContent: `#${i + 1}` })),
      el('div', { className: 'info' },
        el('div', { className: 'topo-linha' }, el('h3', { textContent: l.nome }), selo(plat)),
        el('p', { className: 'sub', textContent: l.titulo || 'Sem título', title: l.titulo }),
        el('small', { className: 'dc-meta', textContent: [`${l.espectadores.toLocaleString('pt-BR')} espectadores`, l.inicio && `no ar ${ha(l.inicio)}`, l.idioma && l.idioma.toUpperCase(), rp].filter(Boolean).join(' · ') }),
        l.tags.length ? el('div', { className: 'dc-tags' }, ...l.tags.slice(0, 6).map(t => el('span', { textContent: t }))) : null,
        el('div', { className: 'ctrl' }, link('Abrir live', l.link, 'btn mini'),
          l.favorito ? botao('Nos favoritos', () => { D.aba = 'favoritos'; desenhar(); }, 'btn leve mini', { title: 'Ver na aba Favoritos' })
            : botao('Favoritar', acao(async () => { const r = await api('/api/descobrir/favoritar', kick ? { plataforma: 'kick', login: l.login } : { user_id: l.user_id }); avisar(r.novo ? `${l.nome} entrou nos favoritos (${r.criador.nome}).` : 'Já estava nos favoritos.'); recarregar(); })),
          botao(kick ? 'Gravar e clipar' : 'Analisar ao vivo', () => analisarAoVivo(l.login, l.nome, l.inicio, plat), 'btn mini', { title: 'Grava esta live a partir de agora, marca os melhores momentos e libera o Clipar agora' }),
          kick ? botao('Ver clipes', () => { Object.assign(D.clips, { plataforma: 'kick', origem: 'canal', canal: l.login, nome: l.nome }); D.aba = 'clips'; desenhar(); }) : null,
          l.monitorado ? botao('Monitorando', () => { D.aba = 'monitor'; desenhar(); }, 'btn leve mini', { title: 'Ver na aba Monitoramento' })
            : botao('Monitorar', acao(async () => { await api('/api/descobrir/monitor/adicionar', kick ? { plataforma: 'kick', login: l.login } : { user_id: l.user_id }); avisar(`Monitorando ${l.nome}: os clipes novos desta live vão para a fila de revisão.`); recarregar(); })))));
  }

  /* ---------- gravar a live: grava, marca momentos (análise + chat) e libera Clipar agora ---------- */
  function analisarAoVivo(login, nome, inicio, plataforma = 'twitch') {
    const d = el('dialog', { className: 'tpl-dlg', style: 'width:min(540px,calc(100vw - 32px))' });
    const qual = el('select', {}, el('option', { value: '720', textContent: '720p (recomendado, ~1,5 GB por hora)', selected: true }), el('option', { value: '1080', textContent: '1080p (melhor para Reels, ~3 GB por hora)' }), el('option', { value: '480', textContent: '480p (leve, ~0,8 GB por hora)' }));
    const auto = el('select', {}, ...[['0', 'Não: eu escolho o que vira corte'], ['60', 'Sim, momentos com nota 60 ou mais'], ['75', 'Sim, nota 75 ou mais (recomendado)'], ['90', 'Sim, só nota 90 ou mais']].map(([v, t]) => el('option', { value: v, textContent: t, selected: v === '0' })));
    const transc = el('input', { type: 'checkbox' }), aut = el('input', { type: 'checkbox' });
    d.append(el('div', { style: 'padding:18px;display:grid;gap:12px' },
      el('h2', { className: 'tit', style: 'margin:0' }, `Gravar a live de ${nome} `, selo(plataforma)),
      el('p', { className: 'dica', style: 'margin:0', textContent: `O Vice Clips grava a live no seu PC daqui para a frente, então nenhum momento "passa": tudo fica na gravação. A cada 25 s ele procura picos de voz, gritos, risadas e mudanças de cena${plataforma === 'twitch' ? ' e lê o chat (acelerando, kkkk, pedindo "clipa")' : ''}. Os momentos aparecem com nota na barra de gravação, que fica visível em todas as telas, junto com Clipar agora (últimos 30 ou 60 s).` }),
      el('label', {}, 'Qualidade da gravação', qual),
      el('label', {}, 'Clipar sozinho', auto),
      el('label', { className: 'marcar' }, transc, 'Transcrever os momentos (mostra a fala; usa a placa de vídeo)'),
      el('label', { className: 'marcar autoriza' }, aut, 'Tenho autorização para gravar e cortar esta live (meu canal, permissão do criador ou conteúdo liberado para cortes).'),
      el('div', { className: 'ferramentas', style: 'margin:0' },
        botao('Começar', acao(async () => {
          await api('/api/descobrir/aovivo/iniciar', { login, plataforma, qualidade: qual.value, transcrever: transc.checked, autorizado: aut.checked, inicio_live: inicio || '', auto: Number(auto.value) });
          d.close(); avisar(`Gravando a live de ${nome}. Use a barra de gravação para assistir, ver os momentos e clipar.`);
          if (window.atualizarGravacao) window.atualizarGravacao();
        }), 'btn mini'),
        botao('Cancelar', () => d.close()))));
    d.addEventListener('close', () => d.remove());
    document.body.append(d); d.showModal();
  }

  /* ---------- clipes: cartão e importação ---------- */
  const importarOficial = (x, recarregar) => async ev => {
    const b = ev.currentTarget, antes = b.textContent;
    b.disabled = true;
    try {
      const t = await api('/api/descobrir/clip/importar', { id: x.id });
      if (!t.pronto) await aguardarTarefa(t.id, y => { b.textContent = `Importando ${Math.round(y.progresso * 100)}%`; });
      avisar('Clip importado. Use “Abrir no editor”.');
    } catch (e) { avisar(e.message, true); } finally { b.disabled = false; b.textContent = antes; recarregar(); }
  };
  const importarArquivo = (x, recarregar) => async ev => {
    const b = ev.currentTarget;
    b.disabled = true;
    try {
      await api('/api/descobrir/clip/registrar', { id: x.id });
      const t = await api('/api/clip/anexar', { id: x.id });
      if (t.cancelado) return;
      avisar('Preparando o arquivo autorizado...');
      await aguardarTarefa(t.id);
      avisar('Arquivo importado. Use “Abrir no editor”.');
    } catch (e) { avisar(e.message, true); } finally { b.disabled = false; recarregar(); }
  };
  /* Do clipe direto para o editor: baixa o arquivo público do clipe (com autorização confirmada). */
  function editarClipe(x) {
    const d = el('dialog', { className: 'tpl-dlg', style: 'width:min(480px,calc(100vw - 32px))' });
    const aut = el('input', { type: 'checkbox' }), prog = el('p', { className: 'dica', style: 'margin:0' });
    const ir = botao('Baixar e editar', acao(async () => {
      if (!aut.checked) { prog.textContent = 'Marque a autorização para continuar.'; return; }
      ir.disabled = true;
      try {
        const t = await api('/api/descobrir/clip/editar', { id: x.id, titulo: x.titulo, canal: x.canal_login || x.canal, plataforma: x.plataforma || 'twitch', autorizado: true,
          views: x.views, autor: x.autor, criado: x.criado, url: x.url, duracao: x.duracao });
        const r = await aguardarTarefa(t.id, y => { prog.textContent = `${y.mensagem} (${Math.round(y.progresso * 100)}%)`; });
        d.close(); irPara('editor', { corte: r.corte });
      } catch (e) { prog.textContent = e.message; prog.className = 'dica erro'; ir.disabled = false; }
    }), 'btn mini');
    d.append(el('div', { style: 'padding:18px;display:grid;gap:12px' },
      el('h2', { className: 'tit', style: 'margin:0', textContent: `Editar o clipe de ${x.canal}` }),
      el('p', { className: 'dica', style: 'margin:0', textContent: `“${x.titulo || x.id}” · ${Math.round(x.duracao)} s. O clipe é baixado, vira um corte em Meus Cortes e abre no editor. Para ter mais tempo antes e depois, use Cortar da gravação.` }),
      el('label', { className: 'marcar autoriza' }, aut, 'Tenho autorização para usar este clipe (meu canal, permissão do criador ou conteúdo liberado para cortes).'),
      el('div', { className: 'ferramentas', style: 'margin:0' }, ir, botao('Cancelar', () => d.close())), prog));
    d.addEventListener('close', () => d.remove());
    document.body.append(d); d.showModal();
  }
  /* Do clipe para o corte: abre a gravação no estúdio com o trecho marcado. */
  async function cortarDaGravacao(x) {
    const a = Math.max(0, x.vod_offset - 10), b = x.vod_offset + x.duracao + 10;
    irPara('gerar', { modo: 'manual' });
    try {
      await abrirFonte({ url: x.vod_url });
      $('#es-ini').value = hms(a); $('#es-fim').value = hms(b); atualizarSel();
      if ($('#es-tit') && !$('#es-tit').value) $('#es-tit').value = x.titulo || '';
      for (let i = 0; i < 40 && !E.player; i++) await new Promise(r => setTimeout(r, 250));
      if (E.player) E.player.ir(a);
      avisar('Trecho do clipe marcado na gravação. Ajuste se quiser e clique em Criar corte.');
    } catch (e) { avisar(e.message, true); }
  }
  function cartaoClipe(x, recarregar, extras = []) {
    const reg = x.registro || {}, cr = x.crescimento || {};
    const kick = x.plataforma === 'kick';
    const importado = reg.importado, soLink = reg.acesso === 'so_link';
    const ver = kick ? () => window.open(x.url, '_blank', 'noopener') : () => abrirClip({ id: x.id, url: x.url, titulo: x.titulo });
    return el('article', { className: 'card clip dc-clip' },
      el('button', { className: 'capa-clip', type: 'button', ariaLabel: 'Assistir ao clipe', onclick: ver },
        x.thumb ? el('img', { src: x.thumb, alt: '', loading: 'lazy' }) : el('span', { textContent: 'Sem miniatura' }),
        importado ? el('span', { className: 'estado ok', textContent: 'Arquivo local · editável' }) : soLink ? el('span', { className: 'estado link', textContent: 'Só link' }) : null,
        el('span', { className: 'tempo', textContent: `${Math.round(x.duracao)} s` })),
      el('div', { className: 'corpo' },
        el('span', { className: 'quem', textContent: `Live de ${x.canal} · ${ha(x.criado)}`, title: `Criado em ${dataHora(x.criado)} por ${x.autor}` }),
        x.autor_id && x.autor_id === x.canal_id ? el('span', { className: 'dc-quem proprio', textContent: `Clipado pelo próprio ${x.canal}` })
          : el('span', { className: 'dc-quem', textContent: `Clipado por ${x.autor || 'um espectador'} (espectador)` }),
        el('p', { className: 'motivo', textContent: x.titulo || x.id }),
        el('div', { className: 'dc-metricas' }, el('b', { textContent: `${x.views.toLocaleString('pt-BR')} ${x.views === 1 ? 'visualização' : 'visualizações'}` }),
          cr.estado === 'ok' ? el('span', { className: 'dc-cresce' + (cr.por_hora > 0 ? '' : ' parado'), textContent: `${cr.por_hora > 0 ? '+' : ''}${fmtNum(Math.round(cr.por_hora))}/h`,
            title: `${cr.ganho >= 0 ? '+' : ''}${cr.ganho} visualizações em ${cr.minutos} min, entre amostras reais (${cr.amostras} no total)` })
            : el('span', { className: 'dc-espera', textContent: cr.texto || 'Aguardando segunda amostra' })),
        x.momento ? el('small', { className: 'dc-momento' + (x.ao_vivo ? ' vivo' : ''), title: x.vod_titulo || '',
          textContent: `Momento: ${dataHora(new Date(x.momento * 1000).toISOString())} · ${x.ao_vivo ? 'clipado ao vivo' : 'clipado depois, da gravação'}` })
          : el('small', { className: 'dc-momento', textContent: kick ? 'Clipe da Kick: abre na Kick ou vira corte com Baixar e editar' : 'Gravação indisponível: não dá para saber em que momento da live foi' }),
        el('small', { className: 'dica', style: 'margin:0', textContent: `Criado ${dataHora(x.criado)}${soLink ? ' · a Twitch só entrega o arquivo ao dono do canal e aos editores dele' : ''}` }),
        el('div', { className: 'ferramentas', style: 'margin:0' },
          botao('Assistir', ver, 'btn leve mini', kick ? { title: 'Abre o clipe na Kick' } : {}), link('Abrir link', x.url),
          botao(kick ? 'Baixar e editar' : 'Editar clipe', () => editarClipe(x), 'btn mini', { title: 'Baixa o clipe, cria o corte e abre no editor' }),
          x.vod_url ? botao('Cortar da gravação', () => cortarDaGravacao(x), 'btn leve mini', { title: 'Abre a gravação em Gerar Cortes com início e fim já marcados neste momento (com folga de 10 s)' }) : null,
          importado ? botao('Abrir no editor', () => irPara('editor', { corte: importado }), 'btn mini') : null,
          !kick && !importado && !soLink ? botao('Importar (oficial)', importarOficial(x, recarregar), 'btn mini', { title: 'GET /clips/downloads: só funciona se você for o dono do canal ou editor dele. Sem permissão, o clipe fica como Só link.' }) : null,
          !kick && !importado ? botao('Importar arquivo autorizado', importarArquivo(x, recarregar), 'btn leve mini', { title: 'Recebeu o arquivo do criador? Escolha o arquivo do PC e ele vira um corte editável.' }) : null,
          ...extras)));
  }

  /* ---------- aba: clipes em alta ---------- */
  function abaClips(corpo, g) {
    const c = D.clips;
    const grade = el('div', { className: 'grade dc-clips' }, vazio('Carregando os clipes...'));
    const info = el('p', { className: 'dica', style: 'margin:0 0 12px' });
    const ranks = el('div', { className: 'filtros', role: 'tablist' }), mais = el('div', { className: 'dc-mais' });
    /* Uma barra de filtros + uma faixa de criadores. O resto aparece só quando é usado. */
    const cats = ((D.est && D.est.categorias) || []).filter(x => x.id);
    if (!c.cat) c.cat = D.vivo.cat || (D.est && D.est.atual) || (cats[0] || {}).id || '';
    if (c.idioma === null) c.idioma = (D.est && D.est.idioma) || 'pt';
    c.faixa = c.faixa || 'sugeridos';
    c.plataforma = c.plataforma || 'twitch';
    const kick = c.plataforma === 'kick';
    const IDIOMAS = [['pt', 'Português'], ['en', 'Inglês'], ['es', 'Espanhol'], ['', 'Todos os idiomas']];
    const sel = (rot, valor, opcoes, mudar) => el('label', { className: 'dc-campo' }, rot, el('select', { onchange: e => mudar(e.target.value) },
      ...opcoes.map(([v, t]) => el('option', { value: v, textContent: t, selected: v === valor }))));
    const canalSel = el('label', { className: 'dc-campo', hidden: true });
    const barra = el('div', { className: 'dc-barra' },
      el('div', { className: 'dc-campo' }, 'Plataforma', el('div', { className: 'dc-seg-grupo' }, ...[['twitch', 'Twitch'], ['kick', 'Kick']].map(([id, t]) => el('button', { type: 'button', textContent: t, ariaPressed: String(id === c.plataforma),
        onclick: () => { Object.assign(c, { plataforma: id, origem: 'categoria', criador: '', canal: '', soCanal: '', semCanal: '' }); desenhar(); } })))),
      sel('Categoria', c.cat, cats.map(x => [x.id, x.nome]), v => { Object.assign(c, { origem: 'categoria', cat: v, soCanal: '', semCanal: '' }); desenhar(); }),
      sel('Idioma', c.idioma, IDIOMAS, v => { Object.assign(c, { idioma: v, soCanal: '', semCanal: '' }); desenhar(); }),
      el('div', { className: 'dc-campo' }, 'Período', el('div', { className: 'dc-seg-grupo' }, ...INTERVALOS.map(([id, t]) => el('button', { type: 'button', textContent: t.replace(' horas', 'h').replace(' hora', 'h').replace(' dias', 'd'), ariaPressed: String(id === c.intervalo), onclick: () => { c.intervalo = id; desenhar(); } })))),
      sel('Ordenar', c.ranking, RANKINGS, v => { c.ranking = v; mostrar = POR_PAGINA; mostrarLista(); }),
      sel('Quem clipou', c.quem || '', [['', 'Qualquer pessoa'], ['proprio', 'O próprio streamer'], ['comunidade', 'Espectadores']], v => { c.quem = v; mostrar = POR_PAGINA; mostrarLista(); }),
      canalSel,
      botao('Atualizar', acao(() => carregar(true)), 'btn leve mini dc-atualizar'));
    const faixa = el('div', { className: 'dc-faixa' }, el('p', { className: 'dica', style: 'margin:0', textContent: 'Carregando criadores...' }));
    const foco = el('div', { className: 'dc-foco', hidden: c.origem === 'categoria' });
    const nomeFoco = () => (c.origem === 'canal' ? c.nome : ((D.criadores && D.criadores.criadores.find(x => x.id === c.criador)) || {}).nome || 'criador');
    if (c.origem !== 'categoria') foco.append(el('span', { textContent: `Clipes das lives de ${nomeFoco()}${c.quem === 'proprio' ? ', feitos por ele mesmo' : c.quem === 'comunidade' ? ', feitos por espectadores' : ''} · ${PERIODO[c.intervalo]}` }), botao('Voltar para todos os canais', () => { Object.assign(c, { origem: 'categoria', criador: '', canal: '' }); desenhar(); }));
    const verCanal = k => { Object.assign(c, { origem: 'canal', canal: kick ? k.login : k.id, nome: k.nome || k.login, soCanal: '', semCanal: '' }); desenhar(); };
    const verCriador = x => { Object.assign(c, { origem: 'criador', criador: x.id, soCanal: '', semCanal: '' }); desenhar(); };
    const ativo = k => (c.origem === 'canal' && c.canal === (kick ? k.login : k.id));
    const pessoa = (k, clique, extra = '') => el('button', { className: 'dc-pessoa' + (k.ao_vivo ? ' vivo' : '') + extra, type: 'button', ariaPressed: String(ativo(k)), onclick: clique,
      title: [k.login && `${kick ? 'kick.com' : 'twitch.tv'}/${k.login}`, k.seguidores ? `${fmtNum(k.seguidores)} seguidores` : '', k.jogo].filter(Boolean).join(' · ') },
      k.foto ? el('img', { src: k.foto, alt: '', loading: 'lazy' }) : el('i', { textContent: (k.nome || k.login || '?').slice(0, 1).toUpperCase() }),
      el('span', { textContent: k.nome || k.login }), k.ao_vivo || k.espectadores ? el('small', { textContent: fmtNum(k.espectadores) }) : null);
    function pintarFaixa(r) {
      const abas = [['sugeridos', 'Sugeridos'], ['vivo', 'Ao vivo agora'], ['favoritos', 'Meus favoritos']];
      const todos = el('button', { className: 'dc-pessoa todos', type: 'button', ariaPressed: String(c.origem === 'categoria'), onclick: () => { Object.assign(c, { origem: 'categoria', criador: '', canal: '' }); desenhar(); } }, el('span', { textContent: 'Todos os canais' }));
      let itens = [];
      if (c.faixa === 'sugeridos') itens = r.sugeridos.filter(k => !k.nao_achado).map(k => {
        const p = pessoa(k, () => verCanal(k), !k.manual && (k.seguidores || 0) < 50000 ? ' duvida' : '');
        return c.editar ? el('span', { className: 'dc-editando' }, p,
          el('button', { className: 'dc-x', type: 'button', title: 'Corrigir o canal', textContent: '✎', onclick: () => corrigir(k) }),
          el('button', { className: 'dc-x', type: 'button', title: 'Tirar da lista', textContent: '×', onclick: acao(async () => { await api('/api/descobrir/sugestoes/editar', { idioma: r.idioma, nome: k.busca, acao: 'remover' }); desenhar(); }) })) : p;
      });
      if (c.faixa === 'vivo') itens = r.em_alta.map(k => pessoa({ ...k, ao_vivo: true }, () => verCanal(k)));
      const temConta = q => (kick ? q.plataforma === 'kick' : q.plataforma === 'twitch' && q.id);
      if (c.faixa === 'favoritos') itens = ((D.criadores && D.criadores.criadores) || []).filter(x => x.contas.some(temConta)).map(x => {
        const k = x.contas.find(temConta);
        const b = pessoa({ nome: x.nome, foto: k.foto, login: k.login, ao_vivo: x.ao_vivo }, () => verCriador(x));
        b.ariaPressed = String(c.origem === 'criador' && c.criador === x.id); return b;
      });
      const corrigir = acao(async k => {
        const login = prompt(`Canal certo da Twitch para “${k.busca}” (login):`, k.login); if (!login || !login.trim()) return;
        await api('/api/descobrir/sugestoes/editar', { idioma: r.idioma, nome: k.busca, acao: 'trocar', login }); c.editar = false; desenhar();
      });
      faixa.replaceChildren(
        el('div', { className: 'dc-faixa-topo' }, el('div', { className: 'dc-seg-grupo' }, ...abas.map(([id, t]) => el('button', { type: 'button', textContent: t, ariaPressed: String(c.faixa === id), onclick: () => { c.faixa = id; pintarFaixa(r); } }))),
          c.faixa === 'sugeridos' && !kick ? el('button', { className: 'dc-link', type: 'button', textContent: c.editar ? 'Pronto' : 'Editar lista', onclick: () => { c.editar = !c.editar; pintarFaixa(r); } }) : null,
          c.faixa === 'sugeridos' && c.editar ? el('form', { className: 'dc-sug-add', onsubmit: acao(async ev => { ev.preventDefault(); const n = ev.target.n.value.trim(); if (!n) return; await api('/api/descobrir/sugestoes/editar', { idioma: r.idioma, nome: n }); desenhar(); }) },
            el('input', { name: 'n', placeholder: '+ adicionar criador', autocomplete: 'off', maxLength: 40 })) : null,
          c.editar && c.faixa === 'sugeridos' ? el('span', { className: 'dica', style: 'margin:0', textContent: '✎ corrige o canal, × tira da lista.' }) : null),
        el('div', { className: 'dc-pessoas' }, todos, ...(itens.length ? itens : [el('span', { className: 'dica', style: 'margin:0', textContent: c.faixa === 'favoritos' ? `Associe contas da ${kick ? 'Kick' : 'Twitch'} em Favoritos.` : 'Ninguém aqui agora.' })])));
    }
    api('/api/descobrir/sugestoes' + qs({ idioma: c.idioma || 'en', plataforma: kick ? 'kick' : '' })).then(r => { if (ativa(g)) { D.sug = r; pintarFaixa(r); } })
      .catch(e => { if (ativa(g)) faixa.replaceChildren(el('p', { className: 'dica erro', style: 'margin:0', textContent: e.message })); });
    const escolha = el('select');  // a lista de favoritos ainda é carregada aqui (vai para a faixa)
    const gerar = el('div', { className: 'dc-gerar' });
    corpo.replaceChildren(barra, faixa, foco, el('div', { className: 'topo-linha dc-info-linha' }, info, gerar), grade, mais,
      el('p', { className: 'dica', textContent: kick ? 'Clipes da Kick pelos endereços públicos do site (a API oficial da Kick não tem clipes): até 20 por consulta, juntando os mais vistos e os mais recentes do período.' : 'Clipes pela API oficial da Twitch.' }));
    /* Gerar conteúdo: os primeiros N da lista do jeito que está filtrada e ordenada viram cortes (e Reels, se houver layout salvo). */
    function botaoGerar(lista) {
      gerar.replaceChildren(lista.length ? botao(`Gerar conteúdo dos Top ${Math.min(10, lista.length)}`, () => dialogoGerar(lista), 'btn mini', { title: 'Baixa os clipes do topo desta lista, cria os cortes e renderiza no template' }) : '',
        botao('Automático', () => dialogoAuto(), 'btn leve mini', { title: 'Deixa programado: de tempos em tempos pega os clipes mais vistos deste filtro que ainda não viraram corte' }));
    }
    /* Automático: guarda o filtro atual e, de tempos em tempos, gera conteúdo dos mais vistos que ainda não viraram corte. */
    async function dialogoAuto() {
      let m = { streamers: [], templates: [] };
      try { m = await api('/api/descobrir/modelos'); } catch { /* segue sem a lista */ }
      const nomeFiltro = c.origem === 'categoria' ? `${kick ? 'Kick' : 'Twitch'} · ${((D.est && D.est.categorias) || []).concat([]).find(x => x.id === c.cat)?.nome || 'categoria'}${c.idioma ? ' · ' + c.idioma.toUpperCase() : ''}`
        : c.origem === 'canal' ? `${c.nome || c.canal} (${kick ? 'Kick' : 'Twitch'})` : `${((D.criadores && D.criadores.criadores) || []).find(x => x.id === c.criador)?.nome || 'favorito'} (${kick ? 'Kick' : 'Twitch'})`;
      const sel = (opcoes, valor) => el('select', {}, ...opcoes.map(([v, t]) => el('option', { value: v, textContent: t, selected: String(v) === String(valor) })));
      const quantos = sel([[3, '3 clipes'], [5, '5 clipes'], [10, '10 clipes']], 5);
      const aCada = sel([[10, 'a cada 10 min'], [20, 'a cada 20 min'], [30, 'a cada 30 min'], [60, 'a cada 1 hora'], [120, 'a cada 2 horas']], 20);
      const minimo = sel([[0, 'qualquer'], [5, '5 ou mais'], [10, '10 ou mais'], [25, '25 ou mais'], [50, '50 ou mais'], [100, '100 ou mais']], 10);
      const comLayout = (m.streamers || []).includes(String(c.origem === 'canal' ? (c.nome || c.canal) : '').toLowerCase());
      const modelo = el('select', {}, el('option', { value: 'streamer', textContent: 'Layout salvo do streamer (renderiza se houver)', selected: true }),
        ...(m.templates || []).map(t => el('option', { value: t, textContent: `Template: ${t}` })), el('option', { value: 'nenhum', textContent: 'Só baixar e cortar' }));
      const aut = el('input', { type: 'checkbox' });
      const resumo = el('p', { className: 'dica', style: 'margin:0' });
      const pintarResumo = () => { resumo.textContent = `${aCada.selectedOptions[0].textContent.replace('a cada', 'A cada')}, pega os ${quantos.value} clipes mais vistos de ${nomeFiltro} ${PERIODO[c.intervalo]}${c.quem === 'comunidade' ? ' (feitos por espectadores)' : c.quem === 'proprio' ? ' (feitos pelo próprio streamer)' : ''}, com ${minimo.value > 0 ? `${minimo.value} visualizações ou mais` : 'qualquer número de visualizações'}, que ainda não viraram corte, e gera o conteúdo. Roda com o painel aberto; ao reabrir, a rodada atrasada acontece na hora.`; };
      [quantos, aCada, minimo].forEach(s => { s.onchange = pintarResumo; }); pintarResumo();
      const d = el('dialog', { className: 'tpl-dlg', style: 'width:min(560px,calc(100vw - 32px))' });
      d.append(el('div', { style: 'padding:18px;display:grid;gap:12px' },
        el('h2', { className: 'tit', style: 'margin:0', textContent: `Automático · ${nomeFiltro}` }), resumo,
        el('div', { className: 'opcoes' }, el('label', {}, 'Quantos por vez', quantos), el('label', {}, 'Frequência', aCada), el('label', {}, 'Visualizações mínimas', minimo)),
        el('label', {}, 'Template', modelo),
        comLayout ? null : el('p', { className: 'dica', style: 'margin:0', textContent: 'Para sair renderizado: abra um corte deste streamer no editor, monte o template e clique em “Salvar para este streamer”. Sem isso, os cortes ficam prontos para você aplicar o template.' }),
        el('label', { className: 'marcar autoriza' }, aut, 'Tenho autorização para usar os clipes destes canais (canal meu, permissão do criador ou conteúdo liberado para cortes).'),
        el('div', { className: 'ferramentas', style: 'margin:0' },
          botao('Ligar automático', acao(async () => {
            await api('/api/auto/salvar', { autorizado: aut.checked, nome: `${nomeFiltro} · ${PERIODO[c.intervalo]}`, quem: c.quem || '', quantos: Number(quantos.value), a_cada: Number(aCada.value), minimo: Number(minimo.value), modelo: modelo.value,
              consulta: { plataforma: kick ? 'kick' : '', origem: c.origem, canal: c.origem === 'canal' ? c.canal : '', nome: c.origem === 'canal' ? c.nome : '', categoria: c.origem === 'categoria' ? c.cat : '', idioma: c.origem === 'categoria' ? c.idioma : '', intervalo: c.intervalo, criador: c.origem === 'criador' ? c.criador : '' } });
            d.close(); avisar('Automático ligado: a primeira rodada começa em instantes. Acompanhe e pause na Atividade.');
            if (window.abrirAtividade) window.abrirAtividade();
          }), 'btn mini'),
          botao('Cancelar', () => d.close()))));
      d.addEventListener('close', () => d.remove());
      document.body.append(d); d.showModal();
    }
    async function dialogoGerar(lista) {
      let m = { streamers: [], templates: [] };
      try { m = await api('/api/descobrir/modelos'); } catch { /* segue sem a lista */ }
      const canaisLista = [...new Set(lista.slice(0, 20).map(x => (x.canal_login || x.canal || '').toLowerCase()))];
      const comLayout = canaisLista.filter(n => m.streamers.includes(n));
      const qtd = el('select', {}, ...[5, 10, 20].filter(n => n <= Math.max(5, lista.length)).map(n => el('option', { value: n, textContent: `Top ${Math.min(n, lista.length)}`, selected: n === 10 })));
      const modelo = el('select', {},
        el('option', { value: 'streamer', textContent: comLayout.length ? `Layout salvo do streamer (${comLayout.join(', ')})` : 'Layout salvo do streamer (nenhum salvo ainda)', selected: !!comLayout.length }),
        ...m.templates.map(t => el('option', { value: t, textContent: `Template: ${t}` })),
        el('option', { value: 'nenhum', textContent: 'Só baixar e cortar (escolho o template no editor)', selected: !comLayout.length }));
      const aut = el('input', { type: 'checkbox' });
      const d = el('dialog', { className: 'tpl-dlg', style: 'width:min(540px,calc(100vw - 32px))' });
      d.append(el('div', { style: 'padding:18px;display:grid;gap:12px' },
        el('h2', { className: 'tit', style: 'margin:0', textContent: 'Gerar conteúdo dos clipes em alta' }),
        el('p', { className: 'dica', style: 'margin:0', textContent: 'Pega os primeiros clipes desta lista, do jeito que está filtrada e ordenada. Cada um é baixado, vira corte em Meus Cortes e, com um layout salvo, já sai renderizado como Reel com o título do clipe na manchete.' }),
        comLayout.length ? null : el('p', { className: 'dica', style: 'margin:0', textContent: 'Para renderizar sozinho: abra um corte deste streamer no editor, monte o template (ex.: Editorial Preto) e clique em “Salvar para este streamer”. Depois disso, todo lote sai pronto.' }),
        el('label', {}, 'Quantos', qtd), el('label', {}, 'Template', modelo),
        el('label', { className: 'marcar autoriza' }, aut, 'Tenho autorização para usar estes clipes (canal meu, permissão do criador ou conteúdo liberado para cortes).'),
        el('div', { className: 'ferramentas', style: 'margin:0' },
          botao('Gerar', acao(async () => {
            const escolhidos = lista.slice(0, Number(qtd.value)).map((x, i) => ({ id: x.id, plataforma: x.plataforma || 'twitch', titulo: x.titulo, canal: x.canal_login || x.canal,
              views: x.views, autor: x.autor, criado: x.criado, url: x.url, duracao: x.duracao, posicao: i + 1 }));
            const nomeLista = [dados && dados.titulo, PERIODO[c.intervalo], (RANKINGS.find(r => r[0] === c.ranking) || [])[1]].filter(Boolean).join(' · ');
            const r = await api('/api/descobrir/clips/conteudo', { clips: escolhidos, modelo: modelo.value, autorizado: aut.checked, lista: nomeLista, total: lista.length });
            d.close(); avisar(`${r.tarefas.length} clipes na fila. Acompanhe na Atividade; prontos, eles ficam em Meus Cortes${modelo.value === 'nenhum' ? '' : ' (os Reels em “Reel exportado”)'}.`);
            if (window.abrirAtividade) window.abrirAtividade();
          }), 'btn mini'),
          botao('Cancelar', () => d.close()))));
      d.addEventListener('close', () => d.remove());
      document.body.append(d); d.showModal();
    }
    let dados = null, mostrar = POR_PAGINA;
    function mostrarLista() {
      if (!dados) return;
      let lista = [...dados.clips], nota = '';
      const porCanal = {}, idCanal = {}; lista.forEach(x => { porCanal[x.canal] = (porCanal[x.canal] || 0) + 1; idCanal[x.canal] = kick ? x.canal_login : x.canal_id; });
      const nomes = Object.entries(porCanal).sort((x, y) => y[1] - x[1]);
      canalSel.hidden = !(c.origem === 'categoria' && nomes.length > 1);
      /* Escolher um canal busca os clipes DELE direto na plataforma: a amostra da categoria só traz os mais vistos de todos os idiomas. */
      canalSel.replaceChildren('Canal', el('select', { title: 'Escolher um canal busca todos os clipes dele no período, direto na plataforma', onchange: e => {
        const v = e.target.value;
        if (v.startsWith('+') && idCanal[v.slice(1)]) { Object.assign(c, { origem: 'canal', canal: idCanal[v.slice(1)], nome: v.slice(1), soCanal: '', semCanal: '' }); desenhar(); return; }
        c.soCanal = ''; c.semCanal = v.startsWith('-') ? v.slice(1) : ''; mostrar = POR_PAGINA; mostrarLista();
      } },
        el('option', { value: '', textContent: `Todos (${lista.length})` }),
        ...(nomes.length && nomes[0][1] > 2 ? [el('option', { value: `-${nomes[0][0]}`, textContent: `Sem ${nomes[0][0]}`, selected: c.semCanal === nomes[0][0] })] : []),
        ...nomes.slice(0, 30).map(([n, k]) => el('option', { value: `+${n}`, textContent: `${n} (${k})`, selected: c.soCanal === n }))));
      const proprio = x => x.autor_id && x.autor_id === x.canal_id;
      if (c.quem === 'proprio') lista = lista.filter(proprio); else if (c.quem === 'comunidade') lista = lista.filter(x => !proprio(x));
      if (c.origem === 'categoria' && c.soCanal) lista = lista.filter(x => x.canal === c.soCanal);
      if (c.origem === 'categoria' && c.semCanal) lista = lista.filter(x => x.canal !== c.semCanal);
      if (c.ranking === 'recentes') lista.sort((a, b) => segs(b.criado) - segs(a.criado));
      if (c.ranking === 'crescendo') {
        const ok = lista.filter(x => x.crescimento.estado === 'ok').sort((a, b) => b.crescimento.por_hora - a.crescimento.por_hora);
        if (lista.length - ok.length) nota = `${lista.length - ok.length} ${lista.length - ok.length === 1 ? 'clipe aguardando' : 'clipes aguardando'} amostras: o crescimento só é calculado entre duas medições reais com 10 min ou mais de distância`;
        lista = ok;
      }
      info.textContent = [`${dados.titulo}, ${PERIODO[dados.intervalo]}`, dados.plataforma === 'kick' ? `${dados.clips.length} ${dados.clips.length === 1 ? 'clipe' : 'clipes'} da Kick`
        : dados.origem === 'categoria' ? `${dados.clips.length} ${dados.clips.length === 1 ? 'clipe' : 'clipes'} (os ${dados.limite_paginas} mais vistos da categoria em todos os idiomas${dados.idioma ? ', mais os canais desse idioma ao vivo agora' : ''}; para ver tudo de um streamer, escolha o Canal)`
        : `${dados.clips.length} ${dados.clips.length === 1 ? 'clipe' : 'clipes'} deste canal`,
        `atualizado às ${hora(dados.atualizado)}`, nota].filter(Boolean).join(' · ');
      botaoGerar(lista);
      grade.replaceChildren(...(lista.length ? lista.slice(0, mostrar).map(x => cartaoClipe(x, () => carregar()))
        : [vazio(c.quem === 'proprio' ? `Nenhum clipe feito pelo próprio streamer ${PERIODO[c.intervalo]}: todos foram feitos por espectadores. Na Twitch é quase sempre assim; os cortes do próprio streamer costumam ir para o YouTube ou TikTok.` : c.ranking === 'crescendo' ? 'Ainda não há duas medições com 10 min de distância. Com o painel aberto, as visualizações desta lista são medidas de novo a cada 10 min.' : 'Nenhum clipe neste intervalo.')]));
      mais.replaceChildren(lista.length > mostrar ? botao(`Mostrar mais (${Math.min(POR_PAGINA, lista.length - mostrar)} de ${lista.length - mostrar} restantes)`, () => { mostrar += POR_PAGINA; mostrarLista(); }) : '');
    }
    async function carregar(forcar = false) {
      try {
        const r = await api('/api/descobrir/clips' + qs({ plataforma: kick ? 'kick' : '', origem: c.origem, criador: c.origem === 'criador' ? c.criador : '', canal: c.origem === 'canal' ? c.canal : '',
          nome: c.origem === 'canal' ? c.nome : '', categoria: c.origem === 'categoria' ? c.cat : '', idioma: c.origem === 'categoria' ? c.idioma : '', intervalo: c.intervalo, forcar }));
        if (!ativa(g)) return;
        dados = r; mostrarLista();
        agendar(() => carregar(), Math.max(15, r.proxima - r.agora + 1) * 1000);
      } catch (e) { if (ativa(g)) { dados = null; info.textContent = ''; grade.replaceChildren(caixaErro(e.message)); } }
    }
    mostrarLista();
    api('/api/descobrir/criadores').then(r => {
      if (!ativa(g)) return;
      D.criadores = r;
      if (D.sug && c.faixa === 'favoritos') pintarFaixa(D.sug);
      escolha.append(...r.criadores.map(x => {
        const tw = x.contas.some(k => k.plataforma === 'twitch' && k.id);
        return el('option', { value: x.id, textContent: tw ? x.nome : `${x.nome} (sem conta da Twitch)`, disabled: !tw, selected: c.origem === 'criador' && x.id === c.criador });
      }));
    }).catch(() => {});
    carregar();
  }

  /* ---------- aba: favoritos ---------- */
  function abaFavoritos(corpo, g) {
    const f = D.fav;
    const filtros = el('div', { className: 'filtros' }), lista = el('div', { className: 'dc-criadores' }, vazio('Carregando...')), hist = el('div', { className: 'lista' });
    const nome = el('input', { placeholder: 'Nome do criador', maxLength: 60, required: true, autocomplete: 'off' });
    corpo.replaceChildren(
      el('form', { className: 'card bloco dc-novo', onsubmit: acao(async () => { await api('/api/descobrir/criadores/salvar', { nome: nome.value }); nome.value = ''; avisar('Criador adicionado. Use Buscar IDs para achar as contas.'); await carregar(); }) },
        el('label', {}, 'Novo criador favorito', nome), el('button', { className: 'btn', type: 'submit', textContent: 'Adicionar' })),
      el('p', { className: 'dica', style: 'margin:0 0 12px', textContent: 'Cada criador pode ter contas em várias plataformas. Buscar IDs consulta a API oficial e mostra candidatos: nada é associado sem você clicar em Associar.' }),
      filtros, lista,
      el('h2', { className: 'tit', style: 'margin-top:20px', textContent: 'Histórico de transmissões' }), hist);
    const redesenhar = () => { if (D.criadores) { desenharFiltros(); desenharLista(); desenharHist(); } };
    function desenharFiltros() {
      filtros.replaceChildren(
        el('label', {}, 'Criador', el('select', { onchange: e => { f.criador = e.target.value; redesenhar(); } }, el('option', { value: '', textContent: 'Todos' }),
          ...D.criadores.criadores.map(c => el('option', { value: c.id, textContent: c.nome, selected: c.id === f.criador })))),
        rotulo('Plataforma'), ...[['todas', 'Todas'], ['twitch', 'Twitch'], ['kick', 'Kick'], ['youtube', 'YouTube']].map(([id, t]) => chip(t, f.plataforma === id, () => { f.plataforma = id; redesenhar(); })),
        rotulo('Histórico'), ...INTERVALOS.map(([id, t]) => chip(t, f.intervalo === id, () => { f.intervalo = id; redesenhar(); })));
    }
    function estadoTxt(k) {
      const st = k.status;
      if (k.plataforma === 'youtube' || k.plataforma === 'outra') return 'sem status (sem integração com a API)';
      if (k.plataforma === 'kick' && !D.criadores.kick) return 'status exige as credenciais da Kick';
      if (!st) return 'aguardando a primeira conferência';
      return st.online ? `ao vivo · ${fmtNum(st.espectadores)} assistindo${st.jogo ? ' · ' + st.jogo : ''}` : `offline (conferido às ${hora(st.visto)})`;
    }
    function linhaConta(c, k) {
      const url = canalUrl(k), mon = D.criadores.monitorados.includes(k.plataforma === 'kick' ? `kick:${k.login.toLowerCase()}` : k.id);
      return el('div', { className: 'linha-item dc-conta' }, el('span', { className: 'ponto' + (k.status && k.status.online ? ' on' : '') }), selo(k.plataforma),
        el('span', { className: 'nome' }, k.nome && k.nome.toLowerCase() !== k.login.toLowerCase() ? `${k.nome} (${k.login})` : k.nome || k.login,
          el('small', { textContent: [k.id ? `ID ${k.id}` : 'sem ID', k.verificado ? 'verificado pela API' : (k.nota || 'não verificado'), estadoTxt(k)].join(' · '), title: k.nota || '' })),
        url ? link('Abrir', url) : null,
        (k.plataforma === 'twitch' && k.id) || k.plataforma === 'kick' ? (mon ? botao('Monitorando', () => { D.aba = 'monitor'; desenhar(); })
          : botao('Monitorar', acao(async () => { await api('/api/descobrir/monitor/adicionar', k.plataforma === 'kick' ? { plataforma: 'kick', login: k.login } : { user_id: k.id }); avisar(`Monitorando ${k.login}.`); await carregar(); }))) : null,
        k.plataforma === 'kick' && k.status && k.status.online ? botao('Gravar e clipar', () => analisarAoVivo(k.login, k.nome || k.login, k.status.inicio, 'kick'), 'btn mini') : null,
        botao('Remover', confirmar('Confirmar', acao(async () => { await api('/api/descobrir/criadores/conta-remover', { criador: c.id, plataforma: k.plataforma, chave: k.id || k.login }); await carregar(); })), 'btn leve mini perigo', { title: 'Tirar esta conta do criador' }));
    }
    function formConta(c) {
      const plat = el('select', {}, ...Object.entries(PLAT).map(([v, t]) => el('option', { value: v, textContent: t })));
      const login = el('input', { placeholder: 'login, @canal ou link', autocomplete: 'off', required: true });
      const ident = el('input', { placeholder: 'opcional', autocomplete: 'off' });
      return el('form', { className: 'dc-form', onsubmit: acao(async () => {
        await api('/api/descobrir/criadores/conta', { criador: c.id, plataforma: plat.value, login: login.value, id: ident.value });
        D.contaAberta = ''; avisar('Conta associada.'); await carregar();
      }) }, el('label', {}, 'Plataforma', plat), el('label', {}, 'Canal', login), el('label', {}, 'ID oficial', ident), el('button', { className: 'btn mini', type: 'submit', textContent: 'Associar' }),
      el('p', { className: 'dica todo', style: 'margin:0', textContent: 'Twitch: o ID vem da API (GET /users). Kick: verificado só com as credenciais da Kick. YouTube e outras: guardados como digitados, sem verificação.' }));
    }
    function painelCandidatos(c, cand) {
      return el('div', { className: 'dc-cand' },
        el('div', { className: 'topo-linha' }, el('b', { textContent: `Candidatos para “${c.nome}”` }), botao('Fechar', () => { delete D.candidatos[c.id]; redesenhar(); })),
        el('small', { className: 'dica', style: 'margin:0', textContent: `Busca por ${cand.consultas.map(t => `“${t}”`).join(', ')} em GET /search/channels${cand.logins.length ? ` e login exato (${cand.logins.join(', ')}) em GET /users` : ''}.` }),
        ...cand.avisos.map(a => el('small', { className: 'dica', style: 'margin:0', textContent: a })),
        ...(cand.candidatos.length ? cand.candidatos.map(k => el('div', { className: 'linha-item' }, k.foto ? el('img', { className: 'dc-foto', src: k.foto, alt: '', loading: 'lazy' }) : null, selo(k.plataforma),
          el('span', { className: 'nome' }, `${k.nome} (${k.login})`,
            el('small', { className: 'dc-seg', textContent: [k.seguidores !== undefined && k.seguidores !== null ? `${fmtNum(k.seguidores)} seguidores` : '', k.tipo, k.ao_vivo && 'AO VIVO agora'].filter(Boolean).join(' · ') }),
            el('small', { textContent: [k.jogo && `jogo: ${k.jogo}`, k.idioma && k.idioma.toUpperCase(), k.desde && `conta desde ${k.desde.split('-').reverse().join('/')}`, k.exato && 'login igual ao nome'].filter(Boolean).join(' · ') }),
            k.descricao ? el('small', { className: 'dc-desc', textContent: k.descricao }) : null),
          link('Ver canal', canalUrl(k)),
          k.associado ? rotulo('Associado') : botao('Associar', acao(async () => {
            await api('/api/descobrir/criadores/conta', { criador: c.id, plataforma: k.plataforma, login: k.login, id: k.id });
            k.associado = true; avisar(`${k.login} associado a ${c.nome}.`); await carregar();
          }), 'btn mini')))
          : [el('p', { className: 'dica', style: 'margin:0', textContent: 'Nenhum candidato. Se souber o canal, use Adicionar conta.' })]));
    }
    function cartaoCriador(c) {
      const contas = c.contas.filter(k => f.plataforma === 'todas' || k.plataforma === f.plataforma);
      const cand = D.candidatos[c.id];
      let cabeca;
      if (D.editando === c.id) {
        const novo = el('input', { value: c.nome, maxLength: 60, required: true, ariaLabel: 'Novo nome' });
        cabeca = el('form', { className: 'dc-renomear', onsubmit: acao(async () => { await api('/api/descobrir/criadores/salvar', { id: c.id, nome: novo.value }); D.editando = ''; await carregar(); }) },
          novo, el('button', { className: 'btn mini', type: 'submit', textContent: 'Salvar' }), botao('Cancelar', () => { D.editando = ''; redesenhar(); }));
        setTimeout(() => novo.focus(), 0);
      } else {
        cabeca = el('div', { className: 'topo-linha' }, el('h3', {}, c.nome, c.ao_vivo ? el('span', { className: 'selo live', textContent: 'AO VIVO' }) : null),
          el('div', { className: 'ferramentas', style: 'margin:0' }, botao('Renomear', () => { D.editando = c.id; redesenhar(); }),
            botao('Remover', confirmar('Confirmar remoção', acao(async () => { await api('/api/descobrir/criadores/remover', { id: c.id }); avisar(`${c.nome} saiu dos favoritos.`); await carregar(); })), 'btn leve mini perigo')));
      }
      return el('article', { className: 'card dc-criador' + (c.ao_vivo ? ' on' : '') }, cabeca,
        c.contas.length ? el('div', { className: 'dc-contas' }, ...(contas.length ? contas.map(k => linhaConta(c, k)) : [el('p', { className: 'dica', style: 'margin:0', textContent: `Nenhuma conta ${PLAT[f.plataforma] ? 'na ' + PLAT[f.plataforma] : ''}.` })]))
          : el('p', { className: 'dc-sem', textContent: 'Sem conta associada. Plataformas: em branco.' }),
        el('div', { className: 'ferramentas', style: 'margin:0' },
          botao('Buscar IDs', acao(async () => { D.candidatos[c.id] = await api('/api/descobrir/criadores/buscar-ids', { id: c.id }); redesenhar(); }), 'btn mini', { title: 'Consulta a Twitch (e a Kick, se configurada) e mostra candidatos para você confirmar' }),
          botao(D.contaAberta === c.id ? 'Fechar formulário' : 'Adicionar conta', () => { D.contaAberta = D.contaAberta === c.id ? '' : c.id; redesenhar(); }),
          c.contas.some(k => k.plataforma === 'twitch' && k.id) ? botao('Ver clipes', () => { Object.assign(D.clips, { plataforma: 'twitch', origem: 'criador', criador: c.id }); D.aba = 'clips'; desenhar(); }) : null,
          c.contas.some(k => k.plataforma === 'kick') ? botao('Ver clipes na Kick', () => { Object.assign(D.clips, { plataforma: 'kick', origem: 'criador', criador: c.id }); D.aba = 'clips'; desenhar(); }) : null),
        D.contaAberta === c.id ? formConta(c) : null, cand ? painelCandidatos(c, cand) : null);
    }
    function desenharLista() {
      const cs = D.criadores.criadores.filter(c => !f.criador || c.id === f.criador);
      lista.replaceChildren(...(cs.length ? cs.map(cartaoCriador) : [vazio('Nenhum criador favorito. Adicione um acima ou favorite uma live em Ao vivo agora.')]));
    }
    function desenharHist() {
      const desde = Date.now() / 1000 - SEG[f.intervalo];
      const evs = D.criadores.eventos.filter(e => Math.max(e.quando, e.detectado) >= desde && (!f.criador || e.criador === f.criador) && (f.plataforma === 'todas' || e.plataforma === f.plataforma));
      hist.replaceChildren(...(evs.length ? evs.slice(0, 80).map(linhaEvento)
        : [el('p', { className: 'dica', style: 'margin:0', textContent: 'Nenhuma entrada ou saída do ar neste intervalo. Com o painel aberto, o status das contas associadas é conferido a cada 90 s.' })]));
    }
    async function carregar() {
      try {
        const r = await api('/api/descobrir/criadores');
        if (!ativa(g)) return;
        D.criadores = r; redesenhar();
      } catch (e) { if (ativa(g)) lista.replaceChildren(caixaErro(e.message)); }
    }
    async function atualizarSozinho() { // não apaga o que você está digitando
      if (!ativa(g)) return;
      const ocupado = corpo.contains(document.activeElement) && /INPUT|SELECT/.test(document.activeElement.tagName);
      if (!ocupado && !D.contaAberta && !D.editando) await carregar();
      agendar(atualizarSozinho, 45000);
    }
    carregar().then(() => agendar(atualizarSozinho, 45000));
  }

  /* ---------- aba: monitoramento ---------- */
  function abaMonitor(corpo, g) {
    const lives = el('div', { className: 'canais' }), info = el('p', { className: 'dica', style: 'margin:0 0 12px' });
    const chips = el('div', { className: 'filtros' }), fila = el('div', { className: 'grade dc-clips' });
    const analise = el('section', { className: 'card bloco dc-analise' });
    const login = el('input', { placeholder: 'canal da Twitch ou da Kick, ou o link', autocomplete: 'off', required: true });
    const platMon = el('select', { ariaLabel: 'Plataforma' }, el('option', { value: 'twitch', textContent: 'Twitch' }), el('option', { value: 'kick', textContent: 'Kick' }));
    const explica = (t, p) => el('div', { className: 'card' }, el('h3', { textContent: t }), el('p', { textContent: p }));
    corpo.replaceChildren(
      el('form', { className: 'card bloco dc-add', onsubmit: acao(async () => { await api('/api/descobrir/monitor/adicionar', { login: login.value, plataforma: platMon.value }); login.value = ''; avisar('Live monitorada.'); D.ultimoMonitor = ''; await carregar(); }) },
        el('label', {}, 'Plataforma', platMon), el('label', {}, 'Monitorar um canal (até 5)', login), el('button', { className: 'btn', type: 'submit', textContent: 'Monitorar' })),
      el('div', { className: 'tres' },
        explica('Monitorar = clipes do público', 'Status a cada 90 s. Com a live no ar, a cada 2 min os clipes que o público criou nela entram na Fila de revisão. Daqui eles viram conteúdo com Editar clipe ou em lote em Clipes em alta → Gerar conteúdo.'),
        explica('Gravar = os seus momentos', 'Gravar e clipar (ou Analisar ao vivo) grava a live no seu PC e marca momentos pela voz, pela imagem e pelo chat da Twitch. A barra de gravação aparece em todas as telas, com Clipar agora.'),
        explica('Kick', 'Na Kick não existe criar clip nem baixar pela API oficial. Os clipes do público vêm dos endereços públicos do site da Kick, e o seu clipe sai da gravação com Clipar agora.')),
      info, lives,
      el('h2', { className: 'tit', style: 'margin-top:20px', textContent: 'Fila de revisão' }), chips, fila,
      el('h2', { className: 'tit', style: 'margin-top:20px', textContent: 'Análise ao vivo e de gravações' }), analise);
    function cartaoMonitor(m) {
      const st = m.status || {}, kick = m.plataforma === 'kick', url = kick ? `https://kick.com/${m.login}` : `https://www.twitch.tv/${m.login}`;
      return el('article', { className: 'card canal' },
        el('a', { className: 'foto', href: url, target: '_blank', rel: 'noopener', title: `Abrir na ${kick ? 'Kick' : 'Twitch'}` },
          st.online && st.thumb ? el('img', { src: `${st.thumb}${st.thumb.includes('?') ? '&' : '?'}t=${Math.floor(Date.now() / 120000)}`, alt: '' }) : el('span', { textContent: st.online === false ? 'Offline' : 'Aguardando status' }),
          st.online ? el('span', { className: 'selo live', textContent: `AO VIVO · ${fmtNum(st.espectadores)}` }) : null),
        el('div', { className: 'info' },
          el('div', { className: 'topo-linha' }, el('h3', { textContent: m.nome }), selo(kick ? 'kick' : 'twitch')),
          el('p', { className: 'sub', textContent: st.online ? `${st.titulo || 'Sem título'} · no ar desde ${hora(segs(st.inicio))}` : 'Fora do ar. Quando entrar, os clipes novos da live vão para a fila.' }),
          el('small', { className: 'dc-meta', textContent: [st.visto && `status às ${hora(st.visto)}`, st.online && m.ultimo_clips && `clipes conferidos às ${hora(m.ultimo_clips)}`,
            st.online && m.clips_live !== undefined && `${m.clips_live} ${m.clips_live === 1 ? 'clipe' : 'clipes'} nesta live`, m.erro].filter(Boolean).join(' · ') || 'A primeira conferência acontece em instantes.' }),
          el('div', { className: 'ctrl' }, link(st.online ? 'Abrir live' : 'Abrir canal', url, 'btn mini'),
            st.online ? botao(kick ? 'Gravar e clipar' : 'Analisar ao vivo', () => analisarAoVivo(m.login, m.nome, st.inicio, kick ? 'kick' : 'twitch'), 'btn mini') : null,
            botao('Ver clipes', () => { Object.assign(D.clips, { plataforma: kick ? 'kick' : 'twitch', origem: 'canal', canal: kick ? m.login : m.user_id, nome: m.nome }); D.aba = 'clips'; desenhar(); }),
            botao('Parar de monitorar', acao(async () => { await api('/api/descobrir/monitor/remover', { user_id: m.user_id }); D.ultimoMonitor = ''; await carregar(); }), 'btn leve mini perigo'))));
    }
    function desenharFila(r) {
      const rotulos = { pendente: 'Pendentes', importado: 'Importados', descartado: 'Descartados' };
      chips.replaceChildren(...Object.entries(rotulos).map(([id, t]) => chip(`${t} (${r.contagem[id] || 0})`, D.revisao === id, () => { D.revisao = id; D.ultimoMonitor = ''; carregar(); })));
      const itens = r.fila.filter(i => i.estado === D.revisao);
      const mudar = (i, a) => acao(async () => { await api('/api/descobrir/revisao', { id: i.id, acao: a }); D.ultimoMonitor = ''; await carregar(); });
      fila.replaceChildren(...(itens.length ? itens.slice(0, 60).map(i => cartaoClipe({ ...i, canal: `${i.nome} · achado às ${hora(i.encontrado)}` }, () => { D.ultimoMonitor = ''; carregar(); },
        i.estado === 'pendente' ? [botao('Descartar', mudar(i, 'descartar'), 'btn leve mini perigo')] : i.estado === 'descartado' ? [botao('Voltar para pendentes', mudar(i, 'restaurar'))] : []))
        : [vazio({ pendente: 'Nenhum clipe novo para revisar. Os clipes criados nas lives monitoradas aparecem aqui.', importado: 'Nenhum clipe importado ainda.', descartado: 'Nenhum clipe descartado.' }[D.revisao])]));
    }
    async function carregar() {
      try {
        const r = await api('/api/descobrir/monitor');
        if (!ativa(g)) return;
        info.textContent = [`${r.canais.length}/${r.max} lives monitoradas`, 'status a cada 90 s e clipes a cada 2 min, só com o painel aberto', r.erro].filter(Boolean).join(' · ');
        const marca = JSON.stringify([r.canais, r.fila.map(i => [i.id, i.estado, i.registro]), D.revisao]);
        if (marca !== D.ultimoMonitor) { // só redesenha quando algo mudou: não interrompe uma importação em andamento
          D.ultimoMonitor = marca;
          lives.replaceChildren(...(r.canais.length ? r.canais.map(cartaoMonitor) : [vazio('Nenhuma live monitorada. Escolha até 5 em Ao vivo agora, em Favoritos ou digite o canal acima.')]));
          desenharFila(r);
        }
      } catch (e) { if (ativa(g)) { lives.replaceChildren(caixaErro(e.message)); D.ultimoMonitor = ''; } }
    }
    async function laco() { await carregar(); if (ativa(g)) agendar(laco, 10000); }
    D.ultimoMonitor = '';
    laco();
    desenharAnalise(analise, g);
  }

  /* ---------- análise em janelas de um arquivo autorizado (preparação) ---------- */
  function desenharAnalise(caixa, g) {
    const caminho = el('input', { placeholder: 'D:\\Gravações\\minha-live.mkv', autocomplete: 'off' });
    const janela = el('select', {}, ...[20, 25, 30].map(j => el('option', { value: j, textContent: `${j} s`, selected: j === 25 })));
    const webcam = el('select', {}, ...WEBCAMS.map(([v, t]) => el('option', { value: v, textContent: t })));
    const visual = el('select', {}, el('option', { value: 'leve', textContent: 'Leve: só quadros-chave' }), el('option', { value: 'completo', textContent: 'Completa: 1 quadro/s, mais CPU' }));
    const seguir = el('input', { type: 'checkbox' }), transcrever = el('input', { type: 'checkbox' }), aut = el('input', { type: 'checkbox' });
    const status = el('div', { className: 'dc-status' });
    caixa.replaceChildren(
      el('p', { className: 'dica', style: 'margin:0 0 12px', textContent: 'Preparação para analisar a live enquanto ela acontece, sem capturar a live de ninguém: a fonte é o arquivo que você mesmo grava no OBS (MKV ou MP4 fragmentado). Ele é lido em janelas curtas, em outro processo com prioridade baixa, uma análise por vez e ffmpeg com 1 thread.' }),
      el('div', { className: 'linha-link', style: 'grid-template-columns:minmax(0,1fr) auto' }, el('label', {}, 'Arquivo da gravação', caminho),
        botao('Escolher arquivo', acao(async () => { const r = await api('/api/escolher-arquivo', {}); if (r.caminho) caminho.value = r.caminho; }), 'btn leve')),
      el('div', { className: 'opcoes' }, el('label', {}, 'Janela', janela), el('label', {}, 'Região da webcam', webcam), el('label', {}, 'Leitura da imagem', visual)),
      el('div', { className: 'dc-marcas' },
        el('label', { className: 'marcar' }, seguir, 'O arquivo ainda está sendo gravado: acompanhar enquanto cresce (para após 2 min sem crescer)'),
        el('label', { className: 'marcar' }, transcrever, 'Transcrever os trechos sugeridos (Whisper no processo da análise, nunca no painel; mais lento)'),
        el('label', { className: 'marcar autoriza' }, aut, 'Este arquivo é a minha própria gravação ou tenho autorização para usá-lo.')),
      el('div', { className: 'ferramentas' },
        botao('Analisar em janelas', acao(async () => {
          await api('/api/descobrir/analise/iniciar', { caminho: caminho.value, janela: Number(janela.value), webcam: webcam.value, visual: visual.value, seguir: seguir.checked, transcrever: transcrever.checked, autorizado: aut.checked });
          D.cortes = {}; avisar('Análise iniciada em segundo plano.'); atualizar();
        }), 'btn mini'),
        botao('Parar análise', acao(async () => { await api('/api/descobrir/analise/parar', {}); atualizar(); }), 'btn leve mini perigo')),
      status);
    const NOMES = { iniciando: 'Iniciando', rodando: 'Analisando', concluida: 'Concluída', parada: 'Parada', erro: 'Erro' };
    const criar = (i, s) => acao(async ev => {
      const b = ev.currentTarget;
      const t = await api('/api/descobrir/analise/corte', { indice: i });
      const r = await aguardarTarefa(t.id, y => { if (b.isConnected) b.textContent = `${Math.round(y.progresso * 100)}%`; });
      D.cortes[`${s.inicio}-${s.fim}`] = r.corte; avisar('Corte criado. Use “Abrir no editor”.'); desenharStatus(ultimo);
    });
    let ultimo = null;
    function desenharStatus(e) {
      ultimo = e;
      if (!e || !e.estado) { status.replaceChildren(el('p', { className: 'dica', style: 'margin:0', textContent: 'Nenhuma análise feita ainda.' })); return; }
      const sug = [...(e.sugestoes || [])].map((s, i) => ({ s, i })).sort((a, b) => b.s.nota - a.s.nota);
      const cap = e.captura || {};
      const NOMES_CAP = { conectando: 'Conectando à live...', gravando: 'Gravando e analisando', encerrada: 'A live acabou ou caiu', parada: 'Gravação parada', erro: 'Erro' };
      status.replaceChildren(
        cap.login ? el('div', { className: 'dc-captura' + (cap.rodando ? ' on' : '') },
          el('b', { textContent: `${NOMES_CAP[cap.estado] || cap.estado} · ${cap.login}` }),
          el('span', { textContent: cap.erro || `${cap.qualidade} · ${cap.mb} MB · ${cap.minutos} min gravados` }),
          cap.rodando ? botao('Parar de gravar', acao(async () => { await api('/api/descobrir/aovivo/parar', {}); atualizar(); }), 'btn leve mini perigo') : null) : null,
        el('p', { className: e.estado === 'erro' ? 'dica erro' : 'dica', style: 'margin:0' }, el('b', { textContent: `${NOMES[e.estado] || e.estado}: ` }),
          `${e.mensagem || ''} · ${e.arquivo ? e.arquivo.split(/[\\/]/).pop() : ''} · analisado até ${relogio(e.processado || 0)} · ${e.janelas || 0} janelas de ${e.janela || '?'} s${(e.cenas || []).length ? ` · ${e.cenas.length} mudanças de cena` : ''}`),
        sug.length ? el('div', { className: 'lista', style: 'margin-top:10px' }, ...sug.slice(0, 30).map(({ s, i }) => {
          const corte = D.cortes[`${s.inicio}-${s.fim}`];
          return el('div', { className: 'linha-item' }, el('span', { className: 'dc-nota', textContent: s.nota, title: 'Estimativa de relevância do momento, não prevê alcance' }),
            el('span', { className: 'nome' }, `${relogio(s.inicio)} → ${relogio(s.fim)} · pico em ${relogio(s.pico)}`, el('small', { textContent: s.motivos.join(' · ') + (s.fala ? ` · “${s.fala}”` : '') })),
            corte ? botao('Abrir no editor', () => irPara('editor', { corte }), 'btn mini') : botao('Criar corte', criar(i, s), 'btn mini', { title: 'Cria o corte deste trecho pelo fluxo de Arquivo do PC' }));
        })) : el('p', { className: 'dica', style: 'margin:8px 0 0', textContent: e.estado === 'rodando' ? 'Nenhum pico ainda. As sugestões aparecem conforme as janelas são analisadas.' : 'Nenhuma sugestão neste arquivo.' }));
    }
    async function atualizar() {
      try {
        const e = await api('/api/descobrir/analise');
        if (!ativa(g)) return;
        desenharStatus(e);
        if (e.rodando || e.estado === 'iniciando' || (e.captura && e.captura.rodando)) agendar(atualizar, 3000);
      } catch (e) { if (ativa(g)) status.replaceChildren(el('p', { className: 'dica erro', textContent: e.message })); }
    }
    atualizar();
  }

  window.Descobrir = { mostrar, sair, gravar: analisarAoVivo };
})();
