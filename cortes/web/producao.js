/* Produção: tudo o que o Vice Clips fez e está fazendo, separado por streamer e pela origem de cada corte
   (automático, clipe baixado, gravação da live, VOD/arquivo), com o porquê de cada um. Também o Resumo da live
   (os clipes mais vistos da live inteira e os picos) e o Compilado (os melhores clipes num vídeo só). */
(() => {
  const P = { dados: null, chave: '*', aba: 'geral', ordem: 'recentes', filtro: 'todos', sel: new Set(), resumo: {}, ultimo: 0, carregando: false, tarefasAss: '', pedidos: {} };
  const ABAS = [['geral', 'Visão geral'], ['auto', 'Automáticos'], ['clipes', 'Clipes baixados'], ['gravacoes', 'Lives gravadas'], ['live', 'Resumo da live e compilado'], ['outros', 'Outros']];
  const PERIODO = { '1h': 'na última hora', '6h': 'nas últimas 6 horas', '24h': 'nas últimas 24 horas', '7d': 'nos últimos 7 dias' };
  const COMO = { chat: 'Momento do chat', analise: 'Pico da análise', clipar_agora: 'Clipar agora' };
  const NOMES_AN = { iniciando: 'começando a análise', rodando: 'analisando', concluida: 'análise concluída', parada: 'análise parada', erro: 'erro na análise' };
  const nomeDe = k => (k === '*' ? 'Todos os streamers' : k || 'Sem streamer');
  const mbTxt = mb => (mb >= 1024 ? `${(mb / 1024).toFixed(1).replace('.', ',')} GB` : `${Math.round(mb || 0)} MB`);
  const quando = t => (t ? new Date(t * 1000).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '');
  const ha = t => { if (!t) return ''; const s = Date.now() / 1000 - t; return s < 90 ? 'agora há pouco' : s < 3600 ? `há ${Math.round(s / 60)} min` : s < 86400 ? `há ${Math.round(s / 3600)} h` : `há ${Math.round(s / 86400)} d`; };
  const tsIso = s => { const t = Date.parse(s || ''); return Number.isNaN(t) ? 0 : t / 1000; };
  const btn = (texto, fn, classe = 'btn leve mini', extra = {}) => el('button', { className: classe, type: 'button', textContent: texto, onclick: fn, ...extra });
  const grupo = () => (P.dados && P.dados.streamers.find(g => g.chave === P.chave)) || null;
  const andando = t => t.estado === 'fila' || t.estado === 'rodando';
  const corDe = g => CORES[(g.plataformas || [])[0]] || 'var(--suave)';
  const viewsDe = c => (c.agora && c.agora.views !== undefined ? c.agora.views : ((c.origem || {}).clipe || {}).views) ?? -1;

  /* De quem é uma tarefa: as novas trazem meta.streamer; as antigas, o nome no título. */
  function donoTarefa(t) {
    if (t.meta && t.meta.streamer !== undefined) return t.meta.streamer;
    const m = /\(([^()]+)\)\s*$/.exec(t.titulo || '') || /(?:Corte de|de) ([\w-]+)(?: \(|$)/.exec(t.titulo || '');
    return m ? m[1].toLowerCase() : '?';
  }
  const tarefasDe = chave => (G.tarefas || []).filter(t => chave === '*' || donoTarefa(t) === chave);

  async function carregar() {
    if (P.carregando) return;
    P.carregando = true;
    try { P.dados = await api('/api/producao'); P.ultimo = Date.now(); } finally { P.carregando = false; }
    const ids = new Set(P.dados.streamers.flatMap(g => g.cortes.map(c => c.id)));
    [...P.sel].forEach(id => { if (!ids.has(id)) P.sel.delete(id); });
    if (P.chave !== '*' && !P.dados.streamers.some(g => g.chave === P.chave)) P.chave = '*';
  }
  const assinatura = d => JSON.stringify(d.streamers.map(g => [g.chave, g.cortes.map(c => [c.id, c.estado, c.manter, c.editados.length, c.agora && c.agora.views]),
    g.gravacoes.map(v => [v.nome, v.gravando, v.analise && [v.analise.estado, v.analise.sugestoes.length], v.chat && v.chat.momentos.length]),
    g.automaticos.map(r => [r.id, r.ativo, r.ultima && r.ultima.quando]), g.compilados.map(c => c.nome)]));

  async function mostrar(opcoes = {}) {
    if (opcoes.streamer !== undefined) { P.chave = opcoes.streamer; P.aba = opcoes.aba || 'geral'; }
    const t = $('#tela-producao');
    if (!P.dados) t.replaceChildren(cabecalho(), el('div', { className: 'vazio', textContent: 'Juntando o que foi baixado, gravado e gerado...' }));
    try { await carregar(); } catch (e) { t.replaceChildren(cabecalho(), el('div', { className: 'vazio erro', textContent: e.message })); return; }
    P.tarefasAss = '';
    desenhar();
  }
  function sair() { const b = $('#pr-barra'); if (b) b.remove(); }
  async function recarregar() {
    const antes = P.dados ? assinatura(P.dados) : '';
    try { await carregar(); } catch { return; }
    if (G.tela === 'producao' && assinatura(P.dados) !== antes) desenhar(true);
  }
  /* A cada 2,5 s (junto com a Atividade): progresso no lugar; quando uma tarefa termina, recarrega os cortes. */
  function tick() {
    if (G.tela !== 'producao' || !P.dados) return;
    const ass = JSON.stringify((G.tarefas || []).map(t => [t.id, t.estado, !!t.cancelando]));
    if (ass !== P.tarefasAss) {
      const terminou = P.tarefasAss && (G.tarefas || []).some(t => !andando(t));
      P.tarefasAss = ass; pintarFazendo();
      if (terminou) recarregar();
    } else {
      document.querySelectorAll('#tela-producao [data-id]').forEach(item => {
        const t = (G.tarefas || []).find(x => x.id === item.dataset.id);
        if (!t) return;
        const pct = Math.round((t.progresso || 0) * 100), msg = item.querySelector('.at-msg'), barra = item.querySelector('.barra i'), vazio = item.querySelector('.at-thumb.vazio');
        if (msg) msg.textContent = `${NOMES_TAREFA[t.estado] || t.estado} · ${t.mensagem}${t.estado === 'rodando' ? ` · ${pct}%` : ''}`;
        if (barra && t.estado === 'rodando') barra.style.width = `${pct}%`;
        if (vazio && t.estado === 'rodando') vazio.textContent = `${pct}%`;
      });
    }
    if (Date.now() - P.ultimo > 20000) recarregar();
  }

  /* ---------------------------------------------------------------- moldura */
  function cabecalho() {
    return el('header', { className: 'cabeca topo-linha', style: 'flex-wrap:wrap' },
      el('div', {}, el('h1', { textContent: 'Produção' }), el('p', { textContent: 'O que foi baixado, gravado e gerado, separado por streamer e por origem, com o porquê de cada corte. Marque ★ o que quer guardar e exclua o resto.' })),
      el('span', { className: 'ferramentas', style: 'margin:0' },
        btn('Atualizar', tentar(async () => { await carregar(); desenhar(true); avisar('Atualizado.'); })),
        btn('Atividade', () => abrirAtividade()),
        btn('Espaço em disco', () => { irPara('config'); setTimeout(() => { const s = $('#cfg-espaco'); if (s) s.scrollIntoView({ behavior: 'smooth' }); }, 500); })));
  }
  function desenhar(manterRolagem) {
    const y = window.scrollY;
    $('#tela-producao').replaceChildren(cabecalho(), el('div', { className: 'pr-layout' }, listaStreamers(), el('section', { id: 'pr-corpo', className: 'pr-corpo' }, ...corpo())));
    pintarFazendo(); barraSel();
    if (manterRolagem) window.scrollTo(0, y);
  }
  function ir(chave, aba = 'geral') { P.chave = chave; P.aba = aba; P.sel.clear(); desenhar(); window.scrollTo(0, 0); }

  function listaStreamers() {
    const gs = P.dados.streamers;
    const item = (chave, titulo, sub, cor, extras = []) => el('button', { className: 'pr-st' + (chave === P.chave ? ' ativo' : ''), type: 'button', onclick: () => ir(chave) },
      el('span', { className: 'pr-av', style: `--cor:${cor}`, textContent: chave === '*' ? '∗' : (chave || '?')[0].toUpperCase() }),
      el('span', { className: 'pr-st-nome' }, el('b', { textContent: titulo }), el('small', { textContent: sub })), ...extras);
    const total = gs.reduce((s, g) => s + g.cortes.length, 0);
    return el('aside', { className: 'pr-lista card' },
      item('*', 'Todos', `${total} cortes · ${gs.length} streamers`, 'var(--rosa)'),
      ...gs.map(g => {
        const fazendo = tarefasDe(g.chave).filter(andando).length, rec = g.gravacoes.some(v => v.gravando), auto = g.automaticos.some(r => r.ativo);
        const reels = g.cortes.filter(c => c.editados.length).length;
        return item(g.chave, nomeDe(g.chave), [`${g.cortes.length} cortes`, reels ? `${reels} Reels` : '', g.gravacoes.length ? `${g.gravacoes.length} gravaç${g.gravacoes.length === 1 ? 'ão' : 'ões'}` : ''].filter(Boolean).join(' · '), corDe(g),
          [el('span', { className: 'pr-st-selos' }, rec ? el('span', { className: 'selo live', textContent: 'REC' }) : null, auto ? el('span', { className: 'selo', style: '--cor:var(--ciano)', textContent: 'AUTO' }) : null,
            fazendo ? el('span', { className: 'selo', style: '--cor:var(--sol)', textContent: `${fazendo} fazendo` }) : null)]);
      }));
  }
  function corpo() {
    if (P.chave === '*') return visaoTodos();
    const g = grupo();
    if (!g) return [el('div', { className: 'vazio', textContent: 'Streamer não encontrado.' })];
    const n = {
      geral: null, auto: g.cortes.filter(c => c.origem.tipo === 'auto').length + g.automaticos.length, clipes: g.cortes.filter(c => c.origem.tipo === 'clipe').length,
      gravacoes: g.gravacoes.length, live: g.compilados.length, outros: g.cortes.filter(c => ['vod', 'arquivo'].includes(c.origem.tipo)).length,
    };
    const abas = ABAS.filter(([id]) => id !== 'outros' || n.outros).filter(([id]) => id !== 'live' || g.chave);
    if (!abas.some(([id]) => id === P.aba)) P.aba = 'geral';
    const conteudo = { geral: abaGeral, auto: abaAuto, clipes: abaClipes, gravacoes: abaGravacoes, live: abaLive, outros: abaOutros }[P.aba](g);
    return [cartaoStreamer(g),
      el('div', { className: 'filtros', role: 'tablist', style: 'margin:14px 0' }, ...abas.map(([id, t]) => el('button', { className: 'chip', type: 'button', role: 'tab', ariaPressed: String(id === P.aba),
        textContent: n[id] === null || n[id] === undefined ? t : `${t} (${n[id]})`, onclick: () => { P.aba = id; desenhar(true); } }))),
      ...conteudo];
  }

  /* ---------------------------------------------------------------- visão geral */
  function numero(valor, rotulo, cls = '') { return el('div', { className: 'card numero ' + cls }, el('b', { textContent: valor }), el('span', { textContent: rotulo })); }
  function cartaoStreamer(g) {
    const canal = (G.canais.canais || []).find(c => c.login === g.chave);
    const discoCortes = g.cortes.reduce((s, c) => s + (c.mb || 0), 0), discoGrav = g.gravacoes.reduce((s, v) => s + (v.mb || 0), 0);
    const semReel = g.cortes.filter(c => !c.editados.length);
    return el('section', { className: 'card bloco pr-cab' },
      el('div', { className: 'pr-cab-topo' }, el('span', { className: 'pr-av grande', style: `--cor:${corDe(g)}`, textContent: (g.chave || '?')[0].toUpperCase() }),
        el('div', {}, el('h2', { className: 'pr-nome', textContent: nomeDe(g.chave) }),
          el('div', { className: 'pr-chips' }, ...g.plataformas.map(p => el('span', { className: 'selo', style: `--cor:${CORES[p]}`, textContent: PLATAFORMA[p] })),
            canal && canal.online ? el('span', { className: 'selo live', textContent: `ao vivo · ${fmtNum(canal.espectadores)}` }) : null,
            g.gravacoes.some(v => v.gravando) ? el('span', { className: 'selo live', textContent: 'gravando agora' }) : null,
            g.tem_layout ? el('span', { className: 'pr-chip ok', textContent: 'layout salvo: sai como Reel' }) : null))),
      el('div', { className: 'numeros pr-numeros' }, numero(g.cortes.length, 'Cortes'), numero(g.cortes.filter(c => c.editados.length).length, 'Com Reel exportado'),
        numero(tarefasDe(g.chave).filter(andando).length, 'Fazendo agora', 'ao-vivo'), numero(mbTxt(discoCortes + discoGrav), `No disco (gravações ${mbTxt(discoGrav)})`)),
      !g.tem_layout && semReel.length && g.chave ? el('p', { className: 'pr-alerta' }, `${nomeDe(g.chave)} não tem layout salvo, então os cortes ficam prontos sem Reel (${semReel.length} agora). Abra um no editor, monte o template e clique em “Salvar para este streamer”: daí em diante o automático já sai renderizado, e aqui dá para renderizar os prontos de uma vez. `,
        btn('Abrir o mais recente no editor', () => irPara('editor', { corte: semReel[0].id }))) : null);
  }
  function abaGeral(g) {
    const conta = tipo => g.cortes.filter(c => c.origem.tipo === tipo);
    const atalho = (aba, titulo, linhas) => el('button', { className: 'card pr-atalho', type: 'button', onclick: () => { P.aba = aba; desenhar(true); } }, el('b', { textContent: titulo }), ...linhas.filter(Boolean).map(t => el('small', { textContent: t })));
    const outros = g.cortes.filter(c => ['vod', 'arquivo'].includes(c.origem.tipo));
    return [
      el('section', { className: 'card bloco' }, el('h2', { className: 'tit', textContent: 'Fazendo agora' }), el('div', { id: 'pr-fazendo', className: 'at-secao' })),
      el('div', { className: 'pr-atalhos' },
        atalho('auto', 'Automáticos', [`${conta('auto').length} cortes`, `${g.automaticos.filter(r => r.ativo).length} ligado(s) de ${g.automaticos.length}`]),
        atalho('clipes', 'Clipes baixados', [`${conta('clipe').length} cortes`, 'Gerar conteúdo, Editar clipe e Resumo da live']),
        atalho('gravacoes', 'Lives gravadas', [`${g.gravacoes.length} gravações · ${mbTxt(g.gravacoes.reduce((s, v) => s + v.mb, 0))}`, `${conta('gravacao').length} cortes delas`]),
        g.chave ? atalho('live', 'Resumo da live e compilado', ['Mais vistos da live inteira, picos', `${g.compilados.length} compilado(s)`]) : null,
        outros.length ? atalho('outros', 'Outros', [`${outros.length} cortes de VOD ou arquivo`]) : null),
      secaoCortes('Cortes mais recentes', g.cortes.slice(0, 8), { semFiltros: true, rodape: g.cortes.length > 8 ? `Mostrando 8 de ${g.cortes.length}. Os outros estão nas abas de cada origem.` : '' })];
  }
  function visaoTodos() {
    const gs = P.dados.streamers, cortes = gs.flatMap(g => g.cortes);
    const discoC = cortes.reduce((s, c) => s + (c.mb || 0), 0), discoG = gs.flatMap(g => g.gravacoes).reduce((s, v) => s + v.mb, 0);
    const conta = (g, tipo) => g.cortes.filter(c => c.origem.tipo === tipo).length;
    const linha = g => el('tr', { onclick: () => ir(g.chave), title: `Abrir ${nomeDe(g.chave)}` },
      el('td', {}, el('span', { className: 'pr-st-nome inline' }, el('span', { className: 'pr-av', style: `--cor:${corDe(g)}`, textContent: (g.chave || '?')[0].toUpperCase() }), el('b', { textContent: nomeDe(g.chave) }))),
      el('td', { textContent: g.plataformas.map(p => PLATAFORMA[p]).join(', ') || '-' }),
      el('td', { textContent: conta(g, 'auto') }), el('td', { textContent: conta(g, 'clipe') }), el('td', { textContent: conta(g, 'gravacao') }),
      el('td', { textContent: g.cortes.filter(c => c.editados.length).length }), el('td', { textContent: `${g.gravacoes.length}${g.gravacoes.some(v => v.gravando) ? ' (REC)' : ''}` }),
      el('td', { textContent: mbTxt(g.cortes.reduce((s, c) => s + (c.mb || 0), 0) + g.gravacoes.reduce((s, v) => s + v.mb, 0)) }),
      el('td', { textContent: g.ultimo ? ha(g.ultimo) : '-' }));
    return [
      el('div', { className: 'numeros pr-numeros' }, numero(cortes.length, 'Cortes'), numero(cortes.filter(c => c.editados.length).length, 'Com Reel exportado'),
        numero((G.tarefas || []).filter(andando).length, 'Fazendo agora', 'ao-vivo'), numero(mbTxt(discoC + discoG), `No disco (gravações ${mbTxt(discoG)})`)),
      el('section', { className: 'card bloco' }, el('h2', { className: 'tit', textContent: 'Fazendo agora (todos)' }), el('div', { id: 'pr-fazendo', className: 'at-secao' })),
      el('section', { className: 'card bloco' }, el('h2', { className: 'tit', textContent: 'Por streamer' }),
        el('div', { className: 'pr-tabela-caixa' }, el('table', { className: 'pr-tabela' },
          el('thead', {}, el('tr', {}, ...['Streamer', 'Plataforma', 'Automáticos', 'Clipes', 'Da gravação', 'Com Reel', 'Gravações', 'Disco', 'Última atividade'].map(t => el('th', { textContent: t })))),
          el('tbody', {}, ...gs.map(linha)))),
        el('p', { className: 'dica', textContent: 'Clique num streamer para ver cada corte com a origem e o motivo, as gravações com os momentos achados, os automáticos com cada rodada e o resumo da última live.' })),
      P.dados.regras_gerais.length ? el('section', { className: 'card bloco' }, el('h2', { className: 'tit', textContent: 'Automáticos de categoria' }), ...P.dados.regras_gerais.map(r => cartaoRegra(r))) : null].filter(Boolean);
  }
  function pintarFazendo() {
    const caixa = $('#pr-fazendo');
    if (!caixa) return;
    const ts = tarefasDe(P.chave), ativas = ts.filter(andando).reverse(), erros = ts.filter(t => t.estado === 'erro').slice(0, 4);
    caixa.replaceChildren(...(ativas.length || erros.length ? [...ativas, ...erros].map(itemAtividade)
      : [el('p', { className: 'dica', style: 'margin:0', textContent: 'Nada em andamento. Downloads, cortes, renders e compilados aparecem aqui com o progresso.' })]));
  }

  /* ---------------------------------------------------------------- cortes: linha com origem e motivo */
  function chipsOrigem(c) {
    const o = c.origem || {}, k = o.clipe || {}, ag = c.agora || {};
    const chip = (txt, cls = '', title = '') => el('span', { className: 'pr-chip ' + cls, textContent: txt, title });
    const out = [];
    if (o.tipo === 'auto') out.push(chip('Automático', 'auto'));
    else if (o.tipo === 'clipe') out.push(chip(o.como === 'live' ? 'Resumo da live' : o.como === 'gerar' ? 'Gerar conteúdo' : o.como === 'editar' ? 'Editar clipe' : 'Clipe baixado', 'clipe'));
    else if (o.tipo === 'gravacao') out.push(chip(o.auto ? 'Clipado sozinho' : (COMO[o.como] || 'Da gravação'), 'grav'));
    else out.push(chip(o.tipo === 'vod' ? 'VOD' : 'Arquivo', 'outro'));
    const nota = c.nota ?? o.nota;
    if (nota !== null && nota !== undefined) out.push(chip(`Nota ${nota}`, 'nota', 'Estimativa de relevância do momento (0 a 100)'));
    if (o.posicao) out.push(chip(`${o.posicao}º de ${o.total || '?'}`, '', 'Posição pelo número de views quando foi escolhido'));
    if (k.views !== undefined && !o.inferido) out.push(chip(`${fmtNum(k.views)} views na escolha`));
    if (ag.views !== undefined) {
      const ganho = k.views !== undefined && !o.inferido ? ag.views - k.views : 0;
      out.push(chip(`${fmtNum(ag.views)} views agora${ganho > 0 ? ` (+${fmtNum(ganho)})` : ''}`, 'agora', `Consultado ${ha(ag.visto)}`));
    }
    if (ag.sumiu) out.push(chip('clipe apagado na plataforma', 'aviso'));
    const autor = k.autor || ag.autor;
    if (autor) out.push(chip(`clipado por ${autor}`));
    const criado = tsIso(k.criado || ag.criado);
    if (criado) out.push(chip(`clipe de ${quando(criado)}`));
    if (o.tipo === 'gravacao' && o.pico !== undefined && o.pico !== null) out.push(chip(`${tempoVivo(o.pico)} da gravação`));
    return out;
  }
  function porque(c) {
    const o = c.origem || {}, k = o.clipe || {};
    if (o.tipo === 'auto') {
      if (o.inferido) return `Pego pelo automático “${o.regra_nome}”${o.regra_excluida ? ' (que você já excluiu)' : ''}. Corte de antes do registro detalhado: a posição e as views da hora da escolha não foram guardadas.`;
      return `Pego pelo automático “${o.regra_nome}” na rodada das ${horaCurta(o.quando)}: era o ${o.posicao}º mais visto ${PERIODO[o.intervalo] || 'no período'} entre ${o.total} clipes`
        + `${o.ja_feitos ? `; ${o.ja_feitos} já tinham virado corte` : ''}${o.abaixo ? `; ${o.abaixo} tinham menos de ${o.minimo} views` : ''}. Entrou como ${o.escolha}º dos ${o.quantos} da rodada.`;
    }
    if (o.tipo === 'clipe') {
      if (o.como === 'live') return `Escolhido no Resumo da live${o.live && o.live.titulo ? ` “${o.live.titulo}”` : ''}: ${o.posicao}º mais visto da live inteira (${fmtNum(k.views)} views na hora).`;
      if (o.como === 'gerar') return `Você clicou em Gerar conteúdo: era o ${o.posicao}º da lista${o.lista ? ` (${o.lista})` : ''}, com ${fmtNum(k.views)} views na hora.`;
      if (o.como === 'editar') return `Você escolheu este clipe em Clipes em alta (Editar clipe), com ${fmtNum(k.views)} views na hora.`;
      return 'Clipe baixado em Clipes em alta (Gerar conteúdo ou Editar clipe). Corte de antes do registro detalhado: o motivo exato não foi guardado.';
    }
    if (o.tipo === 'gravacao') {
      const mot = (o.motivos || []).join(' · '), fala = o.fala ? ` Fala: “${o.fala}”` : '', auto = o.auto ? `Clipado sozinho (nota ≥ ${o.auto}). ` : '';
      if (o.como === 'clipar_agora') return `Você clicou em Clipar agora: os últimos ${o.segundos || 30} s da gravação naquele instante.`;
      if (o.como === 'chat') return `${auto}O chat explodiu: ${mot || 'pico de mensagens'}.${fala}`;
      if (o.como === 'analise') return `${auto}A análise da gravação achou um pico: ${mot || 'voz, som ou imagem acima do normal'}.${fala}`;
      return `Corte da gravação ${o.gravacao}. ${c.motivo && c.motivo !== 'Trecho escolhido manualmente.' ? c.motivo : 'O motivo não foi guardado (corte de antes do registro detalhado).'}`;
    }
    if (o.tipo === 'vod') return 'Trecho escolhido por você em uma gravação (VOD) da plataforma.';
    return c.motivo && c.motivo !== 'Trecho escolhido manualmente.' ? c.motivo : 'Trecho escolhido por você em um arquivo deste PC.';
  }
  function linhaCorte(c) {
    const o = c.origem || {}, reel = c.editados[0], urlClipe = (o.clipe && o.clipe.url) || (c.agora && c.agora.url);
    const caixa = el('input', { type: 'checkbox', checked: P.sel.has(c.id) });
    const item = el('div', { className: 'pr-corte' + (P.sel.has(c.id) ? ' marcado' : '') + (c.manter ? ' manter' : '') },
      el('label', { className: 'pr-check', title: 'Selecionar (para manter, renderizar ou excluir vários)' }, caixa),
      el('button', { className: 'pr-capa', type: 'button', title: 'Assistir', onclick: () => verVideo(c.url, c.texto) }, el('img', { src: c.thumb, alt: '', loading: 'lazy' }),
        el('span', { className: 'tempo', textContent: `${c.duracao}s` }), reel ? el('span', { className: 'pr-reel', textContent: c.editados.length > 1 ? `${c.editados.length} Reels` : 'Reel' }) : null),
      el('div', { className: 'pr-info' },
        el('div', { className: 'pr-tit' }, el('b', { textContent: c.texto || '(sem título)', title: c.texto || '' }), el('span', { className: `estado ${c.estado}`, textContent: ESTADOS[c.estado] || '' }),
          c.manter ? el('span', { className: 'pr-chip ok', textContent: '★ manter' }) : null),
        el('div', { className: 'pr-chips' }, ...chipsOrigem(c)),
        el('p', { className: 'pr-porque', textContent: porque(c) }),
        el('small', { className: 'pr-meta', textContent: [c.criado ? `criado ${ha(c.criado)} (${quando(c.criado)})` : '', `${mbTxt(c.mb)} no disco`, o.tipo === 'vod' || o.tipo === 'arquivo' ? c.live : ''].filter(Boolean).join(' · ') })),
      el('div', { className: 'pr-acoes' },
        btn(c.manter ? '★ Mantendo' : '☆ Manter', tentar(() => marcarManter([c.id], !c.manter)), 'btn leve mini' + (c.manter ? ' pr-mantendo' : ''), { title: 'Marca para guardar. Na hora de limpar, dá para selecionar só os não marcados.' }),
        btn('Assistir', () => verVideo(c.url, c.texto)),
        reel ? btn('Ver Reel', () => verVideo(reel.url, c.texto)) : null,
        btn('Abrir no editor', () => irPara('editor', { corte: c.id }), 'btn mini'),
        urlClipe ? el('a', { className: 'btn leve mini', href: urlClipe, target: '_blank', rel: 'noopener', textContent: 'Clipe original' }) : null,
        btn('Excluir', confirmarClique('Confirmar', tentar(() => excluir([c.id]))), 'btn leve mini perigo')));
    caixa.onchange = () => { if (caixa.checked) P.sel.add(c.id); else P.sel.delete(c.id); item.classList.toggle('marcado', caixa.checked); barraSel(); };
    return item;
  }
  const FILTROS = [['todos', 'Todos'], ['sem_reel', 'Sem Reel'], ['com_reel', 'Com Reel'], ['manter', '★ Marcados'], ['nao_manter', 'Não marcados']];
  const passa = c => ({ todos: true, sem_reel: !c.editados.length, com_reel: !!c.editados.length, manter: c.manter, nao_manter: !c.manter }[P.filtro]);
  function ordenar(lista) {
    const l = [...lista];
    if (P.ordem === 'views') l.sort((a, b) => viewsDe(b) - viewsDe(a) || (b.nota ?? b.origem.nota ?? -1) - (a.nota ?? a.origem.nota ?? -1));
    else if (P.ordem === 'nota') l.sort((a, b) => (b.nota ?? b.origem.nota ?? -1) - (a.nota ?? a.origem.nota ?? -1));
    else if (P.ordem === 'disco') l.sort((a, b) => (b.mb || 0) - (a.mb || 0));
    else l.sort((a, b) => (b.criado || 0) - (a.criado || 0));
    return l;
  }
  /* Uma seção de cortes: filtros (Reel, marcados), ordem e seleção rápida para limpar. */
  function secaoCortes(titulo, lista, op = {}) {
    const visiveis = op.semFiltros ? lista : ordenar(lista.filter(passa));
    const selecionar = filtro => () => { visiveis.filter(filtro).forEach(c => P.sel.add(c.id)); desenhar(true); };
    const mb = lista.reduce((s, c) => s + (c.mb || 0), 0);
    const sel = (valor, opcoes, mudar) => el('select', { onchange: e => { mudar(e.target.value); desenhar(true); } }, ...opcoes.map(([v, t]) => el('option', { value: v, textContent: t, selected: v === valor })));
    return el('section', { className: 'card bloco pr-secao' },
      el('div', { className: 'topo-linha', style: 'flex-wrap:wrap;margin-bottom:10px' }, el('h2', { className: 'tit', style: 'margin:0', textContent: `${titulo} (${lista.length}${lista.length ? ` · ${mbTxt(mb)}` : ''})` }),
        lista.length && !op.semFiltros ? el('span', { className: 'ferramentas', style: 'margin:0' },
          sel(P.ordem, [['recentes', 'Mais recentes'], ['views', 'Mais vistos'], ['nota', 'Maior nota'], ['disco', 'Ocupa mais espaço']], v => { P.ordem = v; }),
          ...FILTROS.map(([id, t]) => el('button', { className: 'chip', type: 'button', textContent: t, ariaPressed: String(id === P.filtro), onclick: () => { P.filtro = id; desenhar(true); } }))) : null),
      lista.length && !op.semFiltros ? el('div', { className: 'pr-selrapida' }, el('span', { className: 'dica', style: 'margin:0', textContent: 'Selecionar:' }),
        btn(`todos daqui (${visiveis.length})`, selecionar(() => true)), btn('só os não marcados ★', selecionar(c => !c.manter)), btn('só os sem Reel', selecionar(c => !c.editados.length))) : null,
      ...(visiveis.length ? visiveis.map(linhaCorte) : [el('p', { className: 'dica', style: 'margin:0', textContent: lista.length ? 'Nenhum corte com esse filtro.' : (op.vazio || 'Nenhum corte aqui ainda.') })]),
      op.rodape ? el('p', { className: 'dica', textContent: op.rodape }) : null);
  }

  /* ---------------------------------------------------------------- ações */
  async function marcarManter(ids, sim) {
    await api('/api/producao/manter', { cortes: ids, manter: sim });
    avisar(sim ? `${ids.length} corte(s) marcados para manter.` : 'Marcação tirada.');
    await carregar(); desenhar(true);
  }
  async function excluir(ids) {
    const r = await api('/api/corte/excluir', { cortes: ids });
    ids.forEach(i => P.sel.delete(i));
    await carregar(); desenhar(true);
    avisoDesfazer(`${r.lixeiras.length} corte(s) excluído(s)${r.erros.length ? `, ${r.erros.length} com erro` : ''}. Ficam na lixeira do Vice Clips até você esvaziar.`, r.lixeiras);
    carregarLives().catch(() => {});
  }
  async function renderizar(cortes) {
    const r = await api('/api/producao/renderizar', { cortes: cortes.map(c => c.id) });
    avisar(`${r.tarefas.length} Reel(s) na fila. Acompanhe em Fazendo agora.`);
    G.tarefas = await api('/api/tarefas'); pintarFazendo();
  }
  function barraSel() {
    let b = $('#pr-barra');
    if (!P.sel.size || G.tela !== 'producao' || !P.dados) { if (b) b.remove(); return; }
    if (!b) { b = el('div', { id: 'pr-barra', className: 'barra-selecao card' }); document.body.append(b); }
    const sel = P.dados.streamers.flatMap(g => g.cortes).filter(c => P.sel.has(c.id)), ids = sel.map(c => c.id);
    b.replaceChildren(el('b', { textContent: `${sel.length} selecionado(s) · ${mbTxt(sel.reduce((s, c) => s + (c.mb || 0), 0))}` }),
      btn('★ Manter', tentar(() => marcarManter(ids, true))), btn('Tirar ★', tentar(() => marcarManter(ids, false))),
      btn('Renderizar no layout', tentar(() => renderizar(sel)), 'btn leve mini', { title: 'Renderiza como Reel no layout salvo do streamer, com o título do corte na manchete' }),
      btn(`Excluir ${sel.length}`, confirmarClique(`Confirmar: excluir ${sel.length}`, tentar(() => excluir(ids))), 'btn mini perigo-forte'),
      btn('Limpar seleção', () => { P.sel.clear(); desenhar(true); }));
  }

  /* ---------------------------------------------------------------- automáticos */
  function linhaRodada(u) {
    const partes = u.erro ? [`erro: ${u.erro}`] : [`${u.vistos} clipes no período`, u.ja_feitos !== undefined ? `${u.ja_feitos} já eram corte` : '', u.abaixo ? `${u.abaixo} abaixo do mínimo` : '',
      u.elegiveis !== undefined ? `${u.elegiveis} podiam entrar` : '', `pegou ${u.novos}`];
    return el('div', { className: 'pr-rodada' + (u.erro ? ' erro' : '') }, el('b', { textContent: quando(u.quando) }), el('span', { textContent: partes.filter(Boolean).join(' · ') }),
      u.clipes && u.clipes.length ? el('div', { className: 'pr-chips' }, ...u.clipes.map(k => el('span', { className: 'pr-chip', textContent: `${k.posicao ? `#${k.posicao} · ` : ''}${fmtNum(k.views)} views · ${k.titulo}` }))) : null);
  }
  function cartaoRegra(r) {
    const c = r.consulta || {}, freq = r.a_cada >= 60 ? `${r.a_cada / 60} h` : `${r.a_cada} min`;
    const fazer = acao => tentar(async () => {
      await api('/api/auto/acao', { id: r.id, acao });
      if (acao === 'agora') avisar('Rodando agora: os clipes novos aparecem em Fazendo agora.');
      await carregar(); desenhar(true);
    });
    const hist = [...(r.historico || [])].reverse();
    const quem = r.quem === 'comunidade' ? ' (só os feitos por espectadores)' : r.quem === 'proprio' ? ' (só os do próprio streamer)' : '';
    const modelo = r.modelo === 'nenhum' ? 'Só baixa e corta (sem Reel).' : r.modelo === 'streamer' ? 'Renderiza no layout salvo do streamer, se houver; sem layout, o corte fica pronto para editar.' : `Renderiza no template ${r.modelo}.`;
    return el('section', { className: 'card bloco pr-regra' + (r.ativo ? ' ligada' : '') },
      el('div', { className: 'topo-linha', style: 'flex-wrap:wrap' }, el('div', {}, el('h2', { className: 'pr-nome pequeno', textContent: r.nome }),
        el('small', { className: 'pr-sub', textContent: r.ativo ? `Ligado · próxima rodada às ${horaCurta(r.proxima)}` : 'Pausado' })),
        el('span', { className: 'ferramentas', style: 'margin:0' }, btn('Rodar agora', fazer('agora'), 'btn mini'), btn(r.ativo ? 'Pausar' : 'Retomar', fazer(r.ativo ? 'pausar' : 'retomar')),
          btn('Excluir', confirmarClique('Confirmar', fazer('excluir')), 'btn leve mini perigo'))),
      el('p', { className: 'pr-porque', textContent: `Como escolhe: a cada ${freq}, lista os clipes ${PERIODO[c.intervalo] || ''} de ${c.nome || c.canal || 'categoria'}${quem}, ordena pelas views e pega os ${r.quantos} primeiros que ainda não viraram corte e têm ${r.minimo > 0 ? `${r.minimo} views ou mais` : 'qualquer número de views'}. ${modelo} Já pegou ${r.n_feitos} clipes.` }),
      el('h3', { className: 'tit', style: 'margin:12px 0 6px', textContent: `Rodadas (${hist.length})` }),
      hist.length ? el('div', { className: 'pr-rodadas' }, ...hist.slice(0, 12).map(linhaRodada)) : el('p', { className: 'dica', style: 'margin:0', textContent: 'Ainda não rodou.' }));
  }
  function abaAuto(g) {
    const autos = g.cortes.filter(c => c.origem.tipo === 'auto');
    const partes = [];
    if (!g.automaticos.length) partes.push(el('div', { className: 'vazio' }, el('p', { textContent: `Nenhum automático ligado para ${nomeDe(g.chave)}. Em Lives → Clipes em alta, escolha o canal e clique em Automático.` }),
      btn('Abrir Clipes em alta', () => irPara('descobrir', { aba: 'clips' }), 'btn mini', { style: 'margin-top:10px' })));
    g.automaticos.forEach(r => partes.push(cartaoRegra(r), secaoCortes(`Cortes de “${r.nome}”`, autos.filter(c => c.origem.regra === r.id), { vazio: 'Nenhum corte deste automático ainda.' })));
    const orfaos = autos.filter(c => !g.automaticos.some(r => r.id === c.origem.regra));
    if (orfaos.length) partes.push(secaoCortes('De automáticos já excluídos', orfaos));
    return partes;
  }
  function abaClipes(g) {
    const cl = g.cortes.filter(c => c.origem.tipo === 'clipe');
    const grupos = [['live', 'Do Resumo da live'], ['gerar', 'Gerar conteúdo (Top N)'], ['editar', 'Editar clipe'], ['', 'Clipes baixados antes do registro detalhado']];
    const partes = grupos.map(([como, t]) => [t, cl.filter(c => (c.origem.como || '') === como)]).filter(([, l]) => l.length).map(([t, l]) => secaoCortes(t, l));
    return partes.length ? partes : [el('div', { className: 'vazio', textContent: 'Nenhum clipe baixado deste streamer. Em Lives → Clipes em alta, use Gerar conteúdo ou Editar clipe; ou aqui, em Resumo da live.' })];
  }
  function abaOutros(g) {
    return [secaoCortes('Cortes de VOD e de arquivos', g.cortes.filter(c => ['vod', 'arquivo'].includes(c.origem.tipo)))];
  }

  /* ---------------------------------------------------------------- gravações (live completa) */
  function abaGravacoes(g) {
    const da = nome => g.cortes.filter(c => c.origem.tipo === 'gravacao' && c.origem.gravacao === nome);
    const partes = g.gravacoes.map(gv => cartaoGravacao(gv, da(gv.nome)));
    const soltos = g.cortes.filter(c => c.origem.tipo === 'gravacao' && !g.gravacoes.some(v => v.nome === c.origem.gravacao));
    if (soltos.length) partes.push(secaoCortes('Cortes de gravações já apagadas', soltos));
    return partes.length ? partes : [el('div', { className: 'vazio', textContent: 'Nenhuma gravação deste streamer. Na live, use Gravar e clipar (Kick) ou Analisar ao vivo (Twitch).' })];
  }
  function cartaoGravacao(gv, cortes) {
    const a = gv.analise, sug = a ? [...a.sugestoes].sort((x, y) => (y.nota || 0) - (x.nota || 0)) : [];
    const corteDo = s => cortes.find(c => (c.origem.pico !== undefined && c.origem.pico !== null && Math.abs(c.origem.pico - s.pico) < 1) || Math.abs((c.inicio ?? -99) - s.inicio) < 1.5);
    const pedido = chave => P.pedidos[`${gv.nome}:${chave}`];
    const pedir = (chave, fn) => tentar(async () => { await fn(); P.pedidos[`${gv.nome}:${chave}`] = 1; avisar('Corte na fila: acompanhe em Fazendo agora (Visão geral).'); G.tarefas = await api('/api/tarefas'); desenhar(true); });
    const livres = sug.filter(s => !corteDo(s) && !pedido(`a${s.indice}`));
    const chatMom = ((gv.chat && gv.chat.momentos) || []).filter(m => m.fim !== undefined && !m.corte && !pedido(`c${m.indice}`)).sort((x, y) => y.nota - x.nota);
    const estadoAn = !a ? 'sem análise' : a.rodando ? `analisando (até ${tempoVivo(a.processado)})` : (['iniciando', 'rodando'].includes(a.estado) ? 'análise interrompida' : NOMES_AN[a.estado] || a.estado);
    const linhaMomento = (nota, titulo, detalhe, acao) => el('div', { className: 'at-item at-momento' }, el('span', { className: 'dc-nota', textContent: nota, title: 'Nota do momento: estimativa de relevância, não prevê alcance' }),
      el('div', { className: 'at-info' }, el('b', { textContent: titulo }), el('small', { textContent: detalhe })), el('div', { className: 'at-acoes' }, acao));
    const momentos = [
      ...livres.slice(0, 12).map(s => linhaMomento(s.nota, `${tempoVivo(s.pico)} da gravação · corte de ${Math.round(s.fim - s.inicio)} s · análise`, (s.motivos || []).join(' · ') + (s.fala ? ` · “${s.fala}”` : ''),
        btn('Criar corte', pedir(`a${s.indice}`, () => api('/api/producao/corte-momento', { fonte: a.fonte, indice: s.indice, streamer: gv.login }))))),
      ...chatMom.slice(0, 8).map(m => linhaMomento(m.nota, `${tempoVivo(m.pico)} da gravação · chat`, (m.motivos || []).join(' · '),
        btn('Criar corte', pedir(`c${m.indice}`, () => api('/api/descobrir/aovivo/momento', { login: gv.login, indice: m.indice })))))];
    const analisar = confirmarClique('Confirmo: gravação autorizada', tentar(async () => {
      await api('/api/armazenamento/analisar', { nome: gv.nome, autorizado: true }); avisar('Análise começou: os momentos aparecem aqui conforme ela avança.'); await carregar(); desenhar(true);
    }));
    return el('section', { className: 'card bloco pr-grav' + (gv.gravando ? ' gravando' : '') },
      el('div', { className: 'topo-linha', style: 'flex-wrap:wrap' },
        el('div', {}, el('h2', { className: 'pr-nome pequeno' }, gv.gravando ? el('span', { className: 'selo live', textContent: 'REC' }) : null, ` Live de ${quando(gv.comecou)}`,
          gv.plataforma ? el('span', { className: 'selo', style: `--cor:${CORES[gv.plataforma]};margin-left:6px`, textContent: PLATAFORMA[gv.plataforma] }) : null),
          el('small', { className: 'pr-sub', textContent: [`${tempoVivo(gv.minutos * 60)} gravados`, mbTxt(gv.mb), estadoAn, a ? `${sug.length} momentos achados` : '', `${cortes.length} cortes feitos`, gv.auto ? `clipa sozinho ≥ ${gv.auto}` : '', gv.nome].filter(Boolean).join(' · ') })),
        el('span', { className: 'ferramentas', style: 'margin:0' },
          gv.gravando ? btn('Clipar 30 s', clipar(gv.login, 30), 'btn mini') : null,
          gv.no_painel ? btn('Assistir e momentos', () => abrirEstudio(gv.login)) : null,
          !a && !gv.gravando ? btn('Achar os melhores momentos', analisar, 'btn mini', { title: 'Analisa voz, gritos, risadas e mudanças de cena da gravação inteira' }) : null,
          gv.gravando ? btn('Parar gravação', pararGravacao(gv.login), 'btn leve mini perigo') : null,
          !gv.gravando ? btn(`Apagar gravação (${mbTxt(gv.mb)})`, confirmarClique('Confirmar: apagar o vídeo bruto', tentar(async () => {
            await api('/api/armazenamento/excluir', { nome: gv.nome }); avisar('Gravação apagada. Os cortes feitos dela continuam.'); await carregar(); desenhar(true);
          })), 'btn leve mini perigo', { title: 'Apaga só o vídeo bruto da live. Os cortes têm cópia própria e continuam.' }) : null)),
      momentos.length ? el('div', { className: 'pr-sub-secao' }, el('h3', { className: 'tit', textContent: `Momentos achados que ainda não viraram corte (${livres.length + chatMom.length})` }), el('div', { className: 'at-secao' }, ...momentos)) : null,
      cortes.length ? el('div', { className: 'pr-sub-secao' }, el('h3', { className: 'tit', textContent: `Cortes desta gravação (${cortes.length})` }), ...ordenar(cortes).map(linhaCorte)) : null,
      !momentos.length && !cortes.length ? el('p', { className: 'dica', textContent: a ? 'Nenhum momento acima do normal nesta gravação.' : 'Esta gravação ainda não foi analisada.' }) : null);
  }

  /* ---------------------------------------------------------------- resumo da live e compilado */
  function estadoResumo(g) {
    return P.resumo[g.chave] || (P.resumo[g.chave] = { plat: g.plataformas.includes('kick') && !g.plataformas.includes('twitch') ? 'kick' : (g.plataformas[0] || 'twitch'),
      lives: null, erro: '', live: null, dados: null, erroResumo: '', sel: new Set(), bloco: null, carregando: false, ordem: 'cronologica', limite: 25 });
  }
  function abaLive(g) {
    const R = estadoResumo(g), caixa = el('div', { id: 'pr-live' });
    pintarLive(g, R, caixa);
    if (!R.lives && !R.carregando && !R.erro) buscarLives(g, R, caixa);
    return [caixa, secaoCompilados(g)];
  }
  async function buscarLives(g, R, caixa, forcar) {
    R.carregando = true; R.erro = ''; pintarLive(g, R, caixa);
    try {
      const r = await api(`/api/producao/lives?plataforma=${R.plat}&canal=${encodeURIComponent(g.chave)}${forcar ? '&forcar=1' : ''}`);
      R.lives = r.lives;
      if (!R.live) { const l = R.lives.find(x => !x.ao_vivo) || R.lives[0]; if (l) { R.carregando = false; escolherLive(g, R, caixa, l); return; } }
    } catch (e) { R.erro = e.message; }
    R.carregando = false; pintarLive(g, R, caixa);
  }
  async function escolherLive(g, R, caixa, l, forcar) {
    R.live = l; R.dados = null; R.erroResumo = ''; R.bloco = null; R.carregando = true; pintarLive(g, R, caixa);
    try {
      R.dados = await api(`/api/producao/resumo?plataforma=${R.plat}&canal=${encodeURIComponent(g.chave)}&inicio=${l.inicio}&fim=${l.fim}${forcar ? '&forcar=1' : ''}`);
      R.sel = new Set(R.dados.clips.slice(0, 10).map(c => c.id));
    } catch (e) { R.erroResumo = e.message; }
    R.carregando = false;
    if ($('#pr-live') === caixa || document.body.contains(caixa)) pintarLive(g, R, caixa);
  }
  function pintarLive(g, R, caixa) {
    const partes = [];
    const trocaPlat = g.plataformas.length > 1 ? el('span', { className: 'ferramentas', style: 'margin:0' }, ...g.plataformas.map(p => el('button', { className: 'chip', type: 'button', textContent: PLATAFORMA[p], ariaPressed: String(p === R.plat),
      onclick: () => { R.plat = p; R.lives = null; R.live = null; R.dados = null; buscarLives(g, R, caixa); } }))) : null;
    partes.push(el('div', { className: 'topo-linha', style: 'flex-wrap:wrap;margin-bottom:10px' }, el('h2', { className: 'tit', style: 'margin:0', textContent: `Últimas lives de ${g.chave} (${PLATAFORMA[R.plat]})` }),
      el('span', { className: 'ferramentas', style: 'margin:0' }, trocaPlat, btn('Atualizar lista', () => { R.live = null; buscarLives(g, R, caixa, true); }))));
    if (R.erro) partes.push(el('p', { className: 'dica erro', textContent: R.erro }));
    else if (!R.lives) partes.push(el('p', { className: 'dica', textContent: 'Buscando as últimas lives...' }));
    else if (!R.lives.length) partes.push(el('p', { className: 'dica', textContent: 'Nenhuma live recente encontrada.' }));
    else partes.push(el('div', { className: 'pr-lives' }, ...R.lives.slice(0, 6).map(l => el('button', { className: 'pr-live' + (R.live && R.live.id === l.id ? ' ativo' : ''), type: 'button', onclick: () => escolherLive(g, R, caixa, l) },
      l.thumb ? el('img', { src: l.thumb, alt: '', loading: 'lazy' }) : el('span', { className: 'pr-live-sem' }),
      el('b', { textContent: l.titulo || 'Live', title: l.titulo }),
      el('small', { textContent: [quando(l.inicio), l.ao_vivo ? 'AO VIVO agora' : `${tempoVivo(l.duracao)} de live`, l.views ? `${fmtNum(l.views)} views` : '', l.pico ? `pico de ${fmtNum(l.pico)} assistindo` : ''].filter(Boolean).join(' · ') })))));
    if (R.live) partes.push(R.carregando ? el('p', { className: 'dica', textContent: `Juntando os clipes da live inteira (${tempoVivo(R.live.duracao || (R.live.fim - R.live.inicio))})... pode levar uns 20 segundos na Kick.` })
      : R.erroResumo ? el('p', { className: 'dica erro', textContent: R.erroResumo }) : R.dados ? resumo(g, R, caixa) : null);
    caixa.replaceChildren(el('section', { className: 'card bloco' }, ...partes.filter(Boolean)));
  }
  function resumo(g, R, caixa) {
    const d = R.dados, l = R.live, dur = d.fim - d.inicio, max = Math.max(1, ...d.blocos.map(b => b.clips));
    const repintar = () => pintarLive(g, R, caixa);
    const faixa = b => `${tempoVivo(b.inicio)}–${tempoVivo(Math.min(b.inicio + 600, dur))}`;
    const grafico = el('div', { className: 'pr-grafico', role: 'img', ariaLabel: `Clipes por bloco de 10 minutos. Picos: ${d.picos.map(i => faixa(d.blocos[i])).join(', ')}` },
      ...d.blocos.map(b => el('button', { type: 'button', className: 'pr-barra' + (d.picos.includes(b.i) ? ' pico' : '') + (R.bloco === b.i ? ' ativo' : ''),
        title: `${faixa(b)} da live · ${b.clips} clipes · ${fmtNum(b.views)} views`, onclick: () => { R.bloco = R.bloco === b.i ? null : b.i; repintar(); } },
        el('i', { style: `height:${Math.max(3, Math.round(b.clips / max * 100))}%` }))));
    const marcas = el('div', { className: 'pr-eixo' }, ...Array.from({ length: Math.floor(dur / 3600) + 1 }, (_, h) => el('span', { style: `left:${Math.min(100, h * 3600 / dur * 100)}%`, textContent: `${h}h` })));
    const nossos = d.nossos.length ? el('div', { className: 'pr-nossos', title: 'Momentos que a análise da sua gravação achou, no tempo da live' },
      ...d.nossos.filter(s => s.momento >= 0 && s.momento <= dur).map(s => el('i', { style: `left:${s.momento / dur * 100}%;opacity:${0.35 + (s.nota || 0) / 160}`, title: `${tempoVivo(s.momento)} · nota ${s.nota}` }))) : null;
    const lista = (R.bloco === null ? d.clips : d.clips.filter(c => Math.min(d.blocos.length - 1, Math.floor(c.momento / 600)) === R.bloco));
    const mostrados = lista.slice(0, R.bloco === null ? R.limite : 100);
    const selecionados = d.clips.filter(c => R.sel.has(c.id));
    const durSel = selecionados.reduce((s, c) => s + (c.duracao || 0), 0);
    const linhaClip = c => {
      const caixaSel = el('input', { type: 'checkbox', checked: R.sel.has(c.id), onchange: e => { if (e.target.checked) R.sel.add(c.id); else R.sel.delete(c.id); repintar(); } });
      return el('div', { className: 'pr-clip' + (R.sel.has(c.id) ? ' marcado' : '') }, el('label', { className: 'pr-check' }, caixaSel),
        el('span', { className: 'pr-pos', textContent: `#${c.posicao}` }),
        el('span', { className: 'pr-views', textContent: `${fmtNum(c.views)}`, title: `${c.views} views` }),
        el('div', { className: 'pr-info' }, el('b', { textContent: c.titulo || '(sem título)', title: c.titulo }),
          el('small', { textContent: [`${tempoVivo(c.momento)} da live`, `${Math.round(c.duracao)} s`, c.autor ? `clipado por ${c.autor}` : '', quando(tsIso(c.criado))].filter(Boolean).join(' · ') })),
        el('div', { className: 'pr-acoes' },
          c.corte ? btn('Já é corte: abrir', () => irPara('editor', { corte: c.corte }), 'btn leve mini pr-mantendo') : null,
          c.url ? el('a', { className: 'btn leve mini', href: c.url, target: '_blank', rel: 'noopener', textContent: 'Ver clipe' }) : null,
          l.link ? btn('Cortar com mais contexto', () => cortarDoVod(l.link, Math.max(0, c.momento - 15), c.momento + c.duracao + 10, c.titulo), 'btn leve mini', { title: 'Abre a gravação da live com o trecho marcado (15 s antes e 10 s depois do clipe)' }) : null));
    };
    const aut = el('input', { type: 'checkbox' });
    const ordem = el('select', { onchange: e => { R.ordem = e.target.value; } }, el('option', { value: 'cronologica', textContent: 'Na ordem da live', selected: R.ordem === 'cronologica' }), el('option', { value: 'views', textContent: 'Do mais visto ao menos visto', selected: R.ordem === 'views' }));
    const pacote = () => selecionados.map(c => ({ id: c.id, plataforma: R.plat, titulo: c.titulo, canal: c.canal_login || g.chave, views: c.views, autor: c.autor, criado: c.criado, url: c.url, duracao: c.duracao, posicao: c.posicao, momento: c.momento }));
    const infoLive = { titulo: l.titulo, inicio: l.inicio, link: l.link };
    const corteNosso = s => g.cortes.find(c => c.origem.gravacao === s.gravacao && ((c.origem.pico !== undefined && c.origem.pico !== null && Math.abs(c.origem.pico - s.pico) < 1) || Math.abs((c.inicio ?? -99) - s.inicio) < 1.5));
    const exigir = () => { if (!selecionados.length) throw new Error('Selecione pelo menos um clipe.'); if (!aut.checked) throw new Error('Marque a autorização para continuar.'); };
    return el('div', { className: 'pr-resumo' },
      el('h3', { className: 'pr-nome pequeno', style: 'margin-top:14px', textContent: l.titulo || 'Live' }),
      el('p', { className: 'pr-sub', textContent: [quando(l.inicio), `${tempoVivo(dur)} de live`, `${d.total} clipes`, `${fmtNum(d.views)} views somadas nos clipes`, l.views ? `${fmtNum(l.views)} views da live` : '', `atualizado ${ha(d.atualizado)}`].filter(Boolean).join(' · ') }),
      el('div', { className: 'pr-grafico-caixa' }, grafico, nossos, marcas),
      el('p', { className: 'dica', style: 'margin:6px 0 0' }, 'Cada barra é um bloco de 10 min: quanto mais alta, mais gente clipou. ', d.picos.length ? 'Picos: ' : '',
        ...d.picos.map(i => btn(`${faixa(d.blocos[i])} (${d.blocos[i].clips} clipes)`, () => { R.bloco = R.bloco === i ? null : i; repintar(); }, 'chip' + (R.bloco === i ? ' ativo' : ''), { ariaPressed: String(R.bloco === i), style: 'margin:2px' })),
        nossos ? ' As marquinhas embaixo são os momentos que a análise da sua gravação achou.' : ''),
      el('div', { className: 'topo-linha', style: 'flex-wrap:wrap;margin:14px 0 8px' },
        el('h3', { className: 'tit', style: 'margin:0', textContent: R.bloco === null ? `Mais vistos da live inteira (${d.total})` : `Clipes de ${faixa(d.blocos[R.bloco])} (${lista.length})` }),
        el('span', { className: 'ferramentas', style: 'margin:0' }, el('span', { className: 'dica', style: 'margin:0', textContent: 'Selecionar:' }),
          ...[5, 10, 20].map(n => btn(`top ${n}`, () => { R.sel = new Set(d.clips.slice(0, n).map(c => c.id)); repintar(); })),
          btn('os que não viraram corte (top 10)', () => { R.sel = new Set(d.clips.filter(c => !c.corte).slice(0, 10).map(c => c.id)); repintar(); }),
          btn('nenhum', () => { R.sel = new Set(); repintar(); }),
          R.bloco !== null ? btn('ver a live inteira', () => { R.bloco = null; repintar(); }) : null,
          btn('Buscar de novo', () => escolherLive(g, R, caixa, l, true)))),
      el('div', { className: 'pr-clips' }, ...(mostrados.length ? mostrados.map(linhaClip) : [el('p', { className: 'dica', textContent: 'Nenhum clipe neste trecho.' })])),
      R.bloco === null && lista.length > R.limite ? btn(`Mostrar mais (${lista.length - R.limite})`, () => { R.limite += 50; repintar(); }, 'btn leve mini', { style: 'margin-top:8px' }) : null,
      el('div', { className: 'card pr-acao-live' },
        el('b', { textContent: `${selecionados.length} clipe(s) selecionado(s) · ${tempoVivo(durSel)} somados` }),
        el('label', { className: 'marcar autoriza' }, aut, 'Tenho autorização para usar estes clipes (canal meu, permissão do criador ou conteúdo liberado para cortes).'),
        el('div', { className: 'ferramentas', style: 'margin:0;align-items:center' },
          btn('Gerar conteúdo (um corte por clipe)', tentar(async () => {
            exigir();
            const r = await api('/api/descobrir/clips/conteudo', { clips: pacote(), modelo: g.tem_layout ? 'streamer' : 'nenhum', autorizado: true, como: 'live', live: infoLive, lista: `da live “${l.titulo}”`, total: d.total });
            avisar(`${r.tarefas.length} clipes na fila: cada um vira um corte${g.tem_layout ? ' e um Reel no layout salvo' : ''}. Acompanhe em Fazendo agora.`);
            G.tarefas = await api('/api/tarefas'); P.aba = 'geral'; desenhar(true);
          }), 'btn mini', { title: 'Cada clipe vira um corte separado (e um Reel, se o streamer tiver layout salvo)' }),
          el('label', { className: 'pr-ordem' }, 'Compilado ', ordem),
          btn('Montar compilado (um vídeo só)', tentar(async () => {
            exigir();
            if (selecionados.length < 2) throw new Error('Escolha pelo menos 2 clipes para o compilado.');
            await api('/api/producao/compilado', { plataforma: R.plat, canal: g.chave, clips: pacote(), ordem: R.ordem, live: infoLive, autorizado: true });
            avisar('Compilado na fila: os clipes são baixados e juntados em 1920x1080. Acompanhe em Fazendo agora; pronto, ele aparece em Compilados, logo abaixo.');
            G.tarefas = await api('/api/tarefas'); pintarFazendo();
          }), 'btn mini', { title: 'Baixa os clipes selecionados e junta tudo num vídeo 16:9 (1920x1080), com os capítulos prontos para a descrição' }))),
      d.nossos.length ? el('div', { className: 'pr-sub-secao' }, el('h3', { className: 'tit', textContent: `Momentos da sua gravação nesta live (${d.nossos.length})` }),
        el('div', { className: 'at-secao' }, ...d.nossos.slice(0, 10).map(s => el('div', { className: 'at-item at-momento' }, el('span', { className: 'dc-nota', textContent: s.nota }),
          el('div', { className: 'at-info' }, el('b', { textContent: `${tempoVivo(s.momento)} da live · ${s.gravacao}` }), el('small', { textContent: (s.motivos || []).join(' · ') + (s.fala ? ` · “${s.fala}”` : '') })),
          el('div', { className: 'at-acoes' }, corteNosso(s) ? btn('Já é corte: abrir', () => irPara('editor', { corte: corteNosso(s).id }), 'btn leve mini pr-mantendo')
            : btn('Criar corte', tentar(async () => { await api('/api/producao/corte-momento', { fonte: s.fonte, indice: s.indice, streamer: g.chave }); avisar('Corte na fila.'); G.tarefas = await api('/api/tarefas'); pintarFazendo(); }))))))) : null);
  }
  async function cortarDoVod(link, a, b, titulo) {
    irPara('gerar', { modo: 'manual' });
    try {
      await abrirFonte({ url: link });
      $('#es-ini').value = hms(a); $('#es-fim').value = hms(b); atualizarSel();
      if ($('#es-tit') && !$('#es-tit').value) $('#es-tit').value = titulo || '';
      for (let i = 0; i < 40 && !E.player; i++) await new Promise(r => setTimeout(r, 250));
      if (E.player) E.player.ir(a);
      avisar('Trecho do clipe marcado na gravação da live (com 15 s antes). Ajuste se quiser e clique em Criar corte.');
    } catch (e) { avisar(e.message, true); }
  }
  function secaoCompilados(g) {
    const cartao = cp => el('div', { className: 'pr-corte' },
      el('span', {}),
      el('button', { className: 'pr-capa', type: 'button', onclick: () => verVideo(cp.url, cp.titulo) }, el('img', { src: cp.thumb, alt: '', loading: 'lazy' }), el('span', { className: 'tempo', textContent: tempoVivo(cp.duracao) })),
      el('div', { className: 'pr-info' }, el('div', { className: 'pr-tit' }, el('b', { textContent: cp.titulo || cp.nome })),
        el('div', { className: 'pr-chips' }, el('span', { className: 'pr-chip clipe', textContent: `${(cp.clipes || []).length} clipes` }), el('span', { className: 'pr-chip', textContent: cp.ordem === 'views' ? 'do mais visto ao menos visto' : 'na ordem da live' }),
          el('span', { className: 'pr-chip', textContent: `${fmtNum((cp.clipes || []).reduce((s, c) => s + (c.views || 0), 0))} views somadas` })),
        el('p', { className: 'pr-porque', textContent: (cp.clipes || []).slice(0, 4).map(c => `${tempoVivo(c.no_video)} ${c.titulo}`).join(' · ') + ((cp.clipes || []).length > 4 ? ' ...' : '') }),
        el('small', { className: 'pr-meta', textContent: [`criado ${ha(cp.criado)}`, mbTxt(cp.mb), (cp.falhas || []).length ? `${cp.falhas.length} clipe(s) não baixaram` : ''].filter(Boolean).join(' · ') })),
      el('div', { className: 'pr-acoes' }, btn('Assistir', () => verVideo(cp.url, cp.titulo), 'btn mini'),
        btn('Copiar capítulos', tentar(async () => { await navigator.clipboard.writeText(cp.capitulos || ''); avisar('Capítulos copiados: cole na descrição do YouTube.'); }), 'btn leve mini', { title: cp.capitulos || '' }),
        el('a', { className: 'btn leve mini', href: cp.url, download: `${cp.nome}.mp4`, textContent: 'Baixar' }),
        btn('Pasta', tentar(() => api('/api/abrir-pasta', { pasta: cp.pasta }))),
        btn('Excluir', confirmarClique('Confirmar', tentar(async () => { await api('/api/producao/compilado/excluir', { nome: cp.nome }); avisar('Compilado na lixeira do Vice Clips.'); await carregar(); desenhar(true); })), 'btn leve mini perigo')));
    return el('section', { className: 'card bloco pr-secao' }, el('h2', { className: 'tit', textContent: `Compilados (${g.compilados.length})` }),
      ...(g.compilados.length ? g.compilados.map(cartao) : [el('p', { className: 'dica', style: 'margin:0', textContent: 'Nenhum compilado ainda. Escolha a live acima, selecione os clipes e clique em Montar compilado.' })]));
  }

  window.Producao = { mostrar, sair, tick, ir: (chave, aba) => { P.chave = chave; P.aba = aba || 'geral'; irPara('producao'); } };
})();
