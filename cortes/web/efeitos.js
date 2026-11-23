/* Segmentos, efeitos e áudio multitrilha. As contas espelham cortes/efeitos.py para a prévia bater com o vídeo final. */
window.VCFx = (() => {
const lim = (v, a, b) => Math.max(a, Math.min(b, v));
const r2 = v => Math.round(v * 100) / 100;
const novoId = p => `${p}${Date.now() % 1e7}${Math.floor(Math.random() * 90 + 10)}`;
const TIPOS = {
  zoom_cam: { nome: 'Zoom na webcam', trilha: 'cam', dur: 2.5, pad: { forca: 1.8, entrada: 0.35, saida: 0.3 }, dica: 'Aproxima a imagem no ponto da webcam marcada.' },
  cam_cheia: { nome: 'Webcam ampliada', trilha: 'cam', dur: 3, pad: { forca: 0.7 }, dica: 'Corte seco para a webcam, centralizada no rosto. Ela ocupa a parte de cima da tela e o gameplay continua embaixo; em 1 vira tela cheia.' },
  zoom: { nome: 'Zoom progressivo', trilha: 'cam', dur: 3, pad: { forca: 1.35, entrada: 3, saida: 0 }, dica: 'Aproxima devagar durante todo o intervalo.' },
  tremor: { nome: 'Tremor de câmera', trilha: 'cam', dur: 0.6, pad: { forca: 1, entrada: 0, saida: 0.4 }, dica: 'Sacode o quadro.' },
  freeze: { nome: 'Freeze frame', trilha: 'cam', dur: 0.6, pad: { forca: 1 }, dica: 'Congela a imagem; o áudio continua.' },
  flash: { nome: 'Flash', trilha: 'cor', dur: 0.35, pad: { forca: 0.9, entrada: 0.03, saida: 0.3 }, dica: 'Clarão branco.' },
  pb: { nome: 'Preto e branco', trilha: 'cor', dur: 3, pad: { forca: 1, entrada: 0.25, saida: 0.4 }, dica: 'Entrada longa = dessaturação progressiva; saída longa = retorno gradual das cores.' },
  vinheta: { nome: 'Vinheta escura', trilha: 'cor', dur: 3, pad: { forca: 0.8, entrada: 0.3, saida: 0.4 }, dica: 'Escurece as bordas.' },
};
const NOME_FORCA = { cam_cheia: 'Parte da tela (0,3 a 1)', zoom: 'Ampliação (x)', zoom_cam: 'Ampliação (x)', tremor: 'Intensidade', flash: 'Opacidade', pb: 'Quanto tira de cor', vinheta: 'Intensidade' };

/* ---------- tempo: fonte <-> saída ---------- */
function mapa(segs) { let t = 0; const ini = segs.map(s => { const a = t; t += (s.fim - s.ini) / s.vel; return a; }); return { ini, dur: t }; }
function saidaDe(segs, t, pref = -1) {
  const m = mapa(segs);
  const dentro = i => t >= segs[i].ini - 1e-3 && t <= segs[i].fim + 1e-3;
  const i = pref >= 0 && pref < segs.length && dentro(pref) ? pref : segs.findIndex((_, n) => dentro(n));
  return i < 0 ? null : { i, T: m.ini[i] + (lim(t, segs[i].ini, segs[i].fim) - segs[i].ini) / segs[i].vel };
}
function fonteDe(segs, T) {
  const m = mapa(segs);
  let i = m.ini.findLastIndex(a => T >= a - 1e-6); if (i < 0) i = 0;
  return { i, t: lim(segs[i].ini + (T - m.ini[i]) * segs[i].vel, segs[i].ini, segs[i].fim) };
}
function intervalosNaSaida(segs, a, b) {
  const m = mapa(segs), s = [];
  segs.forEach((g, i) => { const x = Math.max(a, g.ini), y = Math.min(b, g.fim); if (y > x) s.push([m.ini[i] + (x - g.ini) / g.vel, m.ini[i] + (y - g.ini) / g.vel]); });
  return s;
}
function transicoes(segs) {
  const m = mapa(segs), s = [];
  segs.forEach((g, i) => {
    if (!i || g.trans === 'corte') return;
    const d = g.transDur, t0 = m.ini[i];
    s.push(g.trans === 'fade' ? { cor: '#000', ini: t0 - d / 2, fim: t0 + d / 2, forca: 1, entrada: d / 2, saida: d / 2 } : { cor: '#fff', ini: t0 - 0.03, fim: t0 + d, forca: 0.9, entrada: 0.03, saida: d });
  });
  return s;
}

/* ---------- efeitos ---------- */
const k = (e, T) => (T < e.ini || T > e.fim ? 0 : lim(Math.min((T - e.ini) / Math.max(e.entrada, 0.001), (e.fim - T) / Math.max(e.saida, 0.001)), 0, 1));
/* Retângulo do quadro composto que vai ocupar a tela (zoom + tremor). */
function geometria(efs, T, W, H) {
  const zs = efs.filter(e => e.tipo === 'zoom' || e.tipo === 'zoom_cam'), ts = efs.filter(e => e.tipo === 'tremor');
  if (![...zs, ...ts].some(e => T >= e.ini && T <= e.fim)) return null;
  let z = 1; zs.forEach(e => { z += (e.forca - 1) * k(e, T); }); ts.forEach(e => { z += 0.06 * e.forca * k(e, T); });
  const amp = 0.025 * Math.min(W, H);
  const eixo = (tam, chave, freq, fase) => {
    let c = tam / 2; zs.forEach(e => { c += (e[chave] - tam / 2) * k(e, T); });
    const meio = tam / 2 / z; c = lim(c, meio, tam - meio);
    let d = 0; ts.forEach(e => { d += amp * e.forca * k(e, T) * Math.sin(2 * Math.PI * freq * T + fase); });
    return [c - meio + d, 2 * meio];
  };
  const [x, w] = eixo(W, 'cx', 11, 0), [y, h] = eixo(H, 'cy', 13, 1);
  return { x, y, w, h };
}
const saturacao = (efs, T) => lim(1 - efs.filter(e => e.tipo === 'pb').reduce((s, e) => s + e.forca * k(e, T), 0), 0, 1);
/* Animação de entrada e saída de textos (mesmos tempos do _anim em editor.py). */
function animTexto(tipo, dt, falta, entrada = true, saida = true) {
  const o = { alfa: 1, esc: 1, dy: 0 };
  const some = (a, b) => Math.min(entrada && a ? lim(dt / a, 0, 1) : 1, saida && b ? lim(falta / b, 0, 1) : 1);
  if (tipo === 'fade') o.alfa = some(0.18, 0.18);
  else if (tipo === 'subir') { o.alfa = some(0.15, 0.15); if (entrada) o.dy = 40 * (1 - lim(dt / 0.22, 0, 1)); }
  else if (tipo === 'pop') { o.alfa = some(0.06, 0.12); if (entrada) o.esc = dt < 0.11 ? 0.7 + 0.42 * dt / 0.11 : dt < 0.2 ? 1.12 - 0.12 * (dt - 0.11) / 0.09 : 1; }
  return o;
}
const popPalavra = dt => (dt < 0.07 ? 1 + 0.18 * dt / 0.07 : dt < 0.15 ? 1.18 - 0.18 * (dt - 0.07) / 0.08 : 1);

/* ---------- envelopes de volume ---------- */
function interp(chaves, t) {
  if (!chaves.length) return 1;
  if (t <= chaves[0].t) return chaves[0].v;
  for (let i = 1; i < chaves.length; i++) if (t <= chaves[i].t) { const a = chaves[i - 1], b = chaves[i]; return b.t === a.t ? b.v : a.v + (b.v - a.v) * (t - a.t) / (b.t - a.t); }
  return chaves.at(-1).v;
}
function falasNaSaida(palavras, segs, folga = 0.6) {
  const tr = palavras.flatMap(p => intervalosNaSaida(segs, p.i, p.f)).sort((a, b) => a[0] - b[0]), j = [];
  for (const [a, b] of tr) { if (j.length && a - j.at(-1)[1] <= folga) j.at(-1)[1] = Math.max(j.at(-1)[1], b); else j.push([a, b]); }
  return j;
}
function ganho(trilha, t, dur, falas, duck) {
  if (trilha.mudo) return 0;
  let g = trilha.volume * interp(trilha.chaves, t);
  if (trilha.fadeIn > 0) g *= lim(t / trilha.fadeIn, 0, 1);
  if (trilha.fadeOut > 0) g *= lim((dur - t) / trilha.fadeOut, 0, 1);
  if (falas && duck && duck.ativo) {
    let q = 0; for (const [a, b] of falas) q = Math.max(q, lim(Math.min((t - a) / duck.ataque + 1, (b - t) / duck.soltura + 1), 0, 1));
    g *= 1 - (1 - duck.nivel) * q;
  }
  return g;
}

/* ---------- projeto: campos novos com padrão ---------- */
function completar(p) {
  if (!Array.isArray(p.segmentos) || !p.segmentos.length) p.segmentos = [{ id: 's0', ini: p.inicio, fim: p.fim, vel: 1, trans: 'corte', transDur: 0.3, rotulo: '' }];
  p.efeitos = Array.isArray(p.efeitos) ? p.efeitos : [];
  const a = p.audio = p.audio || {};
  const tr = (n, v = 1) => { a[n] = { volume: v, mudo: false, fadeIn: 0, fadeOut: 0, chaves: [], ...(a[n] || {}) }; };
  tr('original', p.volume ?? 1); tr('musica'); tr('sfx');
  a.clipes = Array.isArray(a.clipes) ? a.clipes : [];
  a.ducking = { ativo: true, nivel: 0.3, ataque: 0.2, soltura: 0.5, ...(a.ducking || {}) };
  p.cor = { contraste: 1, saturacao: 1, barras: 0, ...(p.cor || {}) };
  p.opcoes = p.opcoes || {};
  return p;
}

return { TIPOS, NOME_FORCA, lim, r2, novoId, mapa, saidaDe, fonteDe, intervalosNaSaida, transicoes, k, geometria, saturacao, animTexto, popPalavra, interp, falasNaSaida, ganho, completar };
})();
