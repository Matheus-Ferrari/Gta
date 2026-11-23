/* Timeline de saída (trechos, efeitos, títulos, áudio), abas Efeitos / Áudio / Check-up e o áudio da prévia. */
window.VCUI = (() => {
const X = () => window.VCEditor, Fx = window.VCFx;
const { lim, r2, novoId, TIPOS } = Fx;
const U = { sons: null, bufs: {}, tocando: null, areas: null, checkup: null, choque: { tela: 0.7, modo: 'corte', dur: 3, dessat: 0.25, freeze: true, freezeDur: 0.5, musica: 0.15, sfx: 'impacto/impacto_grave.wav', trilha: 'suspense/suspense_grave.wav', retorno: 0.5, vinheta: true } };
const S = () => X().S, P = () => X().S.p;
const agora = () => { const t = X().tempoSaida(); return t ? t.T : 0; };
const botao = (t, f, titulo, classe = 'btn leve mini') => el('button', { className: classe, type: 'button', textContent: t, title: titulo || t, onclick: f });
const sec = t => el('div', { className: 'sec todo', textContent: t });
const dica = t => el('p', { className: 'dica todo', style: 'margin:0', textContent: t });
const refazer = (livre = false) => { X().mudou(livre); X().pintarPainel(); };

/* ---------- trechos ---------- */
function novoTrecho() {
  const p = P(), v = S().video, dur = S().d.fonte.dur, ini = r2(lim(v.currentTime, 0, dur - 1));
  X().segs();
  const g = { id: novoId('s'), ini, fim: r2(Math.min(dur, ini + 5)), vel: 1, trans: 'corte', transDur: 0.3, rotulo: '' };
  p.segmentos.push(g); X().selSeg(g.id); S().fx = { tipo: 'seg', id: g.id }; S().aba = 'efeitos';
  avisar('Trecho novo criado no ponto atual. Ajuste o início e o fim com as alças rosa.'); refazer();
}
function dividir() {
  const pos = X().tempoSaida(), lista = X().segs();
  if (!pos) { avisar('Coloque a agulha dentro de um trecho para dividir.', true); return null; }
  const g = lista[pos.i], t = r2(S().video.currentTime);
  if (t - g.ini < 0.3 || g.fim - t < 0.3) { avisar('O ponto de divisão está muito perto da borda do trecho.', true); return null; }
  const n = { ...g, id: novoId('s'), ini: t, trans: 'corte' };
  X().selSeg(g.id); P().fim = t; X().segs();
  lista.splice(pos.i + 1, 0, n); X().selSeg(n.id); S().tocando = pos.i + 1; refazer();
  return n;
}
/* Câmera lenta = trecho com velocidade menor: divide em volta do ponto atual. */
function cameraLenta(dur = 1.5, vel = 0.5) {
  const v = S().video, t0 = v.currentTime;
  if (!dividir()) return;
  const g = X().segSel();
  if (g.fim - g.ini > dur + 0.3) { v.currentTime = t0 + dur; S().tocando = P().segmentos.indexOf(g); const resto = dividir(); if (resto) X().selSeg(g.id); }
  g.vel = vel; v.currentTime = t0; S().tocando = P().segmentos.indexOf(g); S().fx = { tipo: 'seg', id: g.id };
  avisar(`Câmera lenta (${vel}x) aplicada em ${((g.fim - g.ini)).toFixed(1)} s. A voz fica mais lenta sem mudar o tom.`); refazer();
}
function propsTrecho(g) {
  const p = P(), i = p.segmentos.indexOf(g), m = Fx.mapa(X().segs());
  const mover = d => () => { const j = i + d; if (j < 0 || j >= p.segmentos.length) return; [p.segmentos[i], p.segmentos[j]] = [p.segmentos[j], p.segmentos[i]]; refazer(); };
  return el('div', { className: 'grupo' }, sec(`Trecho ${i + 1} de ${p.segmentos.length} · entra em ${X().fmt(m.ini[i])} · dura ${((g.fim - g.ini) / g.vel).toFixed(1)} s`),
    X().campoSel('Velocidade', { get v() { return String(g.vel); }, set v(x) { g.vel = Number(x); } }, 'v', [['0.25', '0,25x (bem lento)'], ['0.5', '0,5x (câmera lenta)'], ['0.75', '0,75x'], ['1', 'Normal'], ['1.5', '1,5x'], ['2', '2x']]),
    i ? X().campoSel('Entrada do trecho', g, 'trans', [['corte', 'Corte seco'], ['fade', 'Fade pelo preto'], ['flash', 'Flash branco']]) : dica('O primeiro trecho abre o vídeo.'),
    i && g.trans !== 'corte' ? X().campoNum('Duração da transição (s)', g, 'transDur', { min: 0.06, max: 2, passo: 0.05 }) : null,
    el('label', { className: 'todo' }, 'Rótulo (aparece na timeline)', el('input', { value: g.rotulo || '', maxLength: 40, onchange: e => { g.rotulo = e.target.value; X().mudou(false); } })),
    el('div', { className: 'ferramentas todo', style: 'margin:0' }, botao('← Antes', mover(-1)), botao('Depois →', mover(1)),
      botao('Ir para o trecho', () => X().irSaida(m.ini[i] + 0.01)),
      p.segmentos.length > 1 ? botao('Remover trecho', () => { p.segmentos.splice(i, 1); X().selSeg(p.segmentos[Math.max(0, i - 1)].id); S().fx = null; S().tocando = 0; refazer(); }, 'Remove só este trecho; a gravação não é apagada', 'btn leve mini perigo') : null));
}

/* ---------- efeitos ---------- */
function alvoCam(T, cheia) {
  const p = P(), W = X().W, H = X().H, cam = p.regioes.webcam, v = S().video;
  if (cheia) { const e = p.efeitos.find(x => x.tipo === 'cam_cheia' && x.ini <= T + 0.05 && x.fim > T); return { cx: W / 2, cy: Math.round((typeof cheia === 'number' ? cheia : e ? e.forca : 1) * H * 0.45) }; }
  if (!cam) return { cx: W / 2, cy: H / 2 };
  const f = p.regioes.rosto, alvo = f ? { x: f.x + f.w / 2, y: f.y + f.h / 2 } : { x: cam.x + cam.w / 2, y: cam.y + cam.h / 2 };
  const camadas = p.camadas.filter(c => c.tipo === 'video' && c.visivel).sort((a, b) => (b.regiao === 'webcam') - (a.regiao === 'webcam'));
  if (v.videoWidth) for (const c of camadas) {  // projeta o rosto na saída, pela camada que o mostra (a de webcam primeiro)
    const r = X().regiaoDe(c); if (!r) continue;
    const [x, y, l, a] = X().efetivo(r, c.caixa, c.zoom, c.panX, c.panY, v.videoWidth, v.videoHeight);
    const wx = alvo.x * v.videoWidth, wy = alvo.y * v.videoHeight;
    if (wx >= x && wx <= x + l && wy >= y && wy <= y + a) return { cx: Math.round(c.caixa.x + (wx - x) / l * c.caixa.w), cy: Math.round(c.caixa.y + (wy - y) / a * c.caixa.h) };
  }
  return { cx: W / 2, cy: H / 2 };
}
function novoEfeito(tipo, ini, extra = {}) {
  const t = TIPOS[tipo], dur = X().durSaida();
  ini = r2(lim(ini, 0, Math.max(0, dur - 0.1)));
  const cheia = P().efeitos.some(e => e.tipo === 'cam_cheia' && e.ini <= ini + 0.05 && e.fim > ini) || extra.cheia;
  const e = { id: novoId('e'), tipo, ini, fim: r2(Math.min(dur, ini + t.dur)), forca: 1, entrada: 0, saida: 0, ativo: true, grupo: '', ...alvoCam(ini, cheia), ...t.pad, ...extra };
  delete e.cheia;
  if (tipo === 'zoom') e.entrada = r2(e.fim - e.ini);
  P().efeitos.push(e);
  return e;
}
/* Procura o rosto uma vez por projeto; sem rosto, o recorte fica no centro da webcam. */
async function garantirRosto() {
  const p = P();
  if (!p.regioes.webcam || p.regioes.rosto || S().semRosto === S().id) return;
  try {
    const r = await api('/api/editor/detectar-rosto', { corte: S().id, regiao: p.regioes.webcam });
    if (r.rosto) p.regioes.rosto = r.rosto; else { S().semRosto = S().id; avisar('Não achei o rosto na webcam: o recorte fica no centro dela. Ajuste o retângulo rosa se cortar a pessoa.'); }
  } catch { /* segue com o centro da webcam */ }
}
async function adicionar(tipo) {
  if ((tipo === 'cam_cheia' || tipo === 'zoom_cam') && !P().regioes.webcam) { X().msgFonte('Marque a webcam na fonte original (retângulo rosa) para usar este efeito.'); avisar('Nenhuma webcam marcada neste vídeo.', true); return; }
  if (tipo === 'cam_cheia' || tipo === 'zoom_cam') await garantirRosto();
  const e = novoEfeito(tipo, agora()); S().fx = { tipo: 'efeito', id: e.id }; refazer();
}
function removerGrupo(grupo) {
  const p = P();
  p.efeitos = p.efeitos.filter(e => e.grupo !== grupo); p.audio.clipes = p.audio.clipes.filter(c => c.grupo !== grupo);
  p.audio.musica.chaves = p.audio.musica.chaves.filter(k => k.grupo !== grupo); S().fx = null; refazer();
}
function clipe(trilha, arquivo, ini, extra = {}) {
  const s = (U.sons?.sons || []).find(x => x.arquivo === arquivo);
  if (!s) return null;
  const c = { id: novoId('a'), trilha, arquivo, nome: s.nome, ini: r2(Math.max(0, ini)), dur: r2(s.dur), desde: 0, volume: 1, fadeIn: 0, fadeOut: 0, grupo: '', ...extra };
  P().audio.clipes.push(c); som.carregar();
  return c;
}
/* Preset Choque / momento dramático: tudo vira item normal das trilhas, editável um a um. */
async function aplicarChoque(T, D) {
  const o = U.choque, p = P(), g = novoId('g'), dur = X().durSaida();
  if (!p.regioes.webcam) { X().msgFonte('O Choque usa a webcam marcada na fonte original. Marque o retângulo rosa.'); avisar('Marque a webcam antes de aplicar o Choque.', true); return; }
  await garantirRosto();
  T = r2(lim(T, 0, dur - 0.5)); D = r2(lim(D, 0.6, dur - T));
  const base = { grupo: g, fim: r2(T + D) };
  if (o.modo === 'corte') { novoEfeito('cam_cheia', T, { ...base, forca: o.tela }); novoEfeito('zoom', T, { ...base, forca: 1.12, entrada: D, cheia: o.tela }); }
  else novoEfeito('zoom_cam', T, { ...base, entrada: Math.min(0.35, D / 2), saida: Math.min(o.retorno, D / 2) });
  novoEfeito('pb', T, { ...base, entrada: Math.min(o.dessat, D / 2), saida: Math.min(o.retorno, D / 2) });
  if (o.vinheta) novoEfeito('vinheta', T, { ...base, forca: 0.75, entrada: Math.min(o.dessat, D / 2), saida: Math.min(o.retorno, D / 2) });
  if (o.freeze) novoEfeito('freeze', r2(T + 0.04), { grupo: g, fim: r2(Math.min(T + 0.04 + o.freezeDur, T + D)) });
  if (p.audio.clipes.some(c => c.trilha === 'musica') && o.musica < 1) {  // baixa (ou corta) a música que vinha tocando
    const ch = p.audio.musica.chaves, v0 = Fx.interp(ch, T);
    ch.push({ t: r2(Math.max(0, T - 0.05)), v: v0, grupo: g }, { t: r2(T + 0.1), v: o.musica, grupo: g }, { t: r2(T + D), v: o.musica, grupo: g }, { t: r2(T + D + o.retorno), v: v0, grupo: g });
    ch.sort((a, b) => a.t - b.t);
  }
  if (o.sfx) clipe('sfx', o.sfx, T, { grupo: g });
  if (o.trilha) clipe('sfx', o.trilha, T + 0.1, { grupo: g, dur: r2(Math.max(0.5, D - 0.1)), fadeIn: 0.4, fadeOut: Math.min(o.retorno + 0.2, D / 2), volume: 0.8 });
  S().fx = { tipo: 'efeito', id: p.efeitos.find(e => e.grupo === g).id }; S().aba = 'efeitos';
  avisar('Choque aplicado. Cada parte aparece na timeline e pode ser ajustada ou removida.'); refazer();
}
function propsEfeito(e) {
  const t = TIPOS[e.tipo], dur = X().durSaida();
  const itens = [sec(t.nome), dica(t.dica),
    X().campoNum('Início (s)', e, 'ini', { min: 0, max: dur, passo: 0.05 }), X().campoNum('Fim (s)', e, 'fim', { min: 0.05, max: dur, passo: 0.05 })];
  if (X().Fx.NOME_FORCA[e.tipo]) itens.push(X().campoNum(X().Fx.NOME_FORCA[e.tipo], e, 'forca', e.tipo.startsWith('zoom') ? { min: 1, max: 4, passo: 0.05 } : { min: e.tipo === 'cam_cheia' ? 0.3 : 0, max: 1, passo: 0.05 }));
  if (!['cam_cheia', 'freeze'].includes(e.tipo)) itens.push(X().campoNum('Entrada (s)', e, 'entrada', { min: 0, max: 30, passo: 0.05 }), X().campoNum('Saída (s)', e, 'saida', { min: 0, max: 30, passo: 0.05 }));
  if (e.tipo.startsWith('zoom')) itens.push(X().campoNum('Alvo X', e, 'cx', { min: 0, max: X().W }), X().campoNum('Alvo Y', e, 'cy', { min: 0, max: X().H }),
    el('div', { className: 'ferramentas todo', style: 'margin:0' }, botao('Mirar na webcam', () => { Object.assign(e, alvoCam(e.ini, P().efeitos.some(x => x.tipo === 'cam_cheia' && x.ini <= e.ini + 0.05 && x.fim > e.ini))); refazer(); }), botao('Mirar no centro', () => { e.cx = X().W / 2; e.cy = X().H / 2; refazer(); })));
  if (e.tipo === 'freeze') itens.push(dica('Com o vídeo pausado, a prévia do freeze mostra o quadro atual; reproduzindo, mostra o quadro congelado como no export.'));
  itens.push(X().campoCheck('Efeito ligado', e, 'ativo'),
    el('div', { className: 'ferramentas todo', style: 'margin:0' }, botao('Ver', () => X().irSaida(Math.max(0, e.ini - 0.5))),
      botao('Remover', () => { P().efeitos = P().efeitos.filter(x => x !== e); S().fx = null; refazer(); }, 'Remover este efeito', 'btn leve mini perigo'),
      e.grupo ? botao('Remover o conjunto', () => removerGrupo(e.grupo), 'Remove todos os itens criados juntos (preset)', 'btn leve mini perigo') : null));
  return el('div', { className: 'grupo' }, ...itens.filter(Boolean));
}
function abaEfeitos() {
  const p = P(); S()._livre = false;
  const fx = S().fx, seg = fx?.tipo === 'seg' ? p.segmentos.find(g => g.id === fx.id) : null, ef = fx?.tipo === 'efeito' ? p.efeitos.find(e => e.id === fx.id) : null;
  const o = U.choque, sons = U.sons?.sons || [];
  const opSom = cat => [['', 'Nenhum'], ...sons.filter(s => cat.includes(s.categoria)).map(s => [s.arquivo, s.nome])];
  const T = agora(), pos = X().tempoSaida();
  return [
    propsTrecho(seg || X().segSel()),
    sec('Adicionar no ponto atual'),
    el('div', { className: 'ferramentas', style: 'margin:0' }, ...Object.entries(TIPOS).map(([id, t]) => botao(`+ ${t.nome}`, () => adicionar(id), t.dica)),
      botao('+ Corte seco para a webcam', () => adicionar('cam_cheia'), 'Troca na hora para a webcam em tela cheia'),
      botao('+ Câmera lenta', () => cameraLenta(), 'Divide o trecho e deixa 1,5 s em 0,5x')),
    ef ? propsEfeito(ef) : dica('Clique em um efeito na timeline para ajustar início, fim e intensidade.'),
    sec('Preset: Choque / momento dramático'),
    el('div', { className: 'grupo' },
      X().campoSel('Entrada', o, 'modo', [['corte', 'Corte seco para a webcam'], ['zoom', 'Zoom na reação']]),
      X().campoNum('Duração (s)', o, 'dur', { min: 0.6, max: 30, passo: 0.1 }),
      X().campoNum('Webcam ocupa (0,3 a 1 da tela)', o, 'tela', { min: 0.3, max: 1, passo: 0.05 }),
      X().campoNum('Tirar a cor em (s)', o, 'dessat', { min: 0.05, max: 2, passo: 0.05 }), X().campoNum('Voltar em (s)', o, 'retorno', { min: 0, max: 3, passo: 0.05 }),
      X().campoCheck('Congelar um quadro da reação', o, 'freeze'), X().campoNum('Freeze (s)', o, 'freezeDur', { min: 0.1, max: 2, passo: 0.05 }),
      X().campoNum('Música anterior cai para', o, 'musica', { min: 0, max: 1, passo: 0.05 }), X().campoCheck('Vinheta escura', o, 'vinheta'),
      X().campoSel('Som de impacto', o, 'sfx', opSom(['impacto', 'reacao'])), X().campoSel('Trilha de suspense / pânico', o, 'trilha', opSom(['suspense', 'panico'])),
      el('div', { className: 'ferramentas todo', style: 'margin:0' },
        botao(`Aplicar em ${X().fmt(T)}`, () => aplicarChoque(agora(), o.dur), 'Aplica no ponto atual da agulha', 'btn mini'),
        botao('Aplicar no trecho inteiro', () => { const m = Fx.mapa(X().segs()), i = pos ? pos.i : 0, g = p.segmentos[i]; aplicarChoque(m.ini[i], (g.fim - g.ini) / g.vel); })),
      dica('O preset não é aplicado sozinho: você escolhe o momento (ou aceita uma sugestão do Check-up).')),
    sec(`Efeitos do projeto (${p.efeitos.length})`),
    el('div', { className: 'lista', style: 'gap:4px' }, ...[...p.efeitos].sort((a, b) => a.ini - b.ini).map(e => el('div', { className: 'camada', ariaSelected: String(ef === e), onclick: () => { S().fx = { tipo: 'efeito', id: e.id }; X().pintarPainel(); trilhas(); } },
      el('span', { className: 'tipo-camada', textContent: X().fmt(e.ini) }), el('span', { className: 'nome', textContent: TIPOS[e.tipo].nome + (e.ativo === false ? ' (desligado)' : '') }),
      el('span', { className: 'tipo-camada', textContent: `${(e.fim - e.ini).toFixed(1)} s` })))),
  ];
}

/* ---------- áudio ---------- */
const NOME_TRILHA = { original: 'Áudio original (jogo + voz)', musica: 'Música de fundo', sfx: 'Efeitos sonoros' };
const PRESETS_SOM = {
  suspense: ['Suspense', T => { clipe('sfx', 'suspense/suspense_grave.wav', T, { dur: 8, fadeIn: 1, fadeOut: 1.5, volume: 0.75 }); novoEfeito('vinheta', T, { fim: r2(T + 8), entrada: 1, saida: 1.5 }); }],
  panico: ['Pânico', T => { clipe('sfx', 'panico/panico_pulsante.wav', T, { dur: 6, fadeIn: 0.3, fadeOut: 1, volume: 0.75 }); novoEfeito('tremor', T, { fim: r2(T + 1), saida: 0.6 }); }],
  impacto: ['Impacto', T => { clipe('sfx', 'impacto/impacto_grave.wav', T); novoEfeito('flash', T); novoEfeito('tremor', T, { fim: r2(T + 0.5) }); }],
  comedia: ['Comédia', T => { clipe('sfx', 'comedia/boing.wav', T); if (P().regioes.webcam) novoEfeito('zoom_cam', T, { fim: r2(T + 1.2), forca: 1.5, entrada: 0.12, saida: 0.2 }); }],
  falha: ['Falha engraçada', T => { clipe('sfx', 'falha/trombone_triste.wav', T); novoEfeito('freeze', T, { fim: r2(T + 0.7) }); novoEfeito('pb', T, { fim: r2(T + 2), entrada: 0.1, saida: 0.4 }); }],
  revelacao: ['Revelação', T => { clipe('sfx', 'revelacao/subida.wav', T - 1.8); clipe('sfx', 'revelacao/brilho.wav', T); novoEfeito('flash', T, { saida: 0.5 }); }],
  reacao: ['Reação inesperada', T => { clipe('sfx', 'reacao/risco_de_disco.wav', T); if (P().regioes.webcam) { novoEfeito('cam_cheia', T, { fim: r2(T + 2) }); novoEfeito('zoom', T, { fim: r2(T + 2), forca: 1.2, entrada: 2, cheia: true }); } }],
};
function aplicarPresetSom(id) {
  const g = novoId('g'), p = P(), ne = p.efeitos.length, nc = p.audio.clipes.length;
  PRESETS_SOM[id][1](agora());
  p.efeitos.slice(ne).forEach(e => { e.grupo = g; }); p.audio.clipes.slice(nc).forEach(c => { c.grupo = g; });
  avisar(`Preset ${PRESETS_SOM[id][0]} aplicado no ponto atual.`); refazer();
}
function propsTrilha(nome) {
  const t = P().audio[nome];
  const ponto = () => { t.chaves.push({ t: r2(agora()), v: 1 }); t.chaves.sort((a, b) => a.t - b.t); refazer(); };
  return el('div', { className: 'grupo' }, sec(NOME_TRILHA[nome]),
    X().campoFaixa(`Volume (${Math.round(t.volume * 100)}%)`, t, 'volume', 0, 2, 0.05, () => som.ganhos()), X().campoCheck('Mudo', t, 'mudo', () => som.ganhos()),
    X().campoNum('Fade-in (s)', t, 'fadeIn', { min: 0, max: 30, passo: 0.1 }), X().campoNum('Fade-out (s)', t, 'fadeOut', { min: 0, max: 30, passo: 0.1 }),
    nome === 'sfx' ? null : el('div', { className: 'todo' },
      el('div', { className: 'ferramentas', style: 'margin:0 0 4px' }, botao('+ Ponto de volume aqui', ponto, 'Keyframe: o volume muda em linha reta de um ponto ao outro')),
      ...t.chaves.map(q => el('div', { className: 'bloco-leg', style: 'grid-template-columns:1fr 1fr auto' },
        el('input', { type: 'number', step: 0.05, min: 0, value: q.t, title: 'Tempo (s)', onchange: e => { q.t = r2(Math.max(0, parseFloat(e.target.value) || 0)); t.chaves.sort((a, b) => a.t - b.t); refazer(); } }),
        el('input', { type: 'number', step: 0.05, min: 0, max: 3, value: q.v, title: 'Volume (1 = normal)', onchange: e => { q.v = lim(parseFloat(e.target.value) || 0, 0, 3); refazer(); } }),
        botao('×', () => { t.chaves.splice(t.chaves.indexOf(q), 1); refazer(); }, 'Remover ponto', 'ico')))));
}
function propsClipe(c) {
  const dur = X().durSaida(), s = (U.sons?.sons || []).find(x => x.arquivo === c.arquivo);
  const anterior = P().audio.clipes.filter(o => o !== c && o.trilha === 'musica' && c.trilha === 'musica' && o.ini < c.ini && o.ini + o.dur > c.ini).sort((a, b) => b.ini - a.ini)[0];
  return el('div', { className: 'grupo' }, sec(`${c.trilha === 'musica' ? 'Música' : 'Som'} · ${c.nome || c.arquivo}`),
    X().campoNum('Entra em (s)', c, 'ini', { min: 0, max: dur, passo: 0.05 }), X().campoNum('Duração (s)', c, 'dur', { min: 0.05, max: 3600, passo: 0.1 }),
    X().campoNum('A partir de (s do arquivo)', c, 'desde', { min: 0, max: 36000, passo: 0.1 }), X().campoNum('Volume', c, 'volume', { min: 0, max: 3, passo: 0.05 }),
    X().campoNum('Fade-in (s)', c, 'fadeIn', { min: 0, max: 30, passo: 0.1 }), X().campoNum('Fade-out (s)', c, 'fadeOut', { min: 0, max: 30, passo: 0.1 }),
    X().campoSel('Trilha', c, 'trilha', [['musica', 'Música (sofre ducking)'], ['sfx', 'Efeitos sonoros']]),
    s && c.trilha === 'musica' && c.dur > s.dur ? dica('Mais longa que o arquivo: a música repete.') : null,
    el('div', { className: 'ferramentas todo', style: 'margin:0' },
      botao('Até o fim do vídeo', () => { c.dur = r2(Math.max(0.1, dur - c.ini)); refazer(); }),
      anterior ? botao('Cruzar com a música anterior', () => { const d = r2(anterior.ini + anterior.dur - c.ini); anterior.fadeOut = d; c.fadeIn = d; refazer(); }, 'Transição: a anterior some enquanto esta entra') : null,
      botao('Ouvir daqui', () => X().irSaida(Math.max(0, c.ini - 0.3))),
      botao('Remover', () => { P().audio.clipes = P().audio.clipes.filter(x => x !== c); S().fx = null; refazer(); }, 'Remover', 'btn leve mini perigo')));
}
function abaAudio() {
  const p = P(), a = p.audio; S()._livre = false;
  const fx = S().fx, cl = fx?.tipo === 'clipe' ? a.clipes.find(c => c.id === fx.id) : null;
  const falas = Fx.falasNaSaida(p.legenda.blocos.flat(), X().segs());
  if (!U.sons) { api('/api/sons').then(r => { U.sons = r; if (S().aba === 'audio' || S().aba === 'efeitos') X().pintarPainel(); }).catch(() => {}); }
  const cat = U.cat || 'impacto', sons = (U.sons?.sons || []).filter(s => s.categoria === cat);
  const inserir = (s, trilha) => { const c = clipe(trilha, s.arquivo, agora(), trilha === 'musica' ? { dur: r2(Math.max(1, X().durSaida() - agora())), volume: 0.6, fadeIn: 0.5, fadeOut: 1 } : {}); S().fx = { tipo: 'clipe', id: c.id }; refazer(); };
  return [
    cl ? propsClipe(cl) : dica('Clique em uma música ou som na timeline para ajustar.'),
    sec('Presets no ponto atual'),
    el('div', { className: 'ferramentas', style: 'margin:0' }, ...Object.entries(PRESETS_SOM).map(([id, [nome]]) => botao(nome, () => aplicarPresetSom(id), `Som + efeito visual do preset ${nome}, no ponto da agulha`))),
    sec('Biblioteca local de sons'),
    el('div', { className: 'ferramentas', style: 'margin:0' }, ...Object.entries(U.sons?.categorias || {}).map(([id, nome]) => el('button', { className: 'chip', type: 'button', ariaPressed: String(id === cat), textContent: nome, onclick: () => { U.cat = id; X().pintarPainel(); } }))),
    el('div', { className: 'lista', style: 'gap:4px' }, ...(sons.length ? sons.map(s => el('div', { className: 'camada' },
      botao('▶', ev => { ev.stopPropagation(); som.ouvir(s.arquivo); }, 'Ouvir', 'ico'),
      el('span', { className: 'nome', title: s.origem, textContent: `${s.nome} · ${s.dur.toFixed(1)} s` }),
      botao('+ Som', () => inserir(s, 'sfx'), 'Coloca no ponto atual, na trilha de efeitos'), botao('+ Música', () => inserir(s, 'musica'), 'Coloca como música de fundo a partir do ponto atual')))
      : [dica(cat === 'musica' ? 'Nenhuma música ainda. Importe arquivos seus ou com licença de uso.' : 'Nenhum som nesta categoria.')])),
    el('div', { className: 'ferramentas', style: 'margin:0' }, botao('Importar arquivo de áudio…', tentar(async () => {
      const r = await api('/api/sons/importar', { categoria: cat }); if (r.cancelado) return; U.sons = r; avisar('Áudio adicionado à biblioteca.'); X().pintarPainel();
    }), 'Copia um arquivo seu para a categoria aberta')),
    dica('Os sons iniciais são originais do Vice Clips. Só importe músicas suas ou com licença: nada é baixado da internet.'),
    propsTrilha('original'),
    dica('Voz e jogo vêm misturados na gravação: não dá para separá-los depois. Para ter trilhas independentes, grave no OBS com faixas de áudio separadas.'),
    propsTrilha('musica'),
    el('div', { className: 'grupo' }, sec('Ducking: a música abaixa durante as falas'),
      X().campoCheck('Ligado', a.ducking, 'ativo'), X().campoNum('Música cai para', a.ducking, 'nivel', { min: 0, max: 1, passo: 0.05 }),
      X().campoNum('Desce em (s)', a.ducking, 'ataque', { min: 0.02, max: 2, passo: 0.02 }), X().campoNum('Volta em (s)', a.ducking, 'soltura', { min: 0.02, max: 3, passo: 0.05 }),
      dica(falas.length ? `Usa os tempos reais da transcrição: ${falas.length} trecho(s) de fala neste corte.` : 'Sem transcrição neste corte: o ducking não tem como saber onde há fala. Transcreva na aba Legendas.')),
    propsTrilha('sfx'),
    dica('Na exportação, um limitador segura os picos em -0,5 dBFS para o áudio não estourar.'),
  ];
}

/* ---------- áudio da prévia (Web Audio) ---------- */
const som = {
  ligar() {
    const s = S();
    if (s.audio || !window.AudioContext || !s.video) return;
    try {
      const ac = new AudioContext(), no = () => ac.createGain(), g = no(), mus = no(), sfx = no(), fim = ac.createDynamicsCompressor();
      Object.assign(fim, {}); fim.threshold.value = -1.5; fim.knee.value = 0; fim.ratio.value = 20; fim.attack.value = 0.003; fim.release.value = 0.06;
      ac.createMediaElementSource(s.video).connect(g).connect(fim); mus.connect(fim); sfx.connect(fim); fim.connect(ac.destination);
      s.audio = { ac, g, mus, sfx, nos: [] };
    } catch { s.audio = null; }
    som.carregar();
  },
  async buffer(arq) {
    if (!U.bufs[arq]) U.bufs[arq] = fetch('/som/' + arq.split('/').map(encodeURIComponent).join('/')).then(r => r.arrayBuffer()).then(b => (S().audio ? S().audio.ac : new AudioContext()).decodeAudioData(b)).catch(() => null);
    return U.bufs[arq];
  },
  carregar() { for (const c of P().audio.clipes) som.buffer(c.arquivo); },
  parametros() { const p = P(); return { dur: X().durSaida(), falas: Fx.falasNaSaida(p.legenda.blocos.flat(), X().segs()) }; },
  /* Vídeo parado: cada trilha fica no ganho do instante atual. */
  ganhos() {
    const A = S().audio, a = P().audio, v = S().video;
    if (!A) { if (v) v.volume = Math.min(1, a.original.mudo ? 0 : a.original.volume); return; }
    A.ac.resume().catch(() => {});
    if (!v.paused) return;
    const T = agora(), { dur, falas } = som.parametros(), agoraAc = A.ac.currentTime;
    for (const [n, no] of [['original', A.g], ['musica', A.mus], ['sfx', A.sfx]]) { no.gain.cancelScheduledValues(agoraAc); no.gain.value = Fx.ganho(a[n], T, dur, n === 'musica' ? falas : null, a.ducking); }
  },
  parar() {
    const A = S().audio; if (!A) return;
    A.nos.forEach(n => { try { n.stop(); } catch { /* já terminou */ } }); A.nos = [];
    [A.g, A.mus, A.sfx].forEach(n => n.gain.cancelScheduledValues(A.ac.currentTime));
    som.ganhos();
  },
  async tocar(T) {
    const A = S().audio; if (!A) return;
    A.nos.forEach(n => { try { n.stop(); } catch { /* já terminou */ } }); A.nos = [];
    const a = P().audio, { dur, falas } = som.parametros(), t0 = A.ac.currentTime + 0.02, resta = dur - T;
    if (resta < 0.05) return;
    const curva = (n, f) => { const c = new Float32Array(Math.max(2, n)); for (let i = 0; i < c.length; i++) c[i] = f(i / 50); return c; };
    for (const [nome, no] of [['original', A.g], ['musica', A.mus], ['sfx', A.sfx]]) {
      no.gain.cancelScheduledValues(0);
      no.gain.setValueCurveAtTime(curva(Math.ceil(resta * 50) + 1, x => Fx.ganho(a[nome], T + x, dur, nome === 'musica' ? falas : null, a.ducking)), t0, resta);
    }
    const ficha = S().video;
    for (const c of a.clipes) {
      const o = Math.max(0, T - c.ini), sobra = Math.min(c.dur - o, dur - Math.max(T, c.ini));
      if (sobra <= 0.02) continue;
      const buf = await som.buffer(c.arquivo);
      if (!buf || ficha.paused || S().video !== ficha) continue;
      const atraso = A.ac.currentTime + 0.02 - t0, quando = t0 + Math.max(0, c.ini - T), fonte = A.ac.createBufferSource(), g = A.ac.createGain();
      if (atraso > 0.25) continue;  // o buffer chegou tarde demais: entra na próxima reprodução
      fonte.buffer = buf; fonte.loop = c.trilha === 'musica' && c.dur > buf.duration - c.desde;
      g.gain.setValueCurveAtTime(curva(Math.ceil(sobra * 50) + 1, x => { const tc = o + x; return c.volume * Math.min(1, c.fadeIn > 0 ? tc / c.fadeIn : 1, c.fadeOut > 0 ? Math.max(0, c.dur - tc) / c.fadeOut : 1); }), Math.max(quando, A.ac.currentTime), sobra);
      fonte.connect(g).connect(c.trilha === 'musica' ? A.mus : A.sfx);
      fonte.start(quando, (c.desde + o) % buf.duration, sobra); A.nos.push(fonte);
    }
  },
  async ouvir(arq) {
    som.ligar();
    const A = S().audio; if (!A) return;
    A.ac.resume().catch(() => {});
    if (U.tocando) { try { U.tocando.stop(); } catch { /* já terminou */ } }
    const buf = await som.buffer(arq); if (!buf) { avisar('Não consegui tocar este som.', true); return; }
    const f = A.ac.createBufferSource(); f.buffer = buf; f.connect(A.ac.destination); f.start(0, 0, Math.min(buf.duration, 8)); U.tocando = f;
  },
};

/* ---------- timeline de saída ---------- */
const CORES = { seg: '#ff2d95', cam: '#2de2e6', cor: '#b98cff', titulo: '#ffffff', musica: '#4dffb0', sfx: '#ffb347' };
function trilhas() {
  const raiz = $('#ed-trilhas'); if (!raiz || !S().p) return;
  const p = P(), dur = Math.max(0.1, X().durSaida()), m = Fx.mapa(X().segs()), fx = S().fx || {};
  const pct = t => `${t / dur * 100}%`;
  const bloco = (trilha, tipo, item, ini, fim, rotulo, mexer) => {
    const n = el('div', { className: 'tl-bloco' + (fx.tipo === tipo && fx.id === item.id ? ' sel' : '') + (item.ativo === false ? ' off' : ''), title: `${rotulo} · ${X().fmt(ini)} a ${X().fmt(fim)}` }, el('span', { textContent: rotulo }));
    n.style.cssText = `--cor:${CORES[trilha]};left:${pct(ini)};width:${pct(Math.max(0.02, fim - ini))}`;
    n.onpointerdown = ev => {
      const caixa = n.parentElement.getBoundingClientRect(), r = n.getBoundingClientRect(), x0 = ev.clientX;
      const borda = mexer && r.width > 14 ? (ev.clientX - r.left < 6 ? 'a' : r.right - ev.clientX < 6 ? 'b' : '') : '';
      let moveu = false;
      S().fx = { tipo, id: item.id };
      if (tipo === 'seg') X().selSeg(item.id);
      X().arrastar(ev, e => {
        if (!mexer) return;
        const d = (e.clientX - x0) / caixa.width * dur;
        if (Math.abs(e.clientX - x0) > 2) moveu = true;
        if (moveu) { const [a, b] = mexer(d, borda); n.style.left = pct(a); n.style.width = pct(Math.max(0.02, b - a)); S().sujo = true; }
      }, () => {
        if (tipo === 'titulo') { X().selecionar(item.id); if (moveu) X().mudou(false); return; }
        S().aba = tipo === 'clipe' ? 'audio' : 'efeitos';
        if (moveu) X().mudou(false); else trilhas();
        X().pintarPainel(); X().pintarTimeline();
      });
    };
    return n;
  };
  const faixa = (ini0, fim0, set) => (d, borda) => {
    let a = ini0, b = fim0;
    if (borda === 'a') a = r2(lim(ini0 + d, 0, fim0 - 0.05)); else if (borda === 'b') b = r2(lim(fim0 + d, ini0 + 0.05, dur)); else { a = r2(lim(ini0 + d, 0, Math.max(0, dur - (fim0 - ini0)))); b = r2(a + fim0 - ini0); }
    set(a, b); return [a, b];
  };
  const linhas = [
    ['Trechos', 'seg', p.segmentos.map((g, i) => bloco('seg', 'seg', g, m.ini[i], m.ini[i] + (g.fim - g.ini) / g.vel, `${i + 1}${g.rotulo ? ' · ' + g.rotulo : ''}${g.vel !== 1 ? ` · ${g.vel}x` : ''}${i && g.trans !== 'corte' ? ' · ' + g.trans : ''}`))],
    ['Câmera', 'cam', p.efeitos.filter(e => TIPOS[e.tipo].trilha === 'cam').map(e => bloco('cam', 'efeito', e, e.ini, e.fim, TIPOS[e.tipo].nome, faixa(e.ini, e.fim, (a, b) => { e.ini = a; e.fim = b; })))],
    ['Cor e luz', 'cor', p.efeitos.filter(e => TIPOS[e.tipo].trilha === 'cor').map(e => bloco('cor', 'efeito', e, e.ini, e.fim, TIPOS[e.tipo].nome, faixa(e.ini, e.fim, (a, b) => { e.ini = a; e.fim = b; })))],
    ['Títulos', 'titulo', p.camadas.filter(c => c.tipo === 'texto' && c.fim > c.ini).map(c => bloco('titulo', 'titulo', c, c.ini, Math.min(c.fim, dur), c.texto.split('\n')[0], faixa(c.ini, Math.min(c.fim, dur), (a, b) => { c.ini = a; c.fim = b; })))],
    ['Música', 'musica', p.audio.clipes.filter(c => c.trilha === 'musica').map(c => bloco('musica', 'clipe', c, c.ini, Math.min(dur, c.ini + c.dur), c.nome || c.arquivo, faixa(c.ini, c.ini + c.dur, (a, b) => { c.ini = a; c.dur = r2(b - a); })))],
    ['Sons', 'sfx', p.audio.clipes.filter(c => c.trilha === 'sfx').map(c => bloco('sfx', 'clipe', c, c.ini, Math.min(dur, c.ini + c.dur), c.nome || c.arquivo, faixa(c.ini, c.ini + c.dur, (a, b) => { c.ini = a; c.dur = r2(b - a); })))],
  ];
  raiz.replaceChildren(...linhas.map(([nome, id, blocos]) => {
    // Blocos que se cruzam na mesma trilha ficam em andares diferentes.
    const fins = []; blocos.forEach(b => { const a = parseFloat(b.style.left), f = a + parseFloat(b.style.width); let k = fins.findIndex(x => x <= a + 0.01); if (k < 0) k = fins.length; fins[k] = f; b.style.top = `${2 + k * 20}px`; });
    const pista = el('div', { className: 'tl-pista', style: `height:${Math.max(22, 4 + fins.length * 20)}px` }, ...blocos, el('i', { className: 'tl-agulha saida' }));
    pista.onpointerdown = ev => { if (ev.target !== pista) return; const ir = e => { const r = pista.getBoundingClientRect(); S().video.pause(); X().irSaida(lim((e.clientX - r.left) / r.width, 0, 1) * dur); }; ir(ev); X().arrastar(ev, ir); };
    return el('div', { className: 'tl-linha' }, el('span', { className: 'tl-rot', textContent: nome }), pista);
  }));
  agulha(agora());
}
function agulha(T) {
  const dur = Math.max(0.1, X().durSaida());
  document.querySelectorAll('.tl-agulha.saida').forEach(n => { n.style.display = T === null ? 'none' : ''; if (T !== null) n.style.left = `${T / dur * 100}%`; });
}
function recolher(forcar) {
  const n = $('#ed-tempo'); if (!n) return;
  const rec = forcar ?? !n.classList.contains('recolhida');
  n.classList.toggle('recolhida', rec); $('#ed-tl-recolher').textContent = rec ? 'Mostrar timeline' : 'Recolher';
  try { localStorage.vcTlRec = rec ? '1' : ''; } catch { /* sem armazenamento */ }
  dispatchEvent(new Event('resize'));
}
function ligar() {
  const corpo = $('#ed-tl-corpo'), alca = $('#ed-tl-alca');
  let alt = 190; try { alt = parseInt(localStorage.vcTlAlt, 10) || 190; if (localStorage.vcTlRec) recolher(true); } catch { /* sem armazenamento */ }
  const por = h => { alt = Math.round(lim(h, 70, innerHeight * 0.6)); corpo.style.height = `${alt}px`; };
  por(alt);
  alca.onpointerdown = ev => { const y0 = ev.clientY, h0 = alt; X().arrastar(ev, e => { por(h0 + y0 - e.clientY); dispatchEvent(new Event('resize')); }, () => { try { localStorage.vcTlAlt = alt; } catch { /* sem armazenamento */ } }); };
  if (!U.sons) api('/api/sons').then(r => { U.sons = r; }).catch(() => {});
  if (!U.areas) api('/api/boas-praticas').then(r => { U.areas = (r.itens || []).filter(i => i.regra && i.regra.area_segura); }).catch(() => { U.areas = []; });
  som.carregar();
}
/* Áreas cobertas pela interface dos apps (só 9:16). Sem fonte carregada, usa margens aproximadas e avisa. */
function areaSegura() {
  const a = (U.areas || [])[0];
  return a ? { ...a.regra.area_segura, fonte: `${a.fonte} (${a.tipo === 'anuncios' ? 'especificação de anúncios' : a.tipo})` } : { topo: 220, base: 420, esquerda: 60, direita: 120, fonte: 'margens aproximadas, sem fonte oficial carregada' };
}
function guias(ctx, W, H) {
  if (P().formato !== '9:16') return;
  const a = areaSegura();
  ctx.save(); ctx.fillStyle = 'rgba(255,60,60,.22)';
  ctx.fillRect(0, 0, W, a.topo); ctx.fillRect(0, H - a.base, W, a.base); ctx.fillRect(0, a.topo, a.esquerda, H - a.topo - a.base); ctx.fillRect(W - a.direita, a.topo, a.direita, H - a.topo - a.base);
  ctx.strokeStyle = 'rgba(255,255,255,.8)'; ctx.setLineDash([14, 10]); ctx.lineWidth = 3; ctx.strokeRect(a.esquerda, a.topo, W - a.esquerda - a.direita, H - a.topo - a.base);
  ctx.fillStyle = '#fff'; ctx.font = '600 26px "Segoe UI"'; ctx.textAlign = 'center'; ctx.textBaseline = 'top'; ctx.fillText(`Área segura · ${a.fonte}`.slice(0, 70), W / 2, a.topo + 10);
  ctx.restore();
}

/* ---------- check-up ---------- */
const GRUPOS = { tecnico: ['Erros e avisos técnicos', 'Medidos no arquivo e no projeto.'], editorial: ['Sugestões editoriais', 'Baseadas no que foi medido neste vídeo. Você decide.'], hipotese: ['Hipóteses', 'Tendências e boas práticas: não garantem alcance.'] };
function aplicarSugestao(s) {
  const a = s.acao, p = P();
  if (a.tipo === 'efeito') { const e = novoEfeito(a.efeito, a.t, a.extra || {}); S().fx = { tipo: 'efeito', id: e.id }; S().aba = 'efeitos'; X().irSaida(Math.max(0, a.t - 0.5)); }
  else if (a.tipo === 'choque') { X().irSaida(a.t); aplicarChoque(a.t, a.dur || U.choque.dur); return; }
  else if (a.tipo === 'cortar') {  // tira um intervalo (tempo da fonte) de dentro de um trecho
    const g = p.segmentos.find(x => x.id === a.seg); if (!g) { avisar('Este trecho mudou. Rode o check-up de novo.', true); return; }
    X().selSeg(g.id);
    const i = p.segmentos.indexOf(g), fim0 = g.fim;
    if (a.ate >= fim0 - 0.2) p.fim = r2(a.de); else if (a.de <= g.ini + 0.2) p.inicio = r2(a.ate);
    else { p.fim = r2(a.de); X().segs(); p.segmentos.splice(i + 1, 0, { ...g, id: novoId('s'), ini: r2(a.ate), fim: fim0, trans: 'corte' }); }
  } else if (a.tipo === 'legenda') Object.assign(p.legenda, a.valores);
  else if (a.tipo === 'titulo') {
    const t = X().novoTitulo('transparente');
    Object.assign(t, { texto: a.texto, faixa: false, altMin: 0, raio: 14, y: Math.round(X().H * 0.22), ini: a.ini ?? 0, fim: a.fim ?? Math.min(4, X().durSaida()), anim: 'pop', tamanho: 84, espessura: 8 });
    X().medirTitulo(t); p.camadas.push(t); X().selecionar(t.id);
  } else if (a.tipo === 'audio') { Object.assign(p.audio[a.trilha], a.valores); }
  s.aplicada = true; refazer();
}
function abaCheckup() {
  S()._livre = false;
  const c = U.checkup && U.checkup.corte === S().id ? U.checkup : null;
  const rodar = tentar(async ev => {
    const b = ev.target; b.disabled = true; b.textContent = 'Analisando...';
    try {
      X().segs();
      const t = await api('/api/editor/checkup', { corte: S().id, projeto: P() });
      const r = await aguardarTarefa(t.id, x => { b.textContent = `${x.mensagem} ${Math.round(x.progresso * 100)}%`; });
      U.checkup = { ...r, corte: S().id };
    } finally { if (S().aba === 'checkup') X().pintarPainel(); }
  });
  const itens = [el('p', { className: 'dica', style: 'margin:0', textContent: 'Analisa este corte de verdade: arquivo, áudio, legendas e trechos. Nenhuma promessa de viralização.' }),
    botao(c ? 'Analisar de novo' : 'Fazer o check-up', rodar, 'Mede o áudio e a imagem dos trechos escolhidos', 'btn mini')];
  if (!c) return itens;
  itens.push(el('p', { className: 'dica', style: 'margin:0', textContent: c.resumo }));
  for (const [id, [titulo, sub]] of Object.entries(GRUPOS)) {
    const lista = c.itens.filter(i => i.grupo === id);
    itens.push(el('div', { className: 'sec', textContent: `${titulo} (${lista.length})` }), el('p', { className: 'dica', style: 'margin:0', textContent: lista.length ? sub : 'Nada a apontar.' }));
    for (const s of lista) itens.push(el('div', { className: `ck ck-${s.nivel || 'info'}` },
      el('div', { className: 'ck-topo' }, s.t !== null && s.t !== undefined ? el('button', { className: 'chip', type: 'button', textContent: X().fmt(s.t), title: 'Ir para este ponto', onclick: () => X().irSaida(s.t) }) : null,
        el('b', { textContent: s.problema }), el('span', { className: 'ck-conf', title: 'Confiança da análise', textContent: s.confianca })),
      el('p', { textContent: `Evidência: ${s.evidencia}` }), el('p', { textContent: `Ação: ${s.recomendacao}` }),
      s.fonte ? el('p', { className: 'ck-fonte', textContent: `Fonte: ${s.fonte}` }) : null,
      s.acao ? botao(s.aplicada ? 'Aplicado' : 'Aplicar', ev => { if (!s.aplicada) { aplicarSugestao(s); ev.target.textContent = 'Aplicado'; } }, 'Aplica no projeto (dá para desfazer com Ctrl+Z)', 'btn mini') : null));
  }
  return itens;
}

return { ligar, trilhas, agulha, novoTrecho, dividir, cameraLenta, recolher, guias, areaSegura, abaEfeitos, abaAudio, abaCheckup, som, novoEfeito, aplicarChoque, clipe, alvoCam, U };
})();
