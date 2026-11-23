/* Tela Referências: vídeos que inspiram os cortes, análise de arquivos autorizados e boas práticas com fonte. */
(() => {
  const R = { aba: 'biblioteca', d: null, bp: null, f: { plataforma: 'todas', etiqueta: '', busca: '' }, fbp: { plataforma: 'todas', tipo: 'todos' },
    editando: null, painel: null, consultando: new Set(), ativo: false };
  const TIPOS = {
    tecnico: ['Especificação técnica', 'Requisito objetivo de formato ou envio. Fora dele, o arquivo pode ser recusado ou perder qualidade.'],
    oficial: ['Recomendação oficial', 'Orientação publicada pela própria plataforma. Não garante alcance.'],
    anuncios: ['Especificação de anúncios', 'Vale para anúncios pagos. A fonte não prevê distribuição orgânica: use só como referência aproximada.'],
    tendencia: ['Hipótese de tendência', 'O que a plataforma diz estar em alta. Muda rápido e não garante resultado.'],
  };
  const PLAT_BP = { instagram: 'Instagram', tiktok: 'TikTok', youtube: 'YouTube', twitch: 'Twitch', geral: 'Geral' };
  const COR = { instagram: '#ff8cc6', tiktok: 'var(--ciano)', youtube: 'var(--youtube)', twitch: 'var(--twitch)', arquivo: 'var(--sol)', geral: 'var(--suave)' };
  const BASE = { medido: 'medido no vídeo', etiqueta: 'da sua etiqueta', ideia: 'ideia de combinação, não medida' };
  const DOMINIOS = [['instagram', /(^|\.)(instagram\.com|instagr\.am)$/], ['tiktok', /(^|\.)tiktok\.com$/], ['twitch', /(^|\.)twitch\.tv$/], ['youtube', /(^|\.)(youtube\.com|youtu\.be|youtube-nocookie\.com)$/]];

  const tempo = s => { s = Math.max(0, +s || 0); const m = Math.floor(s / 60); return `${m}:${(s - m * 60).toFixed(1).padStart(4, '0')}`; };
  const durTxt = s => (s >= 3600 ? `${Math.floor(s / 3600)} h${s % 3600 ? ` ${Math.round(s % 3600 / 60)} min` : ''}` : s >= 60 ? `${Math.floor(s / 60)} min${s % 60 ? ` ${Math.round(s % 60)} s` : ''}` : `${Math.round(s)} s`);
  const dataBr = t => (t ? t.slice(0, 10).split('-').reverse().join('/') + (t.length > 10 ? ` ${t.slice(11)}` : '') : '');
  const selo = (txt, cor) => { const n = el('span', { className: 'selo', textContent: txt }); n.style.setProperty('--cor', cor || 'var(--suave)'); return n; };
  const nomeRef = r => (r.metadados && r.metadados.titulo) || (r.arquivo ? r.arquivo.split(/[\\/]/).pop() : '') || r.url;
  const fechar = () => el('button', { className: 'btn leve mini', type: 'button', textContent: 'Fechar', onclick: () => { R.painel = null; desenharPainel(); desenharCartoes(); } });
  const tela = () => $('#tela-referencias');
  function platDoLink(u) {
    try { const h = new URL(u).hostname.toLowerCase(); return (DOMINIOS.find(([, r]) => r.test(h)) || [''])[0]; } catch { return null; }
  }

  function mostrar() { R.ativo = true; R.d = null; R.bp = null; desenhar(); }
  function sair() { R.ativo = false; }

  function desenhar() {
    const corpo = el('div');
    tela().replaceChildren(
      el('header', { className: 'cabeca' }, el('h1', { textContent: 'Referências' }),
        el('p', { textContent: 'Guarde vídeos que inspiram seus cortes, analise arquivos que você tem direito de usar e consulte boas práticas com fonte.' })),
      el('div', { className: 'filtros', role: 'tablist' }, ...[['biblioteca', 'Biblioteca de referências'], ['boas', 'Boas práticas']].map(([id, t]) =>
        el('button', { className: 'chip', type: 'button', role: 'tab', textContent: t, ariaPressed: String(R.aba === id), onclick: () => { R.aba = id; desenhar(); } }))),
      corpo);
    (R.aba === 'boas' ? desenharBoas : desenharBiblioteca)(corpo).catch(e => corpo.replaceChildren(el('div', { className: 'vazio erro', textContent: e.message })));
  }

  /* ---------- biblioteca ---------- */
  async function desenharBiblioteca(corpo) {
    if (!R.d) { corpo.replaceChildren(el('div', { className: 'vazio', textContent: 'Carregando...' })); R.d = await api('/api/referencias'); }
    corpo.replaceChildren(formulario(), el('section', { id: 'ref-painel' }), el('div', { id: 'ref-filtros', className: 'filtros' }), el('div', { id: 'ref-lista', className: 'grade ref-grade' }));
    mostrarPlataforma(); desenharPainel(); desenharFiltros(); desenharCartoes();
  }
  async function recarregar() { R.d = await api('/api/referencias'); }

  function formulario() {
    const ed = R.editando && R.d.itens.find(r => r.id === R.editando);
    const arquivo = ed && ed.plataforma === 'arquivo';
    const etq = el('input', { id: 'ref-etq', autocomplete: 'off', placeholder: 'choque, humor', value: ed ? ed.etiquetas.join(', ') : '' });
    const alternar = e => {
      const atuais = etq.value.split(',').map(x => x.trim()).filter(Boolean);
      etq.value = (atuais.includes(e) ? atuais.filter(x => x !== e) : [...atuais, e]).join(', ');
    };
    return el('form', { id: 'ref-form', className: 'card bloco', onsubmit: tentar(salvar) },
      el('div', { className: 'topo-linha' }, el('h2', { className: 'tit', style: 'margin:0', textContent: ed ? `Editar: ${nomeRef(ed)}` : 'Nova referência' }),
        ed ? el('button', { className: 'btn leve mini', type: 'button', textContent: 'Cancelar edição', onclick: () => { R.editando = null; desenhar(); } }) : null),
      el('div', { className: 'linha-link', style: 'margin-top:12px' },
        el('label', {}, arquivo ? 'Link do vídeo (opcional para arquivo do PC)' : 'Link do vídeo no Instagram, TikTok, Twitch ou YouTube',
          el('input', { id: 'ref-url', autocomplete: 'off', placeholder: 'https://www.youtube.com/shorts/...', value: ed ? ed.url : '', required: !arquivo, oninput: mostrarPlataforma })),
        el('button', { className: 'btn', type: 'submit', textContent: ed ? 'Salvar alterações' : 'Salvar referência' }),
        el('button', { className: 'btn leve', type: 'button', textContent: 'Analisar arquivo do PC', title: 'Vídeo seu ou autorizado, sem precisar de link', onclick: () => abrirPedido(null) })),
      el('small', { id: 'ref-plat', className: 'ref-plat-aviso' }),
      el('div', { className: 'opcoes' },
        el('label', {}, 'Origem (de onde veio)', el('input', { id: 'ref-origem', autocomplete: 'off', maxLength: 200, placeholder: 'Ex.: perfil @pagina, indicação', value: ed ? ed.origem : '' })),
        el('label', {}, 'Estilo', el('input', { id: 'ref-estilo', autocomplete: 'off', maxLength: 200, placeholder: 'Ex.: faixa branca com título e cortes secos', value: ed ? ed.estilo : '' })),
        el('label', {}, 'Etiquetas (separe por vírgula)', etq)),
      el('div', { className: 'ref-sugestoes' }, el('small', { textContent: 'Sugestões:' }),
        ...R.d.etiquetas.map(e => el('button', { className: 'ref-etq', type: 'button', textContent: `#${e}`, onclick: () => alternar(e) }))),
      el('label', { style: 'margin-top:12px' }, 'Observações', el('textarea', { id: 'ref-obs', rows: 2, maxLength: 2000, value: ed ? ed.observacoes : '' })),
      ed ? null : el('label', { className: 'marcar ref-marcar' }, el('input', { id: 'ref-meta', type: 'checkbox', checked: true }),
        'Buscar dados públicos do link (título, autor, duração, data, visualizações e miniatura). Sem login e sem cookies.'),
      el('p', { className: 'dica', textContent: 'Só o link e as suas anotações são guardados: o vídeo não é baixado. Para analisar imagem e som, use um arquivo que você tem direito de usar.' }));
  }
  function mostrarPlataforma() {
    const n = $('#ref-plat'), u = ($('#ref-url') || {}).value || '';
    if (!n) return;
    const p = u.trim() ? platDoLink(u.trim()) : '';
    n.className = 'ref-plat-aviso' + (p === null || (u.trim() && !p) ? ' erro' : '');
    n.textContent = !u.trim() ? '' : p === null ? 'Cole o link completo, começando com https://.' : p ? `Plataforma: ${R.d.plataformas[p]}` : 'Use um link do Instagram, TikTok, Twitch ou YouTube.';
  }

  async function salvar(ev) {
    ev.preventDefault();
    const buscar = $('#ref-meta') ? $('#ref-meta').checked : true;
    const novo = !R.editando;
    const { item } = await api('/api/referencias/salvar', { id: R.editando || undefined, url: $('#ref-url').value.trim(), origem: $('#ref-origem').value,
      estilo: $('#ref-estilo').value, etiquetas: $('#ref-etq').value, observacoes: $('#ref-obs').value });
    R.editando = null;
    avisar(novo ? 'Referência salva.' : 'Alterações salvas.');
    await recarregar();
    desenhar();
    if (item.url && item.metadados.estado === 'pendente' && buscar) consultar(item.id);
  }
  async function consultar(id) {
    R.consultando.add(id); desenharCartoes();
    try {
      const { item } = await api('/api/referencias/metadados', { id });
      if (item.metadados.estado !== 'ok') avisar(item.metadados.motivo);
    } catch (e) { avisar(e.message, true); }
    R.consultando.delete(id);
    if (R.ativo && R.aba === 'biblioteca') { await recarregar().catch(() => {}); desenharCartoes(); }
  }
  async function remover(r) {
    if (!confirm(`Remover "${nomeRef(r)}" da biblioteca? Arquivos do PC não são apagados.`)) return;
    await api('/api/referencias/remover', { id: r.id });
    if (R.painel && R.painel.id === r.id) R.painel = null;
    if (R.editando === r.id) R.editando = null;
    await recarregar(); desenhar();
  }

  function desenharFiltros() {
    const caixa = $('#ref-filtros');
    if (!caixa) return;
    const f = R.f, itens = R.d.itens, conta = {};
    itens.forEach(r => { conta[r.plataforma] = (conta[r.plataforma] || 0) + 1; });
    const etqs = [...new Set(itens.flatMap(r => r.etiquetas))].sort();
    if (f.etiqueta && !etqs.includes(f.etiqueta)) f.etiqueta = '';
    caixa.replaceChildren(
      ...['todas', ...Object.keys(R.d.plataformas).filter(p => conta[p])].map(p => el('button', { className: 'chip', type: 'button', ariaPressed: String(f.plataforma === p),
        textContent: `${p === 'todas' ? 'Todas' : R.d.plataformas[p]} (${p === 'todas' ? itens.length : conta[p]})`, onclick: () => { f.plataforma = p; desenharFiltros(); desenharCartoes(); } })),
      el('label', {}, 'Etiqueta', el('select', { onchange: e => { f.etiqueta = e.target.value; desenharCartoes(); } },
        el('option', { value: '', textContent: 'Todas' }), ...etqs.map(e => el('option', { value: e, textContent: e, selected: e === f.etiqueta })))),
      el('label', {}, 'Buscar', el('input', { type: 'search', value: f.busca, placeholder: 'título, autor, estilo...', oninput: e => { f.busca = e.target.value; desenharCartoes(); } })));
  }
  function desenharCartoes() {
    const caixa = $('#ref-lista');
    if (!caixa || !R.d) return;
    const f = R.f, busca = f.busca.trim().toLowerCase();
    const lista = R.d.itens.filter(r => (f.plataforma === 'todas' || r.plataforma === f.plataforma) && (!f.etiqueta || r.etiquetas.includes(f.etiqueta))
      && (!busca || [r.url, r.origem, r.estilo, r.observacoes, r.arquivo, (r.metadados || {}).titulo, (r.metadados || {}).autor, ...r.etiquetas].join(' ').toLowerCase().includes(busca)));
    caixa.replaceChildren(...(lista.length ? lista.map(cartao) : [el('div', { className: 'vazio', textContent: R.d.itens.length
      ? 'Nenhuma referência com esses filtros.' : 'Nenhuma referência ainda. Cole o link de um vídeo que inspira seus cortes ou analise um arquivo do PC.' })]));
  }
  function cartao(r) {
    const m = r.metadados || {}, an = r.analise;
    const dados = [m.autor, m.data && `publicado em ${dataBr(m.data)}`, typeof m.visualizacoes === 'number' && `${m.visualizacoes.toLocaleString('pt-BR')} visualizações`].filter(Boolean).join(' · ');
    let estado = null;
    if (R.consultando.has(r.id)) estado = el('p', { className: 'ref-estado', textContent: 'Consultando dados públicos...' });
    else if (m.estado === 'indisponivel') estado = el('p', { className: 'ref-estado indisponivel', textContent: m.motivo, title: m.detalhe || '' });
    else if (m.estado === 'pendente' && r.url) estado = el('p', { className: 'ref-estado' }, 'Dados públicos não consultados. ', el('button', { className: 'ref-link', type: 'button', textContent: 'Consultar agora', onclick: () => consultar(r.id) }));
    const capa = el('div', { className: 'ref-capa' },
      m.miniatura ? el('img', { src: m.miniatura, alt: '', loading: 'lazy', referrerPolicy: 'no-referrer', onerror: e => e.target.remove() }) : null,
      el('span', { className: 'ref-sem-capa', textContent: R.d.plataformas[r.plataforma] }),
      selo(R.d.plataformas[r.plataforma], COR[r.plataforma]), r.formato ? el('span', { className: 'ref-formato', textContent: r.formato }) : null,
      m.duracao ? el('span', { className: 'tempo', textContent: durTxt(m.duracao) }) : null);
    return el('article', { className: 'card ref-card' + (R.painel && R.painel.id === r.id ? ' ativo' : '') }, capa,
      el('div', { className: 'ref-corpo' },
        el('h3', { title: nomeRef(r), textContent: nomeRef(r) }),
        dados ? el('small', { textContent: dados }) : null,
        el('small', { textContent: `Salvo em ${dataBr(r.salvo_em)}${r.origem ? ` · origem: ${r.origem}` : ''}` }),
        r.estilo ? el('p', { className: 'ref-estilo', textContent: r.estilo }) : null,
        r.etiquetas.length ? el('div', { className: 'ref-etiquetas' }, ...r.etiquetas.map(e => el('button', { className: 'ref-etq', type: 'button', textContent: `#${e}`, title: 'Filtrar por esta etiqueta',
          onclick: () => { R.f.etiqueta = e; desenharFiltros(); desenharCartoes(); } }))) : null,
        r.observacoes ? el('p', { className: 'motivo', textContent: r.observacoes }) : null,
        estado,
        an ? el('p', { className: 'ref-resumo' }, `Análise de ${dataBr(an.data)}: `, el('b', { textContent: an.sugestoes.templates.slice(0, 2).map(t => t.nome).join(', ') })) : null,
        el('div', { className: 'ref-acoes' },
          r.url ? el('a', { className: 'btn leve mini', href: r.url, target: '_blank', rel: 'noopener noreferrer', textContent: 'Abrir link' }) : null,
          an ? el('button', { className: 'btn mini', type: 'button', textContent: 'Ver análise', onclick: () => abrirPainel('analise', r.id) }) : null,
          el('button', { className: 'btn leve mini', type: 'button', textContent: an ? 'Analisar de novo' : 'Analisar arquivo', onclick: () => abrirPedido(r.id) }),
          el('button', { className: 'btn leve mini', type: 'button', textContent: 'Editar', onclick: () => { R.editando = r.id; desenhar(); window.scrollTo(0, 0); } }),
          el('button', { className: 'btn leve mini perigo', type: 'button', textContent: 'Remover', onclick: tentar(() => remover(r)) }))));
  }

  /* ---------- análise ---------- */
  const abrirPedido = id => abrirPainel('pedido', id);
  function abrirPainel(modo, id) {
    R.painel = { modo, id };
    desenharPainel(); desenharCartoes();
    const n = $('#ref-painel');
    if (n) n.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  function desenharPainel() {
    const caixa = $('#ref-painel');
    if (!caixa) return;
    const p = R.painel, r = p && p.id ? R.d.itens.find(x => x.id === p.id) : null;
    if (!p || (p.id && !r) || (p.modo === 'analise' && !(r && r.analise))) { caixa.replaceChildren(); return; }
    caixa.replaceChildren(p.modo === 'pedido' ? painelPedido(r) : painelAnalise(r));
  }
  function painelPedido(r) {
    const lim = R.d.limite;
    const prog = el('div', { id: 'ra-prog', className: 'ref-prog' });
    const analisar = tentar(async () => {
      prog.className = 'ref-prog';
      if (!$('#ra-aut').checked) { prog.className = 'ref-prog erro'; prog.textContent = 'Marque a confirmação de direito de uso para analisar.'; throw new Error('Confirme que você tem direito de usar e analisar o arquivo.'); }
      const corpo = { id: r ? r.id : undefined, autorizado: true, inicio: Number($('#ra-ini').value) || 0, segundos: Number($('#ra-seg').value) || lim.padrao, caminho: $('#ra-caminho').value.trim() };
      prog.textContent = corpo.caminho ? 'Colocando na fila...' : 'Escolha o arquivo na janela que abriu.';
      $('#ra-ir').disabled = true;
      try {
        const t = await api('/api/referencias/analisar', corpo);
        if (t.cancelado) { prog.textContent = 'Nenhum arquivo escolhido.'; return; }
        const res = await aguardarTarefa(t.id, x => prog.replaceChildren(el('span', { textContent: x.estado === 'fila' ? 'Na fila, esperando outra tarefa terminar' : x.mensagem }),
          el('div', { className: 'barra' }, el('i', { style: `width:${Math.round(x.progresso * 100)}%` }))));
        avisar('Análise concluída.');
        await recarregar();
        if (R.ativo && R.aba === 'biblioteca') { R.painel = { modo: 'analise', id: res.id }; desenharPainel(); desenharFiltros(); desenharCartoes(); }
      } catch (e) {
        prog.className = 'ref-prog erro'; prog.textContent = e.message; throw e;
      } finally { const b = $('#ra-ir'); if (b) b.disabled = false; }
    });
    return el('div', { className: 'card bloco ref-pedido' },
      el('div', { className: 'topo-linha' }, el('h2', { className: 'tit', style: 'margin:0', textContent: r ? `Analisar arquivo · ${nomeRef(r)}` : 'Analisar arquivo do PC' }), fechar()),
      el('p', { className: 'dica', textContent: 'Roda neste PC, na fila de tarefas, com quadros reduzidos e 5 por segundo. Nada é enviado para fora e o arquivo não é copiado. '
        + 'Links não são baixados: use um vídeo seu ou que o criador liberou.' }),
      el('div', { className: 'opcoes' },
        el('label', {}, 'Começar em (segundos)', el('input', { id: 'ra-ini', type: 'number', min: 0, step: 1, value: 0 })),
        el('label', {}, `Analisar quantos segundos (até ${lim.maximo})`, el('input', { id: 'ra-seg', type: 'number', min: 1, max: lim.maximo, step: 1, value: lim.padrao })),
        el('label', { className: 'ref-largo' }, 'Caminho do arquivo (vazio abre a janela para escolher)',
          el('input', { id: 'ra-caminho', autocomplete: 'off', placeholder: 'D:\\Videos\\meu_reel.mp4', value: (r && (r.arquivo || (r.analise && r.analise.arquivo))) || '' }))),
      el('label', { className: 'marcar autoriza ref-marcar' }, el('input', { id: 'ra-aut', type: 'checkbox' }), R.d.autorizacao),
      el('div', { className: 'ref-acoes-linha' }, el('button', { id: 'ra-ir', className: 'btn', type: 'button', textContent: 'Analisar', onclick: analisar }), prog));
  }
  function painelAnalise(r) {
    const a = r.analise, s = a.sugestoes, v = a.video;
    const sugestao = x => el('div', { className: 'ref-sug' },
      el('div', { className: 'topo-linha' }, el('b', { textContent: x.nome }), el('span', { className: 'ref-conf', textContent: `força ${Math.round(x.confianca * 100)}%`, title: 'Soma dos motivos abaixo, de 0 a 90%' })),
      el('ul', {}, ...x.porque.map(p => el('li', {}, p.texto, ' ', el('small', { className: `ref-base ${p.base}`, textContent: BASE[p.base] || p.base })))));
    const evidencia = ev => el('div', { className: 'ref-evid' }, ...ev.slice(0, 14).map(e => el('span', { textContent: e.t0 !== undefined ? `${tempo(e.t0)}–${tempo(e.t1)}` : tempo(e.t) })),
      ev.length > 14 ? el('small', { textContent: `+${ev.length - 14}` }) : null);
    const linha = c => el('div', { className: 'ref-carac' },
      el('div', { className: 'topo-linha' }, el('b', { textContent: c.nome }), el('span', { className: `ref-nivel n-${c.confianca >= 0.75 ? 'alta' : c.confianca >= 0.5 ? 'media' : 'baixa'}`,
        textContent: `${c.nivel} · ${Math.round(c.confianca * 100)}%`, title: 'Confiança da medida' })),
      el('p', { textContent: c.valor }), c.evidencia.length ? evidencia(c.evidencia) : null, el('small', { textContent: c.metodo }));
    return el('div', { className: 'card bloco ref-analise' },
      el('div', { className: 'topo-linha' }, el('h2', { className: 'tit', style: 'margin:0', textContent: `Análise · ${nomeRef(r)}` }), fechar()),
      el('p', { className: 'dica', style: 'margin-top:4px', textContent: `${a.nome_arquivo} · trecho ${tempo(a.inicio)}–${tempo(a.fim)} · ${v.largura}x${v.altura} · ${v.fps} fps · `
        + `${a.amostragem.quadros} quadros lidos em ${a.amostragem.largura}x${a.amostragem.altura} · analisado em ${dataBr(a.data)}` }),
      el('p', { className: 'ref-aviso', textContent: a.aviso }),
      el('div', { className: 'ref-duas' },
        el('section', {}, el('h3', { textContent: 'Templates sugeridos' }), ...s.templates.map(sugestao)),
        el('section', {}, el('h3', { textContent: 'Efeitos sugeridos' }), ...(s.efeitos.length ? s.efeitos.map(sugestao) : [el('p', { className: 'dica', textContent: 'Nenhum efeito apareceu nas medidas.' })]))),
      el('p', { className: 'dica', textContent: `${s.aviso} No Editor, escolha o template e ajuste do seu jeito.` }),
      el('h3', { className: 'ref-sub', textContent: 'Características medidas' }),
      el('div', { className: 'ref-caracs' }, ...a.caracteristicas.map(linha)));
  }

  /* ---------- boas práticas ---------- */
  async function desenharBoas(corpo) {
    if (!R.bp) { corpo.replaceChildren(el('div', { className: 'vazio', textContent: 'Carregando...' })); R.bp = await api('/api/boas-praticas'); }
    const b = R.bp, ver = b.verificacao;
    corpo.replaceChildren(
      el('section', { className: 'card bloco' },
        el('div', { className: 'topo-linha' }, el('h2', { className: 'tit', style: 'margin:0', textContent: 'Boas práticas com fonte' }),
          el('button', { id: 'bp-verificar', className: 'btn leve mini', type: 'button', textContent: 'Verificar links', onclick: tentar(verificar) })),
        el('p', { className: 'dica', style: 'margin-top:4px', textContent: `Versão ${dataBr(b.versao)} · ${b.itens.length} itens · `
          + (ver ? `última verificação em ${dataBr(ver.data)}: ${ver.ok} de ${ver.total} links responderam` : 'links ainda não verificados') }),
        el('p', { className: 'ref-garantia', textContent: 'Nenhuma prática aqui garante alcance ou viralização. Cada item mostra o que a fonte diz, quando vale e de que tipo é.' }),
        el('div', { className: 'ref-legenda' }, ...Object.entries(TIPOS).map(([k, [n, d]]) => el('div', {}, el('span', { className: `ref-tipo ${k}`, textContent: n }), el('small', { textContent: d }))))),
      el('div', { id: 'bp-filtros' }), el('div', { id: 'bp-lista', className: 'ref-bp-grade' }));
    desenharBP();
  }
  function desenharBP() {
    const f = R.fbp, itens = R.bp.itens, ver = (R.bp.verificacao || {}).itens || {};
    const chips = (lista, atual, mudar) => lista.map(([id, t]) => el('button', { className: 'chip', type: 'button', textContent: t, ariaPressed: String(atual === id), onclick: () => { mudar(id); desenharBP(); } }));
    const plats = ['todas', ...Object.keys(PLAT_BP).filter(p => itens.some(i => i.plataforma === p))];
    $('#bp-filtros').replaceChildren(
      el('div', { className: 'filtros', style: 'margin-bottom:8px' }, ...chips(plats.map(p => [p, p === 'todas' ? 'Todas' : PLAT_BP[p]]), f.plataforma, v => { f.plataforma = v; })),
      el('div', { className: 'filtros' }, ...chips([['todos', 'Todos os tipos'], ...Object.entries(TIPOS).map(([k, [n]]) => [k, n])], f.tipo, v => { f.tipo = v; })));
    const ordem = Object.keys(TIPOS);
    const lista = itens.filter(i => (f.plataforma === 'todas' || i.plataforma === f.plataforma) && (f.tipo === 'todos' || i.tipo === f.tipo))
      .sort((x, y) => plats.indexOf(x.plataforma) - plats.indexOf(y.plataforma) || ordem.indexOf(x.tipo) - ordem.indexOf(y.tipo));
    $('#bp-lista').replaceChildren(...(lista.length ? lista.map(i => cartaoBP(i, ver[i.id])) : [el('div', { className: 'vazio', textContent: 'Nenhum item com esses filtros.' })]));
  }
  function regras(r) {
    const saida = [];
    if (r.area_segura) { const a = r.area_segura; saida.push(`Área livre em ${a.largura}x${a.altura}: topo ${a.topo} px, base ${a.base} px, esquerda ${a.esquerda} px, direita ${a.direita} px`); }
    if (r.resolucao) { const x = r.resolucao; saida.push(`Resolução${x.minimo ? ' mínima' : ''}: ${x.largura}x${x.altura}${x.proporcao ? ` (${x.proporcao})` : ''}`); }
    if (r.duracao) { const d = r.duracao; saida.push(`Duração: ${d.min ? `de ${durTxt(d.min)} ` : ''}${d.max != null ? `até ${durTxt(d.max)}` : ''}`); }
    if (r.fps) saida.push(`Quadros por segundo: mínimo ${r.fps.min}`);
    return saida;
  }
  function cartaoBP(i, v) {
    const lista = i.regra ? regras(i.regra) : [];
    return el('article', { className: `card ref-bp t-${i.tipo}` },
      el('div', { className: 'ref-bp-cab' }, el('span', { className: `ref-tipo ${i.tipo}`, textContent: (TIPOS[i.tipo] || [i.tipo])[0] }), selo(PLAT_BP[i.plataforma] || i.plataforma, COR[i.plataforma])),
      el('h3', { textContent: i.titulo }),
      el('p', { textContent: i.resumo }),
      el('p', { className: 'ref-quando' }, el('b', { textContent: 'Quando vale: ' }), i.aplicabilidade),
      lista.length ? el('ul', { className: 'ref-regra' }, ...lista.map(t => el('li', { textContent: t }))) : null,
      el('small', { className: 'ref-fonte' }, 'Fonte: ', el('a', { href: i.url, target: '_blank', rel: 'noopener noreferrer', textContent: i.fonte }), ` · consultada em ${dataBr(i.consultado_em)}`),
      v ? el('small', { className: `ref-verif ${v.status}`, textContent: v.status === 'ok' ? `Link respondeu (HTTP ${v.codigo})`
        : `Link não respondeu ao verificador (${v.erro}). Pode ser bloqueio a robôs: abra no navegador para conferir.` }) : null);
  }
  async function verificar() {
    const b = $('#bp-verificar');
    b.disabled = true; b.textContent = 'Verificando...';
    try {
      const v = await api('/api/boas-praticas/verificar', {});
      R.bp.verificacao = v;
      avisar(`${v.ok} de ${v.total} links responderam.`);
      if (R.ativo && R.aba === 'boas') desenhar();
    } finally { const n = $('#bp-verificar'); if (n) { n.disabled = false; n.textContent = 'Verificar links'; } }
  }

  window.Referencias = { mostrar, sair };
})();
