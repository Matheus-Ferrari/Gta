/* Editor visual. As contas de recorte e texto espelham cortes/editor.py para a prévia bater com o vídeo final. */
(() => {
let W = 1080, H = 1920;
const FORMATOS = { '9:16': [1080, 1920, 'Vertical · TikTok/Reels/Shorts'], '16:9': [1920, 1080, 'Horizontal'], '1:1': [1080, 1080, 'Quadrado'] };
const FONTES = ['Arial Black', 'Impact', 'Segoe UI Black', 'Arial', 'Verdana', 'Trebuchet MS', 'Georgia', 'Tahoma'];
const ESTILOS = [
  { nome: 'Vice amarelo', estilo: { fonte: 'Arial Black', tamanho: 76, cor: '#FFFFFF', destaque: '#FFE500', contorno: '#000000', espessura: 7, sombra: 3, maiusculas: true, modo: 'atual' } },
  { nome: 'Neon rosa', estilo: { fonte: 'Arial Black', tamanho: 76, cor: '#FFFFFF', destaque: '#FF2D95', contorno: '#16061F', espessura: 8, sombra: 2, maiusculas: true, modo: 'atual' } },
  { nome: 'Turquesa', estilo: { fonte: 'Impact', tamanho: 88, cor: '#FFFFFF', destaque: '#2DE2E6', contorno: '#04121C', espessura: 6, sombra: 3, maiusculas: true, modo: 'atual' } },
  { nome: 'Limpa', estilo: { fonte: 'Segoe UI Black', tamanho: 66, cor: '#FFFFFF', destaque: '#FFE500', contorno: '#000000', espessura: 5, sombra: 0, maiusculas: false, modo: 'nenhum' } },
];
const vid = (id, nome, regiao, x, y, w, h, extra = {}) => ({ id, nome, tipo: 'video', regiao, caixa: { x, y, w, h }, zoom: 1, panX: 0, panY: 0, borda: 0, bordaCor: '#FF2D95', visivel: true, ...extra });
const chatCol = (x, y, w, h) => ({ id: 'chat', nome: 'Chat', tipo: 'chat', caixa: { x, y, w, h }, tamanho: 30, cor: '#FFFFFF', contorno: '#000000', espessura: 3, fundoCor: '#000000', fundoAlfa: 0.45, visivel: true });
/* A mesma fonte horizontal entra em várias camadas, cada uma com o seu recorte (webcam, gameplay, chat ou recorte próprio). */
const PRESETS = {
  cam_titulo_jogo: { nome: 'Vice Cortes Clássico', desc: 'Webcam grande em cima, faixa branca com o título e gameplay embaixo.', cam: true, titulo: true, dividir: true, legY: 1560, fmt: ['9:16', '1:1'],
    f: () => [vid('cam', 'Webcam', 'webcam', 0, 0, 1080, 720), vid('jogo', 'Gameplay', 'gameplay', 0, 900, 1080, 1020)], mapa: [['c', 0, 0, 9, 6], ['t', 0, 6, 9, 1.5], ['j', 0, 7.5, 9, 8.5]] },
  cam_jogo: { nome: 'Webcam em cima, jogo embaixo', desc: 'Sem faixa: webcam grande e gameplay.', cam: true, dividir: true, legY: 1420, fmt: ['9:16', '1:1'],
    f: () => [vid('cam', 'Webcam', 'webcam', 0, 0, 1080, 800), vid('jogo', 'Gameplay', 'gameplay', 0, 800, 1080, 1120)], mapa: [['c', 0, 0, 9, 6.7], ['j', 0, 6.7, 9, 9.3]] },
  jogo_cam_topo: { nome: 'Jogo cheio + cam no topo', desc: 'Gameplay em tela cheia com a webcam pequena no topo.', cam: true, legY: 1500,
    f: () => [vid('jogo', 'Gameplay', 'gameplay', 0, 0, W, H), vid('cam', 'Webcam', 'webcam', Math.round(W / 2 - 230), 90, 460, 340, { borda: 6 })], fmt: ['9:16', '1:1', '16:9'], mapa: [['j', 0, 0, 9, 16], ['c', 2.5, .8, 4, 3]] },
  jogo_cheio: { nome: 'Gameplay em tela cheia', desc: 'Só o jogo, recortado sem distorcer.', cam: false, f: () => [vid('jogo', 'Gameplay', 'gameplay', 0, 0, W, H)], fmt: ['9:16', '1:1', '16:9'], mapa: [['j', 0, 0, 9, 16]] },
  jogo_cam_sobre: { nome: 'Webcam sobreposta', desc: 'Gameplay cheio e webcam que você arrasta para onde quiser.', cam: true, legY: 1500,
    f: () => [vid('jogo', 'Gameplay', 'gameplay', 0, 0, W, H), vid('cam', 'Webcam', 'webcam', 40, 110, 440, 330, { borda: 6 })], fmt: ['9:16', '1:1', '16:9'], mapa: [['j', 0, 0, 9, 16], ['c', .5, 1, 3.8, 2.9]] },
  so_cam: { nome: 'Só a câmera', desc: 'Apenas a câmera do streamer.', cam: true, f: () => [vid('cam', 'Webcam', 'webcam', 0, 0, W, H)], fmt: ['9:16', '1:1', '16:9'], mapa: [['c', 0, 0, 9, 16]] },
  jogo_centro_titulo: { nome: 'Jogo horizontal + título', desc: 'Gameplay inteiro em 16:9 no centro, título acima e legenda abaixo.', cam: false, titulo: true, legY: 1400,
    f: () => [vid('jogo', 'Gameplay', 'gameplay', 0, 656, 1080, 608)], mapa: [['t', 0, 3.6, 9, 1.6], ['j', 0, 5.4, 9, 5.1]] },
  jogo_chat: { nome: 'Gameplay + chat lateral', desc: 'Jogo à esquerda e o chat real da gravação em coluna.', cam: false, chat: true, legY: 1500, legX: 360,
    f: () => [vid('jogo', 'Gameplay', 'gameplay', 0, 0, 720, 1920)], mapa: [['j', 0, 0, 6, 16], ['h', 6, 0, 3, 16]] },
  livre: { nome: 'Layout livre', desc: 'Camadas soltas: mova, redimensione, duplique.', cam: false, fmt: ['9:16', '1:1', '16:9'], mapa: [['j', 1, 1, 7, 6], ['c', 2, 9, 5, 5]] },
};
const FAIXAS = {
  branca: { nome: 'Branca', fundoAtivo: true, fundoCor: '#FFFFFF', fundoAlfa: 1, cor: '#000000', contorno: '#000000', espessura: 1, bordaFaixa: 0 },
  vermelha: { nome: 'Vermelha', fundoAtivo: true, fundoCor: '#E10613', fundoAlfa: 1, cor: '#FFFFFF', contorno: '#000000', espessura: 4, bordaFaixa: 0 },
  preta: { nome: 'Preta', fundoAtivo: true, fundoCor: '#000000', fundoAlfa: 1, cor: '#FFFFFF', contorno: '#000000', espessura: 0, bordaFaixa: 0 },
  transparente: { nome: 'Transparente', fundoAtivo: false, fundoCor: '#000000', fundoAlfa: 0, cor: '#FFFFFF', contorno: '#000000', espessura: 6, bordaFaixa: 0 },
};
const serve = pr => (pr.fmt || ['9:16']).includes(S.p.formato || '9:16');
const QUALIDADE = { alta: ['Alta (12 Mbps)', 12e6], media: ['Média (8 Mbps)', 8e6], leve: ['Leve (4,5 Mbps)', 4.5e6] };

const S = { ativo: false, id: null, d: null, p: null, sel: null, aba: 'templates', video: null, ctx: null, sujo: true, onda: [], hist: [], timer: null, raf: 0, imgs: {}, chat: [], chatChave: '', audio: null };
window.__viceClips = S;
const Fx = window.VCFx, UI = () => window.VCUI;
/* O trecho selecionado é editado por p.inicio/p.fim (como nos projetos antigos); aqui os dois ficam sempre iguais. */
const segs = () => { const g = S.p.segmentos.find(x => x.id === S.seg) || S.p.segmentos[0]; S.seg = g.id; g.ini = S.p.inicio; g.fim = S.p.fim; return S.p.segmentos; };
const segSel = () => segs().find(x => x.id === S.seg);
function selSeg(id) { const g = S.p.segmentos.find(x => x.id === id) || S.p.segmentos[0]; S.seg = g.id; S.p.inicio = g.ini; S.p.fim = g.fim; }
const durSaida = () => Fx.mapa(segs()).dur;
const tempoSaida = () => (S.video ? Fx.saidaDe(segs(), S.video.currentTime, S.tocando ?? -1) : null);
function irSaida(T) {
  const f = Fx.fonteDe(segs(), limitar(T, 0, Math.max(0, durSaida() - 0.02)));
  S.tocando = f.i; S.video.currentTime = f.t; S.video.playbackRate = segs()[f.i].vel; S.sujo = true;
  if (!S.video.paused) UI().som.tocar(T);
}
/* Recorte da webcam para uma caixa bw x bh, centralizado no rosto (igual ao recorte_cam do editor.py). */
function recorteCam(p, bw, bh, vw, vh) {
  const r = p.regioes.webcam, f = p.regioes.rosto, rl = r.w * vw, ra = r.h * vh, alvo = bw / bh;
  const l = rl / ra > alvo ? ra * alvo : rl, a = rl / ra > alvo ? ra : rl / alvo, cx = r.x * vw + rl / 2, cy = r.y * vh + ra / 2;
  const fx = f ? (f.x + f.w / 2) * vw : cx, fy = f ? (f.y + f.h / 2) * vh + 0.08 * a : cy;
  return efetivo(r, { w: bw, h: bh }, 1, rl - l > 1 ? limitar((fx - cx) / ((rl - l) / 2), -1, 1) : 0, ra - a > 1 ? limitar((fy - cy) / ((ra - a) / 2), -1, 1) : 0, vw, vh);
}
const telas = {};
function tela(n) { const c = telas[n] || (telas[n] = document.createElement('canvas')); if (c.width !== W || c.height !== H) { c.width = W; c.height = H; } return c; }

/* ---------- utilidades ---------- */
const fmt = t => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}.${Math.floor((t % 1) * 10)}`;
const limitar = (v, a, b) => Math.max(a, Math.min(b, v));
const par = v => 2 * Math.trunc(v / 2 + 0.5);
function efetivo(r, cx, zoom, panX, panY, w, h) {
  const rx = r.x * w, ry = r.y * h, rl = r.w * w, ra = r.h * h, alvo = cx.w / cx.h;
  let l = rl / ra > alvo ? ra * alvo : rl, a = rl / ra > alvo ? ra : rl / alvo;
  l /= zoom; a /= zoom;
  const cxx = rx + rl / 2 + panX * (rl - l) / 2, cyy = ry + ra / 2 + panY * (ra - a) / 2;
  const fl = Math.max(2, Math.min(par(l), w - w % 2)), fa = Math.max(2, Math.min(par(a), h - h % 2));
  return [Math.max(0, Math.min(w - fl, par(cxx - l / 2))), Math.max(0, Math.min(h - fa, par(cyy - a / 2))), fl, fa];
}
const med = document.createElement('canvas').getContext('2d');
const metricas = {};
function metrica(f) {
  if (!metricas[f]) {
    med.font = `100px "${f}"`;
    const m = med.measureText('Hg'), a = m.fontBoundingBoxAscent, d = m.fontBoundingBoxDescent;
    metricas[f] = { asc: a / (a + d), esc: 100 / (a + d) };
  }
  return metricas[f];
}
const fonteCanvas = (f, tam) => `${tam * metrica(f).esc}px "${f}"`;
/* Quebra automática: a prévia decide as linhas e o render usa as mesmas (campo quebra). */
function quebrarLinhas(texto, max) {
  const saida = [];
  for (const par of texto.split('\n')) {
    let linha = '';
    for (const w of par.split(/\s+/).filter(Boolean)) {
      const nova = linha ? `${linha} ${w}` : w;
      if (linha && med.measureText(nova.replace(/\*/g, '')).width > max) { saida.push(linha); linha = w; } else linha = nova;
    }
    saida.push(linha);
  }
  return saida;
}
function medirTitulo(c) {
  med.font = fonteCanvas(c.fonte, c.tamanho);
  const linhas = quebrarLinhas(c.texto, c.largMax || (c.faixa ? W - 80 : W - 180));
  c.quebra = linhas.join('\n');
  const larg = Math.max(...linhas.map(l => med.measureText(l.replace(/\*/g, '')).width), 10);
  c.caixa = { w: c.faixa ? W : Math.round((c.largMax || larg) + 72), h: Math.round(Math.max(linhas.length * c.tamanho + 32, c.altMin || 0)) };
  if (c.faixa) c.x = W / 2;
}
function quebrar(b, L) {
  med.font = fonteCanvas(L.fonte, L.tamanho);
  let linha = '';
  b.forEach((w, n) => {
    const t = L.maiusculas ? w.p.toUpperCase() : w.p, nova = linha ? `${linha} ${t}` : t;
    if (n && med.measureText(nova).width > W - 120) { w.q = true; linha = t; } else { w.q = false; linha = nova; }
  });
}
function agrupar(pal, L) {
  const max = L.maxPalavras, lim = max * 7, gs = [];
  let a = [];
  for (const p of pal) {
    if (a.length && (a.length >= max || a.reduce((s, x) => s + x.p.length, 0) + p.p.length > lim || p.i - a.at(-1).f > 0.4 || /[.!?…]$/.test(a.at(-1).p))) { gs.push(a); a = []; }
    a.push({ p: p.p, i: p.i, f: p.f, d: !!p.d, q: false });
  }
  if (a.length) gs.push(a);
  gs.forEach(b => quebrar(b, L));
  return gs;
}
const reQuebrar = () => S.p.legenda.blocos.forEach(b => quebrar(b, S.p.legenda));
function legendaEm(t) {
  const L = S.p.legenda;
  if (!L.ativa) return null;
  const tt = t - L.offset, B = L.blocos;
  for (let g = 0; g < B.length; g++) {
    const b = B[g], prox = g + 1 < B.length ? B[g + 1][0].i : Infinity, fim = Math.min(b.at(-1).f + 0.15, prox);
    if (tt < b[0].i - 0.01) continue;
    if (L.modo === 'atual' || L.modo === 'karaoke') {
      for (let n = 0; n < b.length; n++) {
        const ate = n + 1 < b.length ? b[n + 1].i : fim;
        if (tt >= b[n].i && tt < ate) return { b, marca: n, dt: tt - b[0].i, falta: fim - tt, dtp: tt - b[n].i };
      }
    } else if (tt >= b[0].i && tt < fim) return { b, marca: null, dt: tt - b[0].i, falta: fim - tt, dtp: 0 };
  }
  return null;
}
const chavesLeg = L => new Set((L.chaves || '').toLowerCase().split(/[\s,;]+/).filter(Boolean));
/* *palavra* troca a cor; a marcação pode atravessar linhas (igual ao _marcado do editor.py). */
function runsMarcados(linhas, cor, destaque) {
  let forte = false;
  return linhas.map(l => l.split('*').map((t, i) => { if (i) forte = !forte; return { t, cor: forte ? destaque : cor }; }).filter(r => r.t));
}

/* ---------- desenho ---------- */
function pintarTexto(ctx, linhas, cx, cy, est, esq = null) {
  const tam = est.tamanho, m = metrica(est.fonte), topo = cy - tam * linhas.length / 2;
  ctx.font = fonteCanvas(est.fonte, tam);
  ctx.textBaseline = 'alphabetic'; ctx.textAlign = 'left'; ctx.lineJoin = 'round'; ctx.miterLimit = 2;
  const pos = [];
  linhas.forEach((runs, i) => {
    const y = topo + i * tam + tam * m.asc;
    if (runs.some(r => r.esc)) {  // palavra em "pop": cada pedaço tem a sua largura
      const ws = runs.map(r => { ctx.font = fonteCanvas(est.fonte, tam * (r.esc || 1)); return ctx.measureText(r.t).width; });
      let x = esq === null ? cx - ws.reduce((a, b) => a + b, 0) / 2 : esq;
      runs.forEach((r, j) => { pos.push({ t: r.t, cor: r.cor, x, y, f: fonteCanvas(est.fonte, tam * (r.esc || 1)) }); x += ws[j]; });
      ctx.font = fonteCanvas(est.fonte, tam);
      return;
    }
    const inteira = runs.map(r => r.t).join('');
    const x0 = esq === null ? cx - ctx.measureText(inteira).width / 2 : esq;
    let antes = '';
    for (const r of runs) { pos.push({ t: r.t, cor: r.cor, x: x0 + ctx.measureText(antes).width, y }); antes += r.t; }
  });
  const fonte = p => { if (p.f) ctx.font = p.f; else ctx.font = fonteCanvas(est.fonte, tam); };
  if (est.sombra > 0) {
    ctx.fillStyle = ctx.strokeStyle = 'rgba(0,0,0,.41)'; ctx.lineWidth = est.espessura * 2;
    for (const p of pos) { fonte(p); if (est.espessura > 0) ctx.strokeText(p.t, p.x + est.sombra, p.y + est.sombra); ctx.fillText(p.t, p.x + est.sombra, p.y + est.sombra); }
  }
  if (est.espessura > 0) { ctx.strokeStyle = est.contorno; ctx.lineWidth = est.espessura * 2; for (const p of pos) { fonte(p); ctx.strokeText(p.t, p.x, p.y); } }
  for (const p of pos) { fonte(p); ctx.fillStyle = p.cor; ctx.fillText(p.t, p.x, p.y); }
}
function retanguloBezier(ctx, x, y, l, a, r) {
  r = Math.min(r, Math.floor(l / 2), Math.floor(a / 2));
  ctx.beginPath(); ctx.moveTo(x + r, y); ctx.lineTo(x + l - r, y); ctx.bezierCurveTo(x + l, y, x + l, y, x + l, y + r); ctx.lineTo(x + l, y + a - r);
  ctx.bezierCurveTo(x + l, y + a, x + l, y + a, x + l - r, y + a); ctx.lineTo(x + r, y + a); ctx.bezierCurveTo(x, y + a, x, y + a, x, y + a - r); ctx.lineTo(x, y + r); ctx.bezierCurveTo(x, y, x, y, x + r, y); ctx.closePath();
}
const regiaoDe = c => (c.regiao === 'propria' ? c.recorte : S.p.regioes[c.regiao]);
const NOMES_REGIAO = { webcam: 'Webcam', gameplay: 'Gameplay', chat: 'Chat do vídeo', propria: 'Recorte próprio' };
function imagem(arquivo) {
  let i = S.imgs[arquivo];
  if (!i) { i = S.imgs[arquivo] = new Image(); i.onload = () => { S.sujo = true; }; i.src = `/grafico/${arquivo}`; }
  return i;
}
/* ---------- chat real (sem mensagens inventadas) ---------- */
const CORES_NOME = ['#FF4F9A', '#2DE2E6', '#FFB347', '#9B7BFF', '#5CFF9D', '#FF6B6B', '#4FC3FF', '#FFE45C'];
function corNome(n) { let h = 0; for (const ch of n) h = (h * 31 + ch.charCodeAt(0)) >>> 0; return CORES_NOME[h % CORES_NOME.length]; }
function linhasChat(c) {
  const chave = `${c.caixa.w}|${c.tamanho}|${(S.d.chat || []).length}`;
  if (S.chatChave === chave) return S.chat;
  med.font = fonteCanvas('Arial', c.tamanho);
  const max = c.caixa.w - 2 * Math.round(c.tamanho * 0.4);
  S.chat = (S.d.chat || []).map(m => {
    const nome = m.n ? `${m.n}: ` : '';
    return { t: m.t, k: nome.length, c: m.c || corNome(m.n || '?'), l: quebrarLinhas(nome + m.m, max).slice(0, 12) };
  });
  S.chatChave = chave;
  return S.chat;
}
function chatVisivel(msgs, t, altura, lh, espaco) {
  const vis = []; let usado = 0;
  for (let i = msgs.length - 1; i >= 0; i--) {
    const m = msgs[i];
    if (m.t > t) continue;
    const alt = m.l.length * lh + (vis.length ? espaco : 0);
    if (usado + alt > altura) break;
    vis.push(m); usado += alt;
  }
  return vis;
}
function pintarEsquerda(ctx, runs, x, topo, est) {
  const m = metrica(est.fonte), y = topo + est.tamanho * m.asc;
  ctx.font = fonteCanvas(est.fonte, est.tamanho); ctx.textBaseline = 'alphabetic'; ctx.textAlign = 'left'; ctx.lineJoin = 'round'; ctx.miterLimit = 2;
  let px = x;
  const pos = runs.map(r => { const o = { ...r, x: px }; px += ctx.measureText(r.t).width; return o; });
  if (est.espessura > 0) { ctx.strokeStyle = est.contorno; ctx.lineWidth = est.espessura * 2; pos.forEach(r => ctx.strokeText(r.t, r.x, y)); }
  pos.forEach(r => { ctx.fillStyle = r.cor; ctx.fillText(r.t, r.x, y); });
}
function desenharChat(ctx, c, t) {
  const tam = c.tamanho, pad = Math.round(tam * 0.4), lh = Math.round(tam * 1.18), esp = Math.round(tam * 0.3);
  const x0 = Math.round(c.caixa.x), y0 = Math.round(c.caixa.y), l = Math.round(c.caixa.w), a = Math.round(c.caixa.h);
  if (c.fundoAlfa > 0) { ctx.globalAlpha = c.fundoAlfa; ctx.fillStyle = c.fundoCor; retanguloBezier(ctx, x0, y0, l, a, 14); ctx.fill(); ctx.globalAlpha = 1; }
  const est = { fonte: 'Arial', tamanho: tam, espessura: c.espessura, contorno: c.contorno };
  let base = y0 + a - pad;
  for (const m of chatVisivel(linhasChat(c), Math.max(t, S.p.inicio), a - 2 * pad, lh, esp)) {
    base -= m.l.length * lh;
    m.l.forEach((linha, j) => pintarEsquerda(ctx, j === 0 && m.k ? [{ t: linha.slice(0, m.k), cor: m.c }, { t: linha.slice(m.k), cor: c.cor }] : [{ t: linha, cor: c.cor }], x0 + pad, base + j * lh, est));
    base -= esp;
  }
}
function desenhar() {
  const { ctx, video, p } = S;
  if (!ctx) return;
  const pos = tempoSaida(), T = pos ? pos.T : null;
  const efs = T === null ? [] : p.efeitos.filter(e => e.ativo !== false);
  const agora = e => T >= e.ini && T <= e.fim;
  const o1 = tela('o1'), g = o1.getContext('2d');
  g.globalAlpha = 1; g.imageSmoothingEnabled = true; g.imageSmoothingQuality = 'high';
  g.fillStyle = p.fundo; g.fillRect(0, 0, W, H);
  for (const c of p.camadas) {
    if (!c.visivel || !['video', 'imagem', 'forma'].includes(c.tipo)) continue;
    const px = Math.round(c.caixa.x), py = Math.round(c.caixa.y);
    if (c.tipo === 'forma') { g.globalAlpha = c.alfa; g.fillStyle = c.cor; g.fillRect(px, py, Math.max(1, Math.round(c.caixa.w)), Math.max(1, Math.round(c.caixa.h))); g.globalAlpha = 1; continue; }
    const bl = par(c.caixa.w), ba = par(c.caixa.h);
    if (c.tipo === 'imagem') {
      const i = imagem(c.arquivo);
      if (i.complete && i.naturalWidth) {
        g.save(); g.globalAlpha = c.opacidade;
        if (c.circular) { g.beginPath(); g.arc(px + bl / 2, py + ba / 2, Math.min(bl, ba) / 2, 0, 2 * Math.PI); g.clip(); }
        g.drawImage(i, px, py, bl, ba); g.restore();
      }
      continue;
    }
    const r = regiaoDe(c);
    if (!r) {
      g.fillStyle = '#1b1030'; g.fillRect(px, py, bl, ba);
      g.fillStyle = '#ff5fb0'; g.font = '700 40px "Segoe UI"'; g.textAlign = 'center'; g.textBaseline = 'middle';
      g.fillText(`${NOMES_REGIAO[c.regiao]} não marcada`, px + bl / 2, py + ba / 2); continue;
    }
    if (video.videoWidth) { const [x, y, l, a] = efetivo(r, c.caixa, c.zoom, c.panX, c.panY, video.videoWidth, video.videoHeight); g.drawImage(video, x, y, l, a, px, py, bl, ba); }
    if (c.borda > 0) { g.strokeStyle = c.bordaCor; g.lineWidth = c.borda; g.strokeRect(px + c.borda / 2, py + c.borda / 2, bl - c.borda, ba - c.borda); }
  }
  if (p.regioes.webcam && video.videoWidth) for (const e of efs) {
    if (e.tipo !== 'cam_cheia' || !agora(e)) continue;
    const hc = Math.min(H, par(Math.max(0.3, e.forca) * H)), vw = video.videoWidth, vh = video.videoHeight;
    const [x, y, l, a] = recorteCam(p, W, hc, vw, vh); g.drawImage(video, x, y, l, a, 0, 0, W, hc);
    if (hc < H) { const [gx, gy, gl, ga] = efetivo(p.regioes.gameplay, { w: W, h: H - hc }, 1, 0, 0, vw, vh); g.drawImage(video, gx, gy, gl, ga, 0, hc, W, H - hc); }
  }
  let quadro = o1;
  const geo = T !== null && Fx.geometria(efs, T, W, H), fr = efs.find(e => e.tipo === 'freeze' && T >= e.ini && T < e.fim);
  if (geo || fr) {
    const o2 = tela('o2'), g2 = o2.getContext('2d');
    g2.imageSmoothingQuality = 'high';
    if (geo) g2.drawImage(o1, geo.x, geo.y, geo.w, geo.h, 0, 0, W, H); else g2.drawImage(o1, 0, 0);
    quadro = o2;
    if (fr) { if (S.frz !== fr.id) { tela('o3').getContext('2d').drawImage(o2, 0, 0); S.frz = fr.id; } quadro = tela('o3'); }
  }
  if (!fr) S.frz = null;
  const sat = p.cor.saturacao * (T === null ? 1 : Fx.saturacao(efs, T)), con = p.cor.contraste;
  ctx.globalAlpha = 1;
  ctx.filter = Math.abs(sat - 1) > 0.004 || Math.abs(con - 1) > 0.004 ? `contrast(${con}) saturate(${sat})` : 'none';
  ctx.drawImage(quadro, 0, 0); ctx.filter = 'none';
  if (p.cor.barras > 0.001) { const h = Math.round(p.cor.barras * H); ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, h); ctx.fillRect(0, H - h, W, h); }
  for (const e of efs) if (e.tipo === 'vinheta' && agora(e)) { const i = imagem(S.d.vinheta[p.formato].replace('/grafico/', '')); if (i.complete && i.naturalWidth) { ctx.globalAlpha = e.forca * Fx.k(e, T); ctx.drawImage(i, 0, 0, W, H); ctx.globalAlpha = 1; } }
  for (const c of p.camadas) {
    if (c.tipo !== 'texto' || !c.visivel || !c.texto.trim()) continue;
    let an = { alfa: 1, esc: 1, dy: 0 }, some = 1;
    if (c.fim > c.ini) {  // título editorial: só no intervalo, com animação
      if (T === null || T < c.ini || T >= c.fim) continue;
      an = Fx.animTexto(c.anim, T - c.ini, c.fim - T);
      if (c.anim && c.anim !== 'nenhuma') some = Math.min(1, (T - c.ini) / 0.15, (c.fim - T) / 0.15);
    }
    const x = Math.round(c.x), y = Math.round(c.y), l = Math.round(c.caixa.w), a = Math.round(c.caixa.h), x0 = x - Math.floor(l / 2), y0 = y - Math.floor(a / 2);
    if (c.fundoAtivo) {
      ctx.globalAlpha = c.fundoAlfa * some; ctx.fillStyle = c.fundoCor; retanguloBezier(ctx, x0, y0, l, a, Math.round(c.raio)); ctx.fill();
      if (c.bordaFaixa > 0) { const t = Math.round(c.bordaFaixa); ctx.globalAlpha = some; ctx.fillStyle = c.bordaFaixaCor; ctx.fillRect(x0, y0, l, t); ctx.fillRect(x0, y0 + a - t, l, t); }
      ctx.globalAlpha = 1;
    }
    const esq = c.alinhar === 'esquerda' ? x0 + (c.faixa ? 40 : 36) : null, ax = esq === null ? x : esq;
    ctx.save(); ctx.globalAlpha = an.alfa; ctx.translate(ax, y + an.dy); ctx.scale(an.esc, an.esc); ctx.translate(-ax, -y);
    pintarTexto(ctx, runsMarcados((c.quebra || c.texto).split('\n'), c.cor, c.destaque || '#E10613'), x, y, c, esq);
    ctx.restore();
  }
  for (const c of p.camadas) if (c.tipo === 'chat' && c.visivel) desenharChat(ctx, c, video.currentTime || 0);
  const L = p.legenda, atual = legendaEm(video.currentTime || 0);
  if (atual) {
    const linhas = [[]], chaves = chavesLeg(L), b = atual.b;
    b.forEach((w, n) => {
      const t = L.maiusculas ? w.p.toUpperCase() : w.p;
      const forte = L.modo === 'atual' ? n === atual.marca : L.modo === 'karaoke' ? n <= atual.marca : (L.modo === 'marcadas' && w.d);
      const cor = forte ? L.destaque : chaves.has(w.p.toLowerCase().replace(/[^\p{L}\p{N}_]/gu, '')) ? (L.corChave || '#FF2D95') : L.cor;
      if (w.q && n) linhas.push([]); else if (n) linhas.at(-1).push({ t: ' ', cor: L.cor });
      linhas.at(-1).push({ t, cor, esc: L.popPalavra && n === atual.marca ? Fx.popPalavra(atual.dtp) : 0 });
    });
    const ult = L.modo === 'atual' || L.modo === 'karaoke' ? atual.marca === b.length - 1 : true;
    const an = Fx.animTexto(L.anim || 'nenhuma', atual.dt, atual.falta, L.modo === 'atual' || L.modo === 'karaoke' ? atual.marca === 0 : true, ult);
    const lx = Math.round(L.x), ly = Math.round(L.y);
    ctx.save(); ctx.globalAlpha = an.alfa; ctx.translate(lx, ly + an.dy); ctx.scale(an.esc, an.esc); ctx.translate(-lx, -ly);
    pintarTexto(ctx, linhas, lx, ly, L);
    ctx.restore();
  }
  if (T !== null) for (const e of [...efs.filter(x => x.tipo === 'flash').map(x => ({ ...x, cor: '#fff' })), ...Fx.transicoes(segs())]) {
    if (T < e.ini || T > e.fim) continue;
    ctx.globalAlpha = e.forca * Fx.k(e, T); ctx.fillStyle = e.cor; ctx.fillRect(0, 0, W, H); ctx.globalAlpha = 1;
  }
  if (S.guias) UI().guias(ctx, W, H);
}
function laco() {
  if (!S.ativo) return;
  const v = S.video;
  if (v) {
    if (!v.paused) {  // toca os trechos na ordem e volta ao primeiro
      const lista = segs(); let i = Math.min(S.tocando ?? 0, lista.length - 1);
      const fim = v.currentTime >= lista[i].fim - 0.004;
      if (fim || v.currentTime < lista[i].ini - 0.25) {
        if (fim) i = (i + 1) % lista.length;
        S.tocando = i; v.currentTime = lista[i].ini; v.playbackRate = lista[i].vel;
        if (fim && i === 0) UI().som.tocar(0);
      } else if (v.playbackRate !== lista[i].vel) v.playbackRate = lista[i].vel;
    }
    if (!v.paused || S.sujo) { desenhar(); S.sujo = false; atualizarTempo(); }
  }
  S.raf = requestAnimationFrame(laco);
}

/* ---------- arrastar ---------- */
function arrastar(ev, mover, fim) {
  ev.preventDefault(); ev.stopPropagation();
  const alvo = ev.currentTarget; alvo.setPointerCapture(ev.pointerId);
  const m = e => mover(e), u = () => { alvo.removeEventListener('pointermove', m); alvo.removeEventListener('pointerup', u); alvo.removeEventListener('pointercancel', u); if (fim) fim(); };
  alvo.addEventListener('pointermove', m); alvo.addEventListener('pointerup', u); alvo.addEventListener('pointercancel', u);
}
const alcas = () => ['nw', 'ne', 'sw', 'se'].map(a => { const n = el('i', { className: 'alca' }); n.dataset.a = a; return n; });
function ajustaFracao(r, a, dx, dy) {
  const min = 0.04;
  let { x, y, w, h } = r;
  if (!a) return { x: limitar(x + dx, 0, 1 - w), y: limitar(y + dy, 0, 1 - h), w, h };
  if (a.includes('w')) { const nx = limitar(x + dx, 0, x + w - min); w += x - nx; x = nx; } else w = limitar(w + dx, min, 1 - x);
  if (a.includes('n')) { const ny = limitar(y + dy, 0, y + h - min); h += y - ny; y = ny; } else h = limitar(h + dy, min, 1 - y);
  return { x, y, w, h };
}

/* ---------- regiões da fonte ---------- */
function pintarRegioes() {
  const wrap = $('#ed-fonte');
  const status = $('#ed-cam-status');
  const preset = S.d.regioes && (S.d.regioes.webcam || S.d.regioes.gameplay) ? ` · preset de ${S.d.streamer || 'streamer'} salvo` : '';
  if (status) status.textContent = (S.p.regioes.webcam ? 'Webcam marcada' : 'Sem webcam marcada') + preset;
  wrap.querySelectorAll('.regiao').forEach(n => n.remove());
  const sel = S.p.camadas.find(c => c.id === S.sel && c.tipo === 'video' && c.regiao === 'propria');
  const itens = [['gameplay', 'var(--ciano)', 'Gameplay'], ['chat', 'var(--sol)', 'Chat do vídeo'], ['webcam', 'var(--rosa)', 'Webcam']];
  if (sel) itens.push([`propria:${sel.id}`, '#ffe45c', `Recorte: ${sel.nome || 'camada'}`]);
  for (const [nome, cor, rotulo] of itens) {
    const ler = () => (nome.startsWith('propria:') ? sel.recorte : S.p.regioes[nome]);
    const r = ler();
    if (!r) continue;
    const n = el('div', { className: 'regiao' }, el('span', { textContent: rotulo }), ...alcas());
    n.dataset.regiao = nome;
    n.style.cssText = `--cor:${cor};left:${r.x * 100}%;top:${r.y * 100}%;width:${r.w * 100}%;height:${r.h * 100}%`;
    n.onpointerdown = ev => {
      const a = ev.target.dataset.a, r0 = { ...ler() }, box = wrap.getBoundingClientRect(), x0 = ev.clientX, y0 = ev.clientY;
      arrastar(ev, e => {
        const q = ajustaFracao(r0, a, (e.clientX - x0) / box.width, (e.clientY - y0) / box.height);
        if (nome.startsWith('propria:')) sel.recorte = q; else S.p.regioes[nome] = q;
        n.style.left = `${q.x * 100}%`; n.style.top = `${q.y * 100}%`; n.style.width = `${q.w * 100}%`; n.style.height = `${q.h * 100}%`;
        S.sujo = true;
      }, () => mudou(false));
    };
    wrap.append(n);
  }
}
const msgFonte = t => { const n = $('#ed-msg'); if (n) n.textContent = t || ''; };
async function detectarWebcam() {
  msgFonte('Procurando webcam no vídeo...');
  try {
    const r = await api('/api/editor/detectar-webcam', { corte: S.id });
    if (r.encontrada) { S.p.regioes.webcam = r.regiao; pintarRegioes(); S.sujo = true; }
    msgFonte(r.mensagem);
    return !!r.encontrada;
  } catch (e) { msgFonte(e.message); return false; }
}

/* ---------- presets ---------- */
function estiloFaixa(nome) { const { nome: _, ...r } = FAIXAS[nome]; return r; }
function novoTitulo(estilo = 'branca') {
  const fala = (S.d.palavras || []).filter(w => w.i >= S.p.inicio && w.i < S.p.fim).slice(0, 7).map(w => w.p).join(' ');
  const base = S.d.manual && S.d.texto ? S.d.texto : ((S.d.manual ? fala : S.d.texto) || fala || 'Título do corte').split(/\s+/).slice(0, 7).join(' ');
  return { id: `t${Date.now() % 100000}`, nome: 'Título', tipo: 'texto', texto: base.toUpperCase(), x: W / 2, y: Math.round(H * 0.42), fonte: 'Arial Black', tamanho: 60, sombra: 0, raio: 0,
    faixa: true, altMin: 200, caixa: { w: W, h: 200 }, visivel: true, bordaFaixa: 0, bordaFaixaCor: '#000000', ...estiloFaixa(estilo) };
}
/* Recalcula as caixas dos layouts empilhados a partir da divisão webcam/gameplay e da altura da faixa. */
function reorganizar() {
  const p = S.p, pr = p.preset;
  const cam = p.camadas.find(c => c.id === 'cam' && c.tipo === 'video'), jogo = p.camadas.find(c => c.id === 'jogo' && c.tipo === 'video');
  const faixa = p.camadas.find(c => c.tipo === 'texto' && c.faixa && c.visivel);
  if (faixa) medirTitulo(faixa);
  if (pr === 'cam_titulo_jogo' && cam && jogo && faixa) {
    const fh = Math.round(faixa.caixa.h), ch = Math.round((H - fh) * p.divisao);
    cam.caixa = { x: 0, y: 0, w: W, h: ch }; faixa.y = ch + Math.floor(fh / 2); jogo.caixa = { x: 0, y: ch + fh, w: W, h: H - ch - fh };
  } else if (pr === 'cam_jogo' && cam && jogo) {
    const ch = Math.round(H * p.divisao);
    cam.caixa = { x: 0, y: 0, w: W, h: ch }; jogo.caixa = { x: 0, y: ch, w: W, h: H - ch };
  } else if (pr === 'jogo_centro_titulo' && jogo && faixa) {
    faixa.y = Math.round(jogo.caixa.y - faixa.caixa.h / 2 - 30);
  }
  S.sujo = true;
}
function aplicarPreset(id) {
  const pr = PRESETS[id], p = S.p;
  if (id === 'livre') {
    p.preset = 'livre';
    S.sel = (p.camadas.find(c => c.tipo === 'video') || {}).id || null;
    S.aba = 'camadas';
    pintarPresets(); pintarPainel(); pintarSelecao(); mudou(false);
    avisar('Layout livre: arraste, redimensione, duplique camadas e use a rodinha do mouse para ampliar.');
    return;
  }
  let extra = [];
  if (pr.chat) {
    if ((S.d.chat || []).length) extra = [chatCol(720, 0, 360, H)];
    else if (p.regioes.chat) extra = [vid('chatv', 'Chat do vídeo', 'chat', 720, 0, 360, H)];
    else {
      msgFonte('Chat indisponível: esta fonte não tem chat gravado. Se o chat aparece dentro da transmissão, clique em Marcar chat e ajuste o retângulo laranja.');
      avisar('Esta fonte não tem chat disponível. Nada foi inventado.', true);
      return;
    }
  }
  if (pr.cam && !p.regioes.webcam) {
    p.regioes.webcam = { x: 0.7, y: 0.03, w: 0.27, h: 0.3 };
    destacar('#ed-caixa-fonte');
    msgFonte('Arraste o retângulo rosa até a câmera do streamer na fonte original. Se o vídeo não tem câmera, escolha Gameplay em tela cheia.');
  }
  const imagens = p.camadas.filter(c => c.tipo === 'imagem'), titulos = p.camadas.filter(c => c.tipo === 'texto');
  const novas = [...pr.f(), ...extra];
  if (pr.titulo) {
    const t = titulos.shift() || novoTitulo(id === 'jogo_centro_titulo' ? 'transparente' : 'branca');
    Object.assign(t, { faixa: true, x: W / 2, visivel: true });
    if (!t.altMin) t.altMin = 200;
    novas.push(t);
  } else titulos.forEach(t => { if (t.faixa) t.visivel = false; });
  p.camadas = [...novas, ...imagens, ...titulos];
  Object.assign(p.legenda, { y: H === 1920 && pr.legY ? pr.legY : Math.round(H * 0.8), x: (W === 1080 && pr.legX) || W / 2 });
  p.preset = id;
  S.sel = null;
  reorganizar();
  pintarRegioes(); pintarPresets(); pintarPainel(); pintarSelecao(); mudou(false);
}
function definirFormato(f, aplicar = true) {
  const p = S.p, [w0, h0] = [W, H];
  p.formato = FORMATOS[f] ? f : '9:16';
  [W, H] = FORMATOS[p.formato];
  const cv = $('#ed-canvas'); if (cv) { cv.width = W; cv.height = H; }
  const pw = $('#ed-prev'); if (pw) pw.style.aspectRatio = `${W} / ${H}`;
  if (!aplicar || (w0 === W && h0 === H)) return;
  // O projeto continua: template compatível é remontado; o resto é reescalado para caber no novo quadro.
  const k = Math.min(W / w0, H / h0), dx = (W - w0 * k) / 2, dy = (H - h0 * k) / 2;
  for (const c of p.camadas) {
    if (c.tipo === 'texto') { c.x = Math.round(c.x * k + dx); c.y = Math.round(c.y * k + dy); medirTitulo(c); }
    else c.caixa = { x: Math.round(c.caixa.x * k + dx), y: Math.round(c.caixa.y * k + dy), w: Math.round(c.caixa.w * k), h: Math.round(c.caixa.h * k) };
  }
  Object.assign(p.legenda, { x: W / 2, y: Math.round(H * 0.8) }); reQuebrar();
  const pr = PRESETS[p.preset];
  if (pr && p.preset !== 'livre' && serve(pr)) aplicarPreset(p.preset);
  else if (p.preset !== 'livre') { p.preset = 'livre'; avisar('Este template não existe neste formato: as camadas foram reescaladas em Layout livre.'); }
  ajustarLayout(); pintarPresets(); pintarPainel(); pintarSelecao(); mudou(false);
}
function aplicarLayoutSalvo(l) {
  const p = S.p;
  p.camadas = JSON.parse(JSON.stringify(l.camadas));
  p.camadas.filter(c => c.tipo === 'texto').forEach(c => { c.texto = novoTitulo().texto; medirTitulo(c); });
  Object.assign(p.legenda, l.legenda, { offset: 0 });
  p.legenda.blocos = agrupar(S.d.palavras, p.legenda);
  p.fundo = l.fundo; p.preset = l.preset; p.divisao = l.divisao || p.divisao; S.sel = null;
  reorganizar();
  pintarPresets(); pintarPainel(); pintarSelecao(); mudou(false);
}
const salvarLayoutStreamer = tentar(async () => {
  const streamer = $('#ed-streamer').value.trim();
  if (!streamer) { $('#ed-streamer').focus(); throw new Error('Escreva o nome do streamer no topo do editor.'); }
  const r = await api('/api/editor/layout-streamer', { streamer, projeto: S.p });
  S.d.regioes = { ...(S.d.regioes || {}), ...S.p.regioes, layout: r.layout }; S.d.streamer = streamer;
  pintarRegioes();
  avisar(`Regiões e layout salvos. Os próximos vídeos de ${streamer} já abrem assim.`);
});
function destacar(seletor) {
  const n = $(seletor); if (!n) return;
  n.classList.remove('pulso'); void n.offsetWidth; n.classList.add('pulso');
  n.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}
const PASSOS = [
  ['Template', 'Escolha a composição. O Vice Cortes Clássico é o padrão, mas qualquer um pode ser personalizado.', () => { S.aba = 'templates'; pintarPainel(); destacar('.ed-lado'); }],
  ['Webcam e gameplay', 'Na fonte original, arraste os retângulos: rosa = webcam, azul = gameplay, laranja = chat.', () => destacar('#ed-caixa-fonte')],
  ['Ajuste na prévia', 'Clique em um elemento para mover e redimensionar. A rodinha do mouse amplia.', () => {
    const c = S.p.camadas.find(x => x.tipo === 'video'); if (c) selecionar(c.id); destacar('#ed-prev');
  }],
  ['Título e legendas', 'Edite o título da faixa, as legendas e os estilos.', () => { const t = S.p.camadas.find(c => c.tipo === 'texto'); if (t) selecionar(t.id); else { S.aba = 'legendas'; pintarPainel(); } destacar('.ed-lado'); }],
  ['Exportar', 'Confira a prévia, escolha a qualidade e gere o MP4.', () => { S.aba = 'exportar'; pintarPainel(); destacar('.ed-lado'); }],
];
function pintarPassos(ativo = 0) {
  $('#ed-passos').replaceChildren(...PASSOS.map(([t, , f], i) => el('button', { className: 'passo', type: 'button', ariaPressed: String(i === ativo), onclick: () => { pintarPassos(i); f(); } }, el('b', { textContent: i + 1 }), t)),
    el('span', { className: 'passo-dica', textContent: PASSOS[ativo][1] }));
}
function miniMapa(mapa) {
  const cores = { j: '#2de2e6', c: '#ff2d95', t: '#ffffff', h: '#ffb347' };
  const t = document.createElement('template');
  t.innerHTML = `<svg viewBox="0 0 9 16" aria-hidden="true"><rect width="9" height="16" fill="#080919"/>${mapa.map(([k, x, y, l, a]) => `<rect x="${x}" y="${y}" width="${l}" height="${a}" fill="${cores[k]}" fill-opacity=".8" stroke="#080919" stroke-width=".25"/>`).join('')}</svg>`;
  return t.content.firstChild;
}
/* Template de outro formato: troca o formato e aplica (o projeto continua). */
function escolherPreset(id) {
  const pr = PRESETS[id];
  if (!serve(pr)) { definirFormato(pr.fmt[0]); avisar(`Formato trocado para ${pr.fmt[0]}: este template só existe em ${pr.fmt.join(', ')}.`); }
  aplicarPreset(id);
}
const fmtsDe = pr => (pr.fmt || ['9:16']).join(' · ');
function botoesPresets() {
  return Object.entries(PRESETS).map(([id, pr]) => {
    const b = el('button', { className: 'preset' + (serve(pr) ? '' : ' fora'), type: 'button', ariaPressed: String(S.p.preset === id), title: `${pr.desc}${serve(pr) ? '' : ` (troca o formato para ${pr.fmt[0]})`}`, onclick: () => escolherPreset(id) });
    b.append(miniMapa(pr.mapa), el('span', { textContent: pr.nome }));
    return b;
  });
}
function controleDivisao() {
  const pr = PRESETS[S.p.preset];
  return pr && pr.dividir ?  [el('label', { className: 'todo' }, `Espaço da webcam: ${Math.round(S.p.divisao * 100)}% · gameplay: ${100 - Math.round(S.p.divisao * 100)}%`,
    el('input', { type: 'range', min: 0.2, max: 0.75, step: 0.01, value: S.p.divisao, oninput: e => {
      S.p.divisao = parseFloat(e.target.value); reorganizar(); pintarSelecao();
      e.target.previousSibling.textContent = `Espaço da webcam: ${Math.round(S.p.divisao * 100)}% · gameplay: ${100 - Math.round(S.p.divisao * 100)}%`;
      clearTimeout(S.tm3); S.tm3 = setTimeout(() => mudou(false), 350);
    } }))] : [];
}
function pintarPresets() {
  const n = $('#ed-presets'); if (n) n.replaceChildren(...botoesPresets());
  const d = $('#ed-divisao'); if (d) d.replaceChildren(...controleDivisao());
  if (S.aba === 'templates' && $('#ed-tpl-aba')) $('#ed-tpl-aba').replaceChildren(...botoesPresets());
}
/* Aba Templates no painel da direita: sempre à mão, sem rolar a coluna da fonte. */
function abaTemplates() {
  S._livre = false;
  const salvos = S.d.templates || [];
  const salvar = tentar(async ev => {
    ev.preventDefault(); const nome = ev.target.nome.value.trim(); if (!nome) return;
    segs(); S.d.templates = (await api('/api/editor/template', { nome, projeto: S.p })).templates; avisar(`Template “${nome}” salvo.`); pintarPainel();
  });
  return [
    el('div', { id: 'ed-tpl-aba', className: 'presets presets-aba' }, ...botoesPresets()),
    el('p', { className: 'dica', style: 'margin:0', textContent: `Formato atual: ${S.p.formato}. Templates apagados são de outro formato: ao clicar, o formato muda junto.` }),
    el('div', { className: 'grupo' }, ...controleDivisao()),
    el('div', { className: 'ferramentas', style: 'margin:0' },
      el('button', { className: 'btn leve mini', type: 'button', textContent: 'Ver todos com descrição', onclick: () => escolherTemplate(S.p.preset) }),
      el('button', { className: 'btn leve mini', type: 'button', textContent: 'Salvar para este streamer', onclick: salvarLayoutStreamer })),
    el('div', { className: 'sec', textContent: 'Meus templates' }),
    el('form', { className: 'grupo', style: 'grid-template-columns:minmax(0,1fr) auto;align-items:end', onsubmit: salvar },
      el('label', {}, 'Salvar a composição atual como template', el('input', { name: 'nome', placeholder: 'Nome do template', autocomplete: 'off', maxLength: 40 })),
      el('button', { className: 'btn leve mini', style: 'height:31px', type: 'submit', textContent: 'Salvar' })),
    ...(salvos.length ? salvos.map(t => el('div', { className: 'camada' },
      el('span', { className: 'tipo-camada', textContent: t.layout.formato || '9:16' }), el('span', { className: 'nome', textContent: t.nome }),
      el('button', { className: 'btn leve mini', type: 'button', textContent: 'Aplicar', onclick: () => {
        if (t.layout.formato && t.layout.formato !== S.p.formato) definirFormato(t.layout.formato, false);
        if (t.layout.cor) S.p.cor = { ...S.p.cor, ...t.layout.cor };
        aplicarLayoutSalvo(t.layout); avisar(`Template “${t.nome}” aplicado.`);
      } }),
      el('button', { className: 'ico', type: 'button', title: 'Apagar template', textContent: '×', onclick: tentar(async () => {
        if (!confirm(`Apagar o template “${t.nome}”?`)) return;
        S.d.templates = (await api('/api/editor/template', { nome: t.nome })).templates; pintarPainel();
      }) })))
      : [el('p', { className: 'dica', style: 'margin:0', textContent: 'Nenhum template salvo ainda.' })]),
  ];
}
function escolherTemplate(recomendado) {
  const d = el('dialog', { className: 'tpl-dlg' });
  const temCam = !!S.p.regioes.webcam, temChat = (S.d.chat || []).length > 0 || !!S.p.regioes.chat;
  d.append(el('div', { className: 'tpl-topo' }, el('h2', { className: 'tit', textContent: 'Escolha o template' }),
    el('p', { className: 'dica', style: 'margin:0', textContent: temCam ? 'Webcam encontrada na fonte. Tudo pode ser ajustado depois.' : 'Nenhuma webcam detectada. Nos templates com câmera você marca a região à mão.' })),
  el('div', { className: 'tpl-grade' }, ...Object.entries(PRESETS).map(([id, pr]) => {
    const aviso = !serve(pr) ? `Só em ${fmtsDe(pr)}: troca o formato` : pr.chat && !temChat ? 'Sem chat nesta fonte' : pr.cam && !temCam ? 'Marque a webcam' : '';
    const b = el('button', { className: 'tpl' + (id === recomendado ? ' recomendado' : ''), type: 'button', onclick: () => { d.close(); escolherPreset(id); pintarPassos(1); } },
      miniMapa(pr.mapa), el('b', { textContent: pr.nome }), el('span', { textContent: pr.desc }), aviso ? el('small', { textContent: aviso }) : null,
      id === recomendado ? el('i', { textContent: 'Recomendado' }) : null);
    return b;
  })),
  el('div', { className: 'topo-linha', style: 'padding:0 16px 14px' }, el('span'), el('button', { className: 'btn leve mini', type: 'button', textContent: 'Fechar', onclick: () => d.close() })));
  d.addEventListener('close', () => d.remove());
  document.body.append(d); d.showModal();
}

/* ---------- seleção na prévia ---------- */
function caixaDe(id) {
  if (id === '__leg') { const L = S.p.legenda; return { x: L.x - (W - 140) / 2, y: L.y - L.tamanho * 0.8, w: W - 140, h: L.tamanho * 1.6 }; }
  const c = S.p.camadas.find(x => x.id === id);
  if (!c) return null;
  return c.tipo === 'texto' ? { x: c.x - c.caixa.w / 2, y: c.y - c.caixa.h / 2, w: c.caixa.w, h: c.caixa.h } : c.caixa;
}
function pintarSelecao() {
  const n = $('#ed-sel'); if (!n) return;
  const b = S.sel && caixaDe(S.sel);
  n.hidden = !b;
  if (!b) return;
  // Camadas maiores que a tela continuam com as alças ao alcance do mouse.
  const x = limitar(b.x, 0, W - 40), y = limitar(b.y, 0, H - 40), l = Math.max(40, Math.min(b.x + b.w, W) - x), a = Math.max(40, Math.min(b.y + b.h, H) - y);
  n.style.cssText = `left:${x / W * 100}%;top:${y / H * 100}%;width:${l / W * 100}%;height:${a / H * 100}%`;
}
function selecionar(id) { S.sel = id; pintarSelecao(); if (id) S.aba = id === '__leg' ? 'legendas' : 'camadas'; pintarPainel(); pintarRegioes(); }
function pontoPrev(ev) { const r = $('#ed-prev').getBoundingClientRect(); return { x: (ev.clientX - r.left) / r.width * W, y: (ev.clientY - r.top) / r.height * H }; }
function escolherEm(pt) {
  const dentro = b => b && pt.x >= b.x && pt.x <= b.x + b.w && pt.y >= b.y && pt.y <= b.y + b.h;
  if (S.p.legenda.ativa && dentro(caixaDe('__leg'))) return '__leg';
  for (const tipo of ['texto', 'chat', 'imagem', 'video']) for (const c of [...S.p.camadas].reverse()) if (c.tipo === tipo && c.visivel && dentro(caixaDe(c.id))) return c.id;
  return null;
}
function guias(xs, ys) {
  const wrap = $('#ed-prev'); wrap.querySelectorAll('.guia').forEach(n => n.remove());
  xs.forEach(v => wrap.append(el('i', { className: 'guia v', style: `left:${v / W * 100}%` })));
  ys.forEach(v => wrap.append(el('i', { className: 'guia h', style: `top:${v / H * 100}%` })));
}
function imantar(v, tam, alvos) {
  for (const a of alvos) for (const [o, d] of [[0, v], [tam / 2, v + tam / 2], [tam, v + tam]]) if (Math.abs(d - a) < 14) return { v: a - o, g: a };
  return { v, g: null };
}
function moverSel(ev) {
  const id = S.sel, pt0 = pontoPrev(ev);
  if (id === '__leg') {
    const L = S.p.legenda, y0 = L.y, x0 = L.x;
    arrastar(ev, e => {
      const p = pontoPrev(e), mx = imantar(x0 + p.x - pt0.x, 0, [W / 2]);
      L.y = Math.round(limitar(y0 + p.y - pt0.y, 40, H - 40)); L.x = Math.round(limitar(mx.v, 120, W - 120));
      guias(mx.g === null ? [] : [mx.g], []); S.sujo = true; pintarSelecao();
    }, () => { guias([], []); mudou(false); });
    return;
  }
  const c = S.p.camadas.find(x => x.id === id);
  let moveu = false;
  const mexeu = e => { const p = pontoPrev(e); if (Math.abs(p.x - pt0.x) + Math.abs(p.y - pt0.y) > 3) moveu = true; return moveu; };
  if (c.tipo === 'texto') {
    const x0 = c.x, y0 = c.y;
    arrastar(ev, e => {
      if (!mexeu(e)) return;
      const p = pontoPrev(e), my = imantar(y0 - c.caixa.h / 2 + p.y - pt0.y, c.caixa.h, [0, H / 2, H]);
      c.x = c.faixa ? W / 2 : Math.round(x0 + p.x - pt0.x); c.y = Math.round(my.v + c.caixa.h / 2);
      guias([], my.g === null ? [] : [my.g]); S.sujo = true; pintarSelecao();
    }, () => { guias([], []); if (moveu) mudou(); });
    return;
  }
  const b0 = { ...c.caixa }, outros = S.p.camadas.filter(o => o.tipo !== 'texto' && o !== c && o.visivel);
  const alvosX = [0, W / 2, W, ...outros.flatMap(o => [o.caixa.x, o.caixa.x + o.caixa.w])], alvosY = [0, H / 2, H, ...outros.flatMap(o => [o.caixa.y, o.caixa.y + o.caixa.h])];
  arrastar(ev, e => {
    if (!mexeu(e)) return;
    const p = pontoPrev(e), mx = imantar(b0.x + p.x - pt0.x, b0.w, alvosX), my = imantar(b0.y + p.y - pt0.y, b0.h, alvosY);
    c.caixa.x = Math.round(mx.v); c.caixa.y = Math.round(my.v);
    guias(mx.g === null ? [] : [mx.g], my.g === null ? [] : [my.g]); S.sujo = true; pintarSelecao();
  }, () => { guias([], []); if (moveu) { mudou(); pintarPainel(); } });
}
function redimensionarSel(ev, a) {
  const id = S.sel, pt0 = pontoPrev(ev);
  if (id === '__leg') {
    const L = S.p.legenda, t0 = L.tamanho;
    arrastar(ev, e => { L.tamanho = Math.round(limitar(t0 * (1 + (a.includes('n') ? pt0.y - pontoPrev(e).y : pontoPrev(e).y - pt0.y) / 200), 24, 200)); reQuebrar(); S.sujo = true; pintarSelecao(); }, () => { mudou(false); pintarPainel(); });
    return;
  }
  const c = S.p.camadas.find(x => x.id === id);
  if (c.tipo === 'texto') {
    const t0 = c.tamanho, d0 = Math.hypot(pt0.x - c.x, pt0.y - c.y) || 1;
    arrastar(ev, e => { const p = pontoPrev(e); c.tamanho = Math.round(limitar(t0 * Math.hypot(p.x - c.x, p.y - c.y) / d0, 16, 260)); medirTitulo(c); S.sujo = true; pintarSelecao(); }, () => { mudou(); pintarPainel(); });
    return;
  }
  const b0 = { ...c.caixa }, razao = b0.w / b0.h;
  arrastar(ev, e => {
    const p = pontoPrev(e), dx = p.x - pt0.x, dy = p.y - pt0.y;
    let x = b0.x, y = b0.y, w = b0.w, h = b0.h;
    if (a.includes('w')) { w = Math.max(80, b0.w - dx); x = b0.x + b0.w - w; } else w = Math.max(80, b0.w + dx);
    if (a.includes('n')) { h = Math.max(80, b0.h - dy); y = b0.y + b0.h - h; } else h = Math.max(80, b0.h + dy);
    if (e.shiftKey) { h = w / razao; if (a.includes('n')) y = b0.y + b0.h - h; }
    c.caixa = { x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h) };
    S.sujo = true; pintarSelecao();
  }, () => { mudou(); pintarPainel(); });
}

/* ---------- histórico e salvamento ---------- */
function mudou(virouLivre = true) {
  if (virouLivre && S.p.preset !== 'livre') { S.p.preset = 'livre'; pintarPresets(); }
  S.sujo = true; segs(); S.p.volume = S.p.audio.original.volume;
  const foto = JSON.stringify(S.p);
  if (S.hist.at(-1) !== foto) { S.hist.push(foto); if (S.hist.length > 60) S.hist.shift(); }
  pintarTimeline();
  const n = $('#ed-salvo'); if (n) n.textContent = 'Salvando...';
  clearTimeout(S.timer); S.timer = setTimeout(salvar, 900);
}
async function salvar() {
  clearTimeout(S.timer);
  try {
    await api('/api/editor/salvar', { corte: S.id, projeto: S.p, streamer: $('#ed-streamer')?.value || '' });
    const n = $('#ed-salvo'); if (n) n.textContent = 'Salvo';
  } catch (e) { const n = $('#ed-salvo'); if (n) n.textContent = 'Não salvou'; avisar(e.message, true); }
}
function desfazer() {
  if (S.hist.length < 2) return;
  S.hist.pop();
  S.p = JSON.parse(S.hist.at(-1)); selSeg(S.seg); S.fx = null;
  if (S.sel && S.sel !== '__leg' && !S.p.camadas.some(c => c.id === S.sel)) S.sel = null;
  pintarRegioes(); pintarPresets(); pintarPainel(); pintarSelecao(); pintarTimeline(); S.sujo = true;
  clearTimeout(S.timer); S.timer = setTimeout(salvar, 900);
}

/* ---------- campos ---------- */
const aoEditar = (efeito) => { if (efeito) efeito(); S.sujo = true; pintarSelecao(); clearTimeout(S.tm2); S.tm2 = setTimeout(() => mudou(S._livre !== false), 350); };
function campoNum(rot, o, k, { min = -9999, max = 9999, passo = 1, efeito, classe = '' } = {}) {
  return el('label', { className: classe }, rot, el('input', { type: 'number', value: Math.round(o[k] * 100) / 100, min, max, step: passo, oninput: e => { const v = parseFloat(e.target.value); if (!isNaN(v)) { o[k] = limitar(v, min, max); aoEditar(efeito); } } }));
}
const campoCor = (rot, o, k, efeito) => el('label', {}, rot, el('input', { type: 'color', value: o[k], oninput: e => { o[k] = e.target.value.toUpperCase(); aoEditar(efeito); } }));
const campoFaixa = (rot, o, k, min, max, passo, efeito) => el('label', { className: 'todo' }, rot, el('input', { type: 'range', min, max, step: passo, value: o[k], oninput: e => { o[k] = parseFloat(e.target.value); aoEditar(efeito); } }));
const campoSel = (rot, o, k, opcoes, efeito) => el('label', {}, rot, el('select', { onchange: e => { o[k] = e.target.value; aoEditar(efeito); } }, ...opcoes.map(([v, t]) => el('option', { value: v, textContent: t, selected: v === o[k] }))));
const campoCheck = (rot, o, k, efeito) => el('label', { className: 'marcar todo' }, el('input', { type: 'checkbox', checked: !!o[k], onchange: e => { o[k] = e.target.checked; aoEditar(efeito); } }), rot);
const opFontes = FONTES.map(f => [f, f]);

/* ---------- painel lateral ---------- */
function pintarPainel() {
  const abas = [['templates', 'Templates'], ['camadas', 'Camadas'], ['legendas', 'Legendas'], ['efeitos', 'Efeitos'], ['audio', 'Áudio'], ['exportar', 'Exportar']];
  $('#ed-abas').replaceChildren(...abas.map(([id, t]) => el('button', { className: 'aba', type: 'button', role: 'tab', ariaSelected: String(S.aba === id), textContent: t, onclick: () => { S.aba = id; pintarPainel(); } })));
  $('#ed-aba').replaceChildren(...({ templates: abaTemplates, camadas: abaCamadas, legendas: abaLegendas, efeitos: () => UI().abaEfeitos(), audio: () => UI().abaAudio(), checkup: () => UI().abaCheckup(), exportar: abaExportar }[S.aba])().filter(Boolean));
}
function abaCamadas() {
  const p = S.p;
  S._livre = true;
  const add = (t, f, titulo) => el('button', { className: 'btn leve mini', type: 'button', textContent: t, title: titulo || t, onclick: f });
  const inserir = c => { p.camadas.push(c); S.sel = c.id; pintarPainel(); pintarSelecao(); pintarRegioes(); mudou(); };
  const novaVideo = (regiao, nome) => () => {
    if (regiao === 'webcam' && !p.regioes.webcam) { msgFonte('Marque a webcam na fonte antes de adicionar esta camada.'); avisar('Nenhuma webcam marcada neste vídeo.', true); return; }
    inserir(vid(`v${Date.now() % 100000}`, nome, regiao, 240, 500, 600, 450, regiao === 'propria' ? { recorte: { x: 0.3, y: 0.3, w: 0.4, h: 0.4 } } : {}));
  };
  const novaImagem = () => {
    const entrada = el('input', { type: 'file', accept: 'image/png,image/jpeg,image/webp,image/gif' });
    entrada.onchange = tentar(async () => {
      const arq = entrada.files[0]; if (!arq) return;
      const dados = await new Promise((ok, falha) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = falha; r.readAsDataURL(arq); });
      const g = await api('/api/grafico', { dados });
      const i = imagem(g.arquivo); await new Promise(ok => { if (i.complete && i.naturalWidth) ok(); else { i.onload = () => { S.sujo = true; ok(); }; i.onerror = ok; } });
      const w = Math.min(500, i.naturalWidth || 500), h = Math.round(w * (i.naturalHeight || 1) / (i.naturalWidth || 1));
      inserir({ id: `i${Date.now() % 100000}`, nome: arq.name.slice(0, 40), tipo: 'imagem', arquivo: g.arquivo, caixa: { x: Math.round((W - w) / 2), y: 200, w, h }, opacidade: 1, visivel: true });
    });
    entrada.click();
  };
  const novoChat = () => {
    if ((S.d.chat || []).length) { inserir({ ...chatCol(700, 300, 360, 900), id: `h${Date.now() % 100000}` }); return; }
    if (p.regioes.chat) { inserir(vid(`v${Date.now() % 100000}`, 'Chat do vídeo', 'chat', 700, 300, 360, 900)); return; }
    msgFonte('Esta fonte não tem chat gravado. Se o chat aparece na transmissão, clique em Marcar chat na fonte original.');
    avisar('Chat não disponível nesta fonte. Nada foi inventado.', true);
  };
  const lista = [...p.camadas].reverse().map(c => {
    const i = p.camadas.indexOf(c);
    const trocar = d => ev => { ev.stopPropagation(); const j = i + d; if (j >= 0 && j < p.camadas.length) { [p.camadas[i], p.camadas[j]] = [p.camadas[j], p.camadas[i]]; pintarPainel(); mudou(); } };
    const tipo = { video: c.regiao === 'webcam' ? 'Webcam' : c.regiao === 'propria' ? 'Recorte' : c.regiao === 'chat' ? 'Chat' : 'Gameplay', texto: 'Título', imagem: 'Imagem', chat: 'Chat' }[c.tipo];
    return el('div', { className: 'camada', role: 'option', ariaSelected: String(S.sel === c.id), onclick: () => selecionar(c.id) },
      el('button', { className: 'ico', type: 'button', title: c.visivel ? 'Ocultar' : 'Mostrar', textContent: c.visivel ? '●' : '○', onclick: ev => { ev.stopPropagation(); c.visivel = !c.visivel; if (c.tipo === 'texto') reorganizar(); pintarPainel(); mudou(false); } }),
      el('span', { className: 'tipo-camada', textContent: tipo }),
      el('span', { className: 'nome', textContent: c.tipo === 'texto' ? (c.texto.split('\n')[0] || 'Título') : (c.nome || tipo) }),
      el('button', { className: 'ico', type: 'button', title: 'Para frente', textContent: '↑', onclick: trocar(1) }), el('button', { className: 'ico', type: 'button', title: 'Para trás', textContent: '↓', onclick: trocar(-1) }),
      el('button', { className: 'ico', type: 'button', title: 'Remover', textContent: '×', onclick: ev => { ev.stopPropagation(); p.camadas.splice(i, 1); if (S.sel === c.id) S.sel = null; pintarPainel(); pintarSelecao(); pintarRegioes(); mudou(); } }));
  });
  const itens = [el('div', { className: 'ferramentas', style: 'margin:0' }, add('+ Gameplay', novaVideo('gameplay', 'Gameplay')), add('+ Webcam', novaVideo('webcam', 'Webcam')),
    add('+ Recorte', novaVideo('propria', 'Recorte'), 'Outra camada da mesma fonte com recorte próprio'),
    add('+ Título', () => { const t = novoTitulo('transparente'); Object.assign(t, { faixa: false, altMin: 0, raio: 14, y: H / 2 }); medirTitulo(t); inserir(t); }),
    add('+ Chat', novoChat), add('+ Imagem', novaImagem, 'Logo, selo ou elemento gráfico do seu PC')),
    el('div', { className: 'lista', role: 'listbox', style: 'gap:4px' }, ...lista),
    el('p', { className: 'dica', style: 'margin:0', textContent: 'Títulos, chat e legendas ficam sempre por cima dos vídeos e imagens.' })];
  const c = p.camadas.find(x => x.id === S.sel);
  if (c) itens.push({ video: propsVideo, texto: propsTexto, imagem: propsImagem, chat: propsChat }[c.tipo](c));
  else itens.push(el('p', { className: 'dica', style: 'margin:0', textContent: 'Clique em um elemento da prévia para mover, redimensionar e ajustar.' }));
  return itens;
}
function caixaCampos(c, minimo = 40) {
  return el('div', { className: 'grupo q todo' }, campoNum('X', c.caixa, 'x'), campoNum('Y', c.caixa, 'y'), campoNum('Largura', c.caixa, 'w', { min: minimo, max: 3240 }), campoNum('Altura', c.caixa, 'h', { min: minimo, max: 5760 }));
}
function propsVideo(c) {
  const p = S.p;
  const trocaRegiao = () => { if (c.regiao === 'propria' && !c.recorte) c.recorte = { ...(p.regioes.gameplay || { x: 0, y: 0, w: 1, h: 1 }) }; pintarRegioes(); };
  return el('div', { className: 'grupo' }, el('div', { className: 'sec todo', textContent: c.nome }),
    campoSel('Recorte da fonte', c, 'regiao', [['gameplay', 'Gameplay'], ['webcam', 'Webcam'], ['chat', 'Chat do vídeo'], ['propria', 'Recorte próprio']], trocaRegiao),
    el('div', { className: 'ferramentas', style: 'margin:0;align-self:end' },
      el('button', { className: 'btn leve mini', type: 'button', textContent: 'Tela cheia', onclick: () => { c.caixa = { x: 0, y: 0, w: W, h: H }; pintarSelecao(); pintarPainel(); mudou(); } }),
      el('button', { className: 'btn leve mini', type: 'button', textContent: 'Duplicar', title: 'Outra camada da mesma fonte, com recorte próprio', onclick: () => {
        const r = regiaoDe(c) || { x: 0, y: 0, w: 1, h: 1 };
        const n = { ...JSON.parse(JSON.stringify(c)), id: `v${Date.now() % 100000}`, nome: `${c.nome} (cópia)`, regiao: 'propria', recorte: { ...r } };
        n.caixa.x += 40; n.caixa.y += 40;
        p.camadas.push(n); S.sel = n.id; pintarPainel(); pintarSelecao(); pintarRegioes(); mudou();
        msgFonte('Cópia criada com recorte próprio: ajuste o retângulo amarelo na fonte original.');
      } })),
    c.regiao === 'propria' ? el('p', { className: 'dica todo', style: 'margin:0', textContent: 'O recorte desta camada é o retângulo amarelo na fonte original.' }) : null,
    caixaCampos(c),
    campoFaixa('Ampliar', c, 'zoom', 1, 6, 0.01), campoFaixa('Mover enquadramento na horizontal', c, 'panX', -1, 1, 0.01), campoFaixa('Mover enquadramento na vertical', c, 'panY', -1, 1, 0.01),
    campoNum('Borda', c, 'borda', { min: 0, max: 40 }), campoCor('Cor da borda', c, 'bordaCor'),
    resolucao(c));
}
/* Mostra quanto a fonte está sendo ampliada: a nitidez depende da resolução original. */
function resolucao(c) {
  const r = regiaoDe(c), v = S.video;
  if (!r || !v || !v.videoWidth) return null;
  const [, , l] = efetivo(r, c.caixa, c.zoom, c.panX, c.panY, v.videoWidth, v.videoHeight), f = c.caixa.w / l;
  return el('p', { className: 'dica todo', style: `margin:0;color:${f > 2.5 ? 'var(--sol)' : 'var(--suave)'}`, textContent: `Ampliação ${f.toFixed(1)}x sobre a fonte (${l}px de largura)${f > 2.5 ? ': pode perder nitidez' : ''}.` });
}
function propsTexto(c) {
  S._livre = false;
  const m = () => { medirTitulo(c); reorganizar(); };
  const faixas = el('div', { className: 'ferramentas todo', style: 'margin:0' }, el('span', { className: 'dica', style: 'margin:0 4px 0 0;align-self:center', textContent: 'Faixa:' }),
    ...Object.entries(FAIXAS).map(([id, f]) => el('button', { className: 'btn leve mini', type: 'button', textContent: f.nome, onclick: () => { Object.assign(c, estiloFaixa(id)); m(); pintarPainel(); mudou(false); } })));
  return el('div', { className: 'grupo' }, el('div', { className: 'sec todo', textContent: 'Título' }),
    el('label', { className: 'todo' }, 'Texto (quebra automática; Enter força nova linha)', el('textarea', { rows: 3, value: c.texto, oninput: e => { c.texto = e.target.value; aoEditar(m); } })),
    faixas,
    campoSel('Fonte', c, 'fonte', opFontes, m), campoNum('Tamanho', c, 'tamanho', { min: 16, max: 260, efeito: m }),
    campoCor('Cor do texto', c, 'cor'), campoCor('Contorno do texto', c, 'contorno'), campoNum('Espessura do contorno', c, 'espessura', { min: 0, max: 24 }), campoNum('Sombra', c, 'sombra', { min: 0, max: 20 }),
    campoCheck('Fundo colorido', c, 'fundoAtivo'), campoCheck('Faixa na largura toda', c, 'faixa', m), campoCor('Cor do fundo', c, 'fundoCor'), campoNum('Arredondar', c, 'raio', { min: 0, max: 80 }),
    campoFaixa(`Altura mínima da faixa (${Math.round(c.altMin)} px)`, c, 'altMin', 0, 600, 2, m),
    campoFaixa('Opacidade do fundo', c, 'fundoAlfa', 0, 1, 0.01),
    campoNum('Linha da faixa (px)', c, 'bordaFaixa', { min: 0, max: 30 }), campoCor('Cor da linha', c, 'bordaFaixaCor'),
    c.faixa ? null : campoNum('Posição X', c, 'x', { min: 0, max: W }), campoNum('Posição Y (centro)', c, 'y', { min: 0, max: H, efeito: () => { if (S.p.preset !== 'livre') { S.p.preset = 'livre'; pintarPresets(); } } }));
}
function propsImagem(c) {
  return el('div', { className: 'grupo' }, el('div', { className: 'sec todo', textContent: `Imagem · ${c.nome}` }), caixaCampos(c, 10),
    campoFaixa('Opacidade', c, 'opacidade', 0, 1, 0.01),
    el('p', { className: 'dica todo', style: 'margin:0', textContent: 'Shift mantém a proporção ao redimensionar.' }));
}
function propsChat(c) {
  S._livre = false;
  const limpar = () => { S.chatChave = ''; };
  const n = (S.d.chat || []).length;
  return el('div', { className: 'grupo' }, el('div', { className: 'sec todo', textContent: 'Chat' }),
    el('p', { className: 'dica todo', style: 'margin:0', textContent: n ? `${n} mensagens reais (${S.d.chat_origem}), sincronizadas com o vídeo.` : 'Sem mensagens nesta fonte.' }),
    caixaCampos(c, 80), campoNum('Tamanho da letra', c, 'tamanho', { min: 14, max: 80, efeito: limpar }),
    campoCor('Cor do texto', c, 'cor'), campoCor('Contorno', c, 'contorno'), campoNum('Espessura', c, 'espessura', { min: 0, max: 12 }),
    campoCor('Cor do fundo', c, 'fundoCor'), campoFaixa('Opacidade do fundo', c, 'fundoAlfa', 0, 1, 0.01));
}
function textoBloco(b) { return b.map(w => (w.d ? `*${w.p}*` : w.p)).join(' '); }
function editarBloco(i, texto) {
  const L = S.p.legenda, b = L.blocos[i], toks = texto.trim().split(/\s+/).filter(Boolean);
  if (!toks.length) return;
  const ini = b[0].i, fim = b.at(-1).f, total = toks.reduce((s, t) => s + t.length, 0);
  let t = ini;
  L.blocos[i] = toks.map(tok => {
    const d = /^\*.+\*$/.test(tok), p = tok.replace(/^\*|\*$/g, ''), dur = (fim - ini) * tok.length / total;
    const w = { p, i: Math.round(t * 100) / 100, f: Math.round((t + dur) * 100) / 100, d, q: false };
    t += dur; return w;
  });
  quebrar(L.blocos[i], L);
}
function abaLegendas() {
  const L = S.p.legenda, reagrupar = () => { L.blocos = agrupar(L.blocos.flat(), L); pintarListaLeg(); };
  const todos = [...ESTILOS, ...(S.d.estilos || [])];
  const aplicarEstilo = e => { const { blocos, x, y, offset, ativa, maxPalavras, ...r } = e.estilo; Object.assign(L, r); reQuebrar(); pintarPainel(); mudou(false); };
  S._livre = false;
  const rotuloSinc = () => `Sincronia (${L.offset >= 0 ? '+' : ''}${L.offset.toFixed(2)} s)`;
  const sincronia = campoFaixa(rotuloSinc(), L, 'offset', -2, 2, 0.05, () => { sincronia.firstChild.textContent = rotuloSinc(); });
  return [
    el('label', { className: 'marcar' }, el('input', { type: 'checkbox', checked: L.ativa, onchange: e => { L.ativa = e.target.checked; S.sujo = true; mudou(false); } }), 'Mostrar legendas'),
    el('div', { className: 'ferramentas', style: 'margin:0' }, ...todos.map(e => el('button', { className: 'btn leve mini', type: 'button', textContent: e.nome, onclick: () => aplicarEstilo(e) }))),
    el('div', { className: 'grupo' },
      campoSel('Fonte', L, 'fonte', opFontes, reQuebrar), campoNum('Tamanho', L, 'tamanho', { min: 24, max: 200, efeito: reQuebrar }),
      campoCor('Cor do texto', L, 'cor'), campoCor('Destaque', L, 'destaque'), campoCor('Contorno', L, 'contorno'), campoNum('Espessura', L, 'espessura', { min: 0, max: 24 }),
      campoNum('Sombra', L, 'sombra', { min: 0, max: 20 }), campoNum('Palavras por bloco', L, 'maxPalavras', { min: 1, max: 8, efeito: reagrupar }),
      campoSel('Destacar', L, 'modo', [['atual', 'Palavra falada'], ['marcadas', 'Palavras marcadas'], ['nenhum', 'Nada']]),
      campoNum('Posição horizontal', L, 'x', { min: 120, max: W - 120 }), campoNum('Posição vertical', L, 'y', { min: 40, max: H - 40 }), campoCheck('Letras maiúsculas', L, 'maiusculas', reQuebrar),
      sincronia),
    el('form', { className: 'grupo', style: 'grid-template-columns:minmax(0,1fr) auto;align-items:end', onsubmit: tentar(async e => {
      e.preventDefault(); const nome = e.target.nome.value.trim(); if (!nome) return;
      S.d.estilos = (await api('/api/editor/estilo', { nome, estilo: L })).estilos; avisar('Estilo salvo.'); pintarPainel();
    }) }, el('label', {}, 'Salvar este estilo', el('input', { name: 'nome', placeholder: 'Nome do estilo', autocomplete: 'off' })), el('button', { className: 'btn leve mini', style: 'height:31px', type: 'submit', textContent: 'Salvar' })),
    el('div', { className: 'sec', textContent: 'Texto das legendas' }),
    el('p', { className: 'dica', style: 'margin:0', textContent: 'Use *palavra* para marcar em destaque.' }),
    el('div', { id: 'ed-lista-leg', className: 'lista-leg' }),
    el('button', { className: 'btn leve mini', type: 'button', textContent: 'Transcrever este trecho de novo', onclick: tentar(async ev => {
      ev.target.disabled = true; ev.target.textContent = 'Transcrevendo...';
      try {
        const t = await api('/api/editor/transcrever', { corte: S.id, modelo: 'medium' }), r = await aguardarTarefa(t.id);
        S.d.palavras = r.palavras; L.blocos = agrupar(r.palavras, L); pintarPainel(); mudou(false); avisar('Legendas atualizadas.');
      } finally { ev.target.disabled = false; ev.target.textContent = 'Transcrever este trecho de novo'; }
    }) }),
  ].concat(setTimeout(pintarListaLeg) && []);
}
function pintarListaLeg() {
  const n = $('#ed-lista-leg'); if (!n) return;
  const L = S.p.legenda;
  const linhas = [];
  L.blocos.forEach((b, i) => {
    if (!Fx.intervalosNaSaida(segs(), b[0].i + L.offset, b.at(-1).f + L.offset + 0.15).length) return;
    const mover = d => () => { b.forEach(w => { w.i = Math.round((w.i + d) * 100) / 100; w.f = Math.round((w.f + d) * 100) / 100; }); S.sujo = true; mudou(false); };
    linhas.push(el('div', { className: 'bloco-leg' }, el('time', { textContent: fmt(b[0].i), title: 'Ir para este ponto', onclick: () => { S.video.currentTime = b[0].i + L.offset; S.sujo = true; } }),
      el('input', { value: textoBloco(b), ariaLabel: 'Texto da legenda', onchange: e => { editarBloco(i, e.target.value); S.sujo = true; mudou(false); } }),
      el('span', { className: 'ns' }, el('button', { className: 'ico', type: 'button', title: 'Adiantar 0,1 s', textContent: '−', onclick: mover(-0.1) }), el('button', { className: 'ico', type: 'button', title: 'Atrasar 0,1 s', textContent: '+', onclick: mover(0.1) }))));
  });
  n.replaceChildren(...(linhas.length ? linhas : [el('p', { className: 'dica', style: 'margin:0', textContent: 'Não há falas transcritas neste trecho. Clique em Transcrever.' })]));
}
function abaExportar() {
  const p = S.p;
  S._livre = false;
  const lista = (S.d.exportados || []).slice().reverse();
  const dur = durSaida();
  const estimar = () => `Saída: MP4 ${W}x${H} (${p.formato}), H.264 + AAC, ${fmt(dur)} de duração. Tamanho estimado: até ${((QUALIDADE[p.qualidade][1] + 192e3) * dur / 8 / 1048576).toFixed(0)} MB.`;
  const info = el('p', { className: 'dica', style: 'margin:0', textContent: estimar() });
  const fonte = S.d.fonte;
  return [
    el('div', { className: 'grupo' },
      campoSel('Qualidade', p, 'qualidade', Object.entries(QUALIDADE).map(([k, [t]]) => [k, t]), () => { info.textContent = estimar(); }),
      campoSel('Quadros por segundo', { get fps() { return String(p.fps); }, set fps(v) { p.fps = Number(v); } }, 'fps', [['30', '30 fps'], ['60', '60 fps']]),
      campoCor('Cor de fundo', p, 'fundo')),
    info,
    el('p', { className: 'dica', style: 'margin:0', textContent: `Fonte: ${fonte.w}x${fonte.h} a ${Math.round(fonte.fps)} fps, ${fonte.original ? 'original sem legenda' : 'corte já renderizado (qualidade menor)'}. O vídeo é renderizado uma vez só, direto da fonte, com escala Lanczos.` }),
    el('button', { id: 'ed-exportar2', className: 'btn', type: 'button', textContent: 'Renderizar vídeo', onclick: exportar }),
    el('div', { className: 'sec', textContent: 'Vídeos exportados' }),
    ...(lista.length ? lista.map(e => el('div', { className: 'linha-item' }, el('span', { className: 'nome', textContent: e.arquivo, title: e.arquivo }),
      el('button', { className: 'btn leve mini', type: 'button', textContent: 'Ver', onclick: () => mostrarPronto(e) }),
      e.fonte_url ? el('button', { className: 'btn leve mini', type: 'button', textContent: 'Comparar', onclick: () => compararReel(e) }) : null,
      el('a', { className: 'btn leve mini', href: e.url, download: e.arquivo, textContent: 'Baixar' })))
      : [el('p', { className: 'dica', style: 'margin:0', textContent: 'Nenhum vídeo exportado deste corte.' })]),
  ];
}
function chatParaExportar() {
  const c = S.p.camadas.find(x => x.tipo === 'chat' && x.visivel);
  if (!c) return [];
  const a = Math.min(...segs().map(g => g.ini)), b = Math.max(...segs().map(g => g.fim));
  return linhasChat(c).filter(m => m.t <= b && m.t >= a - 120);
}
const exportar = tentar(async () => {
  if (durSaida() < 1) throw new Error('O corte precisa ter pelo menos 1 segundo.');
  S.video.pause(); segs();
  const botoes = [$('#ed-exportar'), $('#ed-exportar2')].filter(Boolean);
  botoes.forEach(b => { b.disabled = true; b.textContent = 'Na fila...'; });
  try {
    const t = await api('/api/editor/exportar', { corte: S.id, projeto: S.p, streamer: $('#ed-streamer').value, chat: chatParaExportar() });
    const r = await aguardarTarefa(t.id, x => botoes.forEach(b => { b.textContent = x.estado === 'rodando' ? `Renderizando ${Math.round(x.progresso * 100)}%` : 'Na fila...'; }));
    S.d.exportados = [...(S.d.exportados || []), r];
    if (S.aba === 'exportar') pintarPainel();
    mostrarPronto(r);
  } finally { [$('#ed-exportar'), $('#ed-exportar2')].filter(Boolean).forEach(b => { b.disabled = false; b.textContent = b.id === 'ed-exportar' ? 'Exportar' : 'Renderizar vídeo'; }); }
});
function mostrarPronto(e) {
  const d = el('dialog', { className: 'pronto', style: 'width:min(460px,calc(100vw - 32px))' });
  const v = el('video', { src: e.url, controls: true, autoplay: true, playsInline: true });
  const mb = e.bytes ? ` · ${(e.bytes / 1048576).toFixed(1)} MB` : '';
  d.append(v, el('p', { className: 'dica', style: 'margin:8px 12px 0', textContent: `${e.arquivo} · ${e.largura}x${e.altura} · ${Math.round(e.duracao)} s${mb}` }),
    el('div', { className: 'acoes', style: 'padding:12px;grid-template-columns:1fr 1fr 1fr 1fr' },
      el('a', { className: 'btn', href: e.url, download: e.arquivo, textContent: 'Baixar' }),
      e.fonte_url ? el('button', { className: 'btn leve', type: 'button', textContent: 'Comparar', onclick: () => { d.close(); compararReel(e); } }) : null,
      el('button', { className: 'btn leve', type: 'button', textContent: 'Pasta', onclick: tentar(() => api('/api/abrir-pasta', { pasta: e.pasta })) }),
      el('button', { className: 'btn leve', type: 'button', textContent: 'Fechar', onclick: () => d.close() })));
  d.addEventListener('close', () => { v.pause(); d.remove(); });
  document.body.append(d); d.showModal();
}

/* ---------- timeline ---------- */
const xDe = t => t / S.d.fonte.dur * 100;
function pintarTimeline() {
  const c = $('#ed-onda'); if (!c) return;
  const r = c.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
  c.width = Math.round(r.width * dpr); c.height = Math.round(r.height * dpr);
  const g = c.getContext('2d'), l = c.width, a = c.height, meio = a * 0.42;
  const dur = S.d.fonte.dur, Lg = S.p.legenda, lista = segs();
  g.clearRect(0, 0, l, a);
  lista.forEach((s, i) => { g.fillStyle = s.id === S.seg ? 'rgba(255,45,149,.20)' : 'rgba(45,226,230,.16)'; g.fillRect(s.ini / dur * l, 0, (s.fim - s.ini) / dur * l, a); g.fillStyle = '#fff'; g.font = `${11 * dpr}px "Segoe UI"`; if (lista.length > 1) g.fillText(String(i + 1), s.ini / dur * l + 4 * dpr, 12 * dpr); });
  g.fillStyle = '#ff5fb0';
  S.onda.forEach((v, i) => { const x = i / S.onda.length * l, h = Math.max(1, v * a * 0.38); g.fillRect(x, meio - h, Math.max(1, l / S.onda.length - 0.5), h * 2); });
  g.fillStyle = 'rgba(45,226,230,.75)';
  for (const b of Lg.blocos) { const x = (b[0].i + Lg.offset) / dur * l, f = (b.at(-1).f + Lg.offset) / dur * l; g.fillRect(x, a - 9 * dpr, Math.max(2, f - x - 1), 6 * dpr); }
  const um = lista.length === 1;
  $('#ed-fora-a').style.cssText = um ? `left:0;width:${xDe(S.p.inicio)}%` : 'display:none';
  $('#ed-fora-b').style.cssText = um ? `left:${xDe(S.p.fim)}%;right:0` : 'display:none';
  $('#ed-mao-a').style.left = `${xDe(S.p.inicio)}%`;
  $('#ed-mao-b').style.left = `${xDe(S.p.fim)}%`;
  const campo = (id, v) => { const n = $(id); if (n && document.activeElement !== n) n.value = v; };
  campo('#ed-ini', fmt(S.p.inicio)); campo('#ed-fim', fmt(S.p.fim)); campo('#ed-durc', (S.p.fim - S.p.inicio).toFixed(1));
  UI().trilhas();
  atualizarTempo();
}
/* Campos de tempo: início e fim no tempo da fonte (m:ss.d) e duração em segundos. */
function definirTempo(qual, valor) {
  const d = S.d.fonte.dur, p = S.p;
  if (qual === 'dur') { const v = parseFloat(String(valor).replace(',', '.')); if (!(v >= 1)) return; p.fim = Math.min(d, Math.round((p.inicio + v) * 100) / 100); }
  else {
    const t = lerHms(valor); if (t === null) return;
    if (qual === 'ini') p.inicio = Math.round(limitar(t, 0, p.fim - 1) * 100) / 100; else p.fim = Math.round(limitar(t, p.inicio + 1, d) * 100) / 100;
  }
  S.video.currentTime = p.inicio; S.sujo = true; pintarTimeline(); pintarListaLeg(); mudou(false);
  if (S.aba === 'exportar') pintarPainel();
}
function ligarAudio() { UI().som.ligar(); aplicarVolume(); }
function aplicarVolume() {
  UI().som.ganhos();
  const n = $('#ed-vol-txt'); if (n) n.textContent = `${Math.round(S.p.audio.original.volume * 100)}%`;
}
function atualizarTempo() {
  const v = S.video; if (!v || !$('#ed-agulha')) return;
  const pos = tempoSaida();
  $('#ed-agulha').style.left = `${xDe(v.currentTime)}%`;
  $('#ed-t-agora').textContent = pos ? fmt(pos.T) : '—';
  $('#ed-t-total').textContent = fmt(durSaida());
  $('#ed-play').textContent = v.paused ? 'Reproduzir' : 'Pausar';
  UI().agulha(pos ? pos.T : null);
}
function tempoDoPonteiro(ev) { const r = $('#ed-tl').getBoundingClientRect(); return limitar((ev.clientX - r.left) / r.width, 0, 1) * S.d.fonte.dur; }
function ligarTimeline() {
  const tl = $('#ed-tl');
  const ir = e => { const t = tempoDoPonteiro(e), r = Fx.saidaDe(segs(), t); S.tocando = r ? r.i : S.tocando; S.video.currentTime = t; S.sujo = true; };
  tl.onpointerdown = ev => { S.video.pause(); ir(ev); arrastar(ev, ir); };
  $('#ed-mao-a').onpointerdown = ev => arrastar(ev, e => { S.p.inicio = Math.round(limitar(tempoDoPonteiro(e), 0, S.p.fim - 1) * 100) / 100; S.video.currentTime = S.p.inicio; S.sujo = true; pintarTimeline(); }, () => { mudou(false); pintarListaLeg(); });
  $('#ed-mao-b').onpointerdown = ev => arrastar(ev, e => { S.p.fim = Math.round(limitar(tempoDoPonteiro(e), S.p.inicio + 1, S.d.fonte.dur) * 100) / 100; S.video.currentTime = Math.max(S.p.inicio, S.p.fim - 1.5); S.sujo = true; pintarTimeline(); }, () => { mudou(false); pintarListaLeg(); });
}
function tocar() {
  const v = S.video;
  ligarAudio();
  if (v.paused) {
    let pos = tempoSaida();
    if (!pos || pos.T >= durSaida() - 0.05) { irSaida(0); pos = { T: 0, i: 0 }; }
    S.tocando = pos.i; v.playbackRate = segs()[pos.i].vel;
    v.play().then(() => UI().som.tocar(pos.T)).catch(() => {});
  } else v.pause();
  atualizarTempo();
}

/* ---------- montagem ---------- */
function ajustarLayout() {
  const meio = $('#ed-meio'); if (!meio) return;
  if (innerWidth <= 1250) { meio.style.removeProperty('--prevw'); meio.style.gridTemplateColumns = ''; return; }
  const h = meio.clientHeight, w = Math.round(Math.max(200, Math.min(h * W / H, meio.clientWidth - 348 - 320 - 20)));
  meio.style.gridTemplateColumns = `minmax(300px,1fr) ${w}px 348px`;
  pintarTimeline();
}
function montar() {
  const d = S.d;
  $('#tela-editor').replaceChildren(el('div', { className: 'edt' },
    el('header', { className: 'ed-topo' },
      el('button', { className: 'btn leve mini', type: 'button', textContent: 'Meus Cortes', onclick: () => irPara('cortes') }),
      el('h1', { textContent: d.titulo_live, title: d.titulo_live }),
      el('input', { id: 'ed-streamer', className: 'streamer', value: d.streamer, placeholder: 'Streamer', ariaLabel: 'Streamer', onchange: () => mudou(false) }),
      el('select', { id: 'ed-formato', className: 'streamer', style: 'width:150px', title: 'Formato de saída', ariaLabel: 'Formato de saída', onchange: e => definirFormato(e.target.value) },
        ...Object.entries(FORMATOS).map(([k, [w, h, t]]) => el('option', { value: k, textContent: `${k} · ${w}x${h}`, title: t, selected: k === S.p.formato }))),
      el('span', { id: 'ed-salvo', className: 'salvo', textContent: 'Salvo' }),
      el('button', { className: 'btn leve mini', type: 'button', textContent: 'Desfazer', onclick: desfazer }),
      el('button', { id: 'ed-exportar', className: 'btn mini', style: 'height:34px;padding:0 18px', type: 'button', textContent: 'Exportar', onclick: exportar })),
    el('nav', { id: 'ed-passos', className: 'passos-ed', ariaLabel: 'Passos da edição' }),
    el('div', { id: 'ed-meio', className: 'ed-meio' },
      el('div', { className: 'ed-col' },
        el('section', { id: 'ed-caixa-fonte', className: 'card ed-caixa' }, el('div', { className: 'ed-rot' }, el('span', { textContent: 'FONTE ORIGINAL' }), el('b', { id: 'ed-cam-status' })),
          el('div', { id: 'ed-fonte', className: 'fonte-wrap' }, el('video', { id: 'ed-video', src: d.fonte.url, playsInline: true, preload: 'auto' })),
          el('div', { className: 'ferramentas' },
            el('button', { className: 'btn leve mini', type: 'button', textContent: 'Detectar webcam', onclick: detectarWebcam }),
            el('button', { className: 'btn leve mini', type: 'button', textContent: 'Marcar webcam', onclick: () => { S.p.regioes.webcam = S.p.regioes.webcam || { x: 0.7, y: 0.03, w: 0.27, h: 0.3 }; pintarRegioes(); msgFonte('Arraste o retângulo rosa até a câmera.'); mudou(false); } }),
            el('button', { className: 'btn leve mini', type: 'button', textContent: 'Sem webcam', onclick: () => { S.p.regioes.webcam = null; S.p.camadas = S.p.camadas.filter(c => c.regiao !== 'webcam'); if (!S.p.camadas.some(c => c.tipo === 'video')) S.p.camadas.unshift(...PRESETS.jogo_cheio.f()); S.sel = null; pintarRegioes(); pintarPainel(); pintarSelecao(); msgFonte('Este vídeo ficará sem camada de webcam.'); mudou(); } }),
            el('button', { className: 'btn leve mini', type: 'button', textContent: 'Gameplay inteiro', onclick: () => { S.p.regioes.gameplay = { x: 0, y: 0, w: 1, h: 1 }; pintarRegioes(); mudou(false); } }),
            el('button', { className: 'btn leve mini', type: 'button', textContent: S.p.regioes.chat ? 'Sem chat no vídeo' : 'Marcar chat', title: 'Use se o chat aparece dentro da transmissão', onclick: ev => {
              S.p.regioes.chat = S.p.regioes.chat ? null : { x: 0.02, y: 0.3, w: 0.22, h: 0.6 };
              ev.target.textContent = S.p.regioes.chat ? 'Sem chat no vídeo' : 'Marcar chat'; pintarRegioes(); mudou(false);
              if (S.p.regioes.chat) msgFonte('Arraste o retângulo laranja até o chat que aparece na transmissão.');
            } }),
            el('button', { className: 'btn leve mini', type: 'button', textContent: 'Salvar regiões do streamer', onclick: salvarLayoutStreamer })),
          el('p', { id: 'ed-msg', className: 'msg-fonte', textContent: d.fonte.aviso || '' })),
        el('section', { id: 'ed-caixa-layouts', className: 'card ed-caixa' }, el('div', { className: 'ed-rot' }, el('span', { textContent: 'TEMPLATES' }),
          el('span', { className: 'ferramentas', style: 'margin:0' }, el('button', { className: 'btn leve mini', type: 'button', textContent: 'Ver todos', onclick: () => escolherTemplate(S.p.preset) }),
            el('button', { id: 'ed-salvar-layout', className: 'btn leve mini', type: 'button', textContent: 'Salvar para este streamer', onclick: salvarLayoutStreamer }))),
          el('div', { id: 'ed-presets', className: 'presets' }), el('div', { id: 'ed-divisao', className: 'grupo', style: 'margin-top:6px' }))),
      el('div', { className: 'ed-col preview-col' }, el('div', { id: 'ed-prev', className: 'prev-wrap' },
        el('canvas', { id: 'ed-canvas', width: W, height: H }), el('div', { id: 'ed-sel', className: 'selecao', hidden: true }, ...alcas()))),
      el('section', { className: 'card ed-lado' }, el('div', { id: 'ed-abas', className: 'abas', role: 'tablist' }), el('div', { id: 'ed-aba', className: 'aba-corpo' }))),
    el('section', { id: 'ed-tempo', className: 'card ed-tempo' },
      el('i', { id: 'ed-tl-alca', className: 'tl-alca', title: 'Arraste para aumentar ou diminuir a timeline' }),
      el('div', { className: 'tempo-topo' }, el('button', { id: 'ed-play', className: 'btn mini', style: 'min-width:92px', type: 'button', textContent: 'Reproduzir', onclick: tocar }),
        el('span', {}, el('b', { id: 'ed-t-agora', textContent: '0:00.0' }), ' / ', el('span', { id: 'ed-t-total' })),
        el('label', { className: 'tl-campo' }, 'Início', el('input', { id: 'ed-ini', onchange: e => definirTempo('ini', e.target.value) })),
        el('label', { className: 'tl-campo' }, 'Fim', el('input', { id: 'ed-fim', onchange: e => definirTempo('fim', e.target.value) })),
        el('label', { className: 'tl-campo' }, 'Duração (s)', el('input', { id: 'ed-durc', onchange: e => definirTempo('dur', e.target.value) })),
        el('label', { className: 'tl-campo vol' }, 'Volume ', el('b', { id: 'ed-vol-txt', textContent: `${Math.round(S.p.audio.original.volume * 100)}%` }),
          el('input', { type: 'range', min: 0, max: 2, step: 0.05, value: S.p.audio.original.volume, oninput: e => { S.p.audio.original.volume = parseFloat(e.target.value); ligarAudio(); clearTimeout(S.tm4); S.tm4 = setTimeout(() => mudou(false), 400); } })),
        el('span', { className: 'ferramentas', style: 'margin:0 0 0 auto;flex-wrap:nowrap' },
          el('button', { className: 'btn leve mini', type: 'button', textContent: '+ Trecho', title: 'Novo trecho da mesma gravação, a partir do ponto atual', onclick: () => UI().novoTrecho() }),
          el('button', { className: 'btn leve mini', type: 'button', textContent: 'Dividir', title: 'Divide o trecho no ponto atual', onclick: () => UI().dividir() }),
          el('button', { className: 'btn leve mini', type: 'button', textContent: 'Área segura', title: 'Mostra na prévia as áreas cobertas pela interface do Reels e do TikTok', onclick: () => { S.guias = !S.guias; S.sujo = true; } }),
          el('button', { id: 'ed-tl-recolher', className: 'btn leve mini', type: 'button', textContent: 'Recolher', title: 'Recolhe ou mostra a timeline', onclick: () => UI().recolher() }))),
      el('div', { id: 'ed-tl-corpo', className: 'tl-corpo' },
        el('div', { className: 'tl-linha' }, el('span', { className: 'tl-rot', textContent: 'Gravação' }),
          el('div', { id: 'ed-tl', className: 'tl' }, el('canvas', { id: 'ed-onda' }), el('i', { id: 'ed-fora-a', className: 'tl-fora' }), el('i', { id: 'ed-fora-b', className: 'tl-fora' }),
            el('i', { id: 'ed-mao-a', className: 'tl-mao', title: 'Início do trecho selecionado' }), el('i', { id: 'ed-mao-b', className: 'tl-mao', title: 'Fim do trecho selecionado' }), el('i', { id: 'ed-agulha', className: 'tl-agulha' }))),
        el('div', { id: 'ed-trilhas', className: 'trilhas' })))));
  S.video = $('#ed-video'); S.ctx = $('#ed-canvas').getContext('2d'); $('#ed-prev').style.aspectRatio = `${W} / ${H}`;
  const v = S.video;
  v.addEventListener('loadedmetadata', () => { v.currentTime = S.p.inicio; $('#ed-fonte').style.width = `min(100%, ${(40 * v.videoWidth / v.videoHeight).toFixed(2)}vh)`; });
  ['seeked', 'loadeddata', 'pause', 'play'].forEach(n => v.addEventListener(n, () => { S.sujo = true; atualizarTempo(); }));
  v.addEventListener('pause', () => UI().som.parar());
  $('#ed-prev').onpointerdown = ev => { const alvo = escolherEm(pontoPrev(ev)); selecionar(alvo); if (alvo) moverSel(ev); };
  $('#ed-sel').onpointerdown = ev => {
    const a = ev.target.dataset.a;
    if (a) { redimensionarSel(ev, a); return; }
    // A seleção cobre a camada inteira: um clique sobre outra camada menor precisa alcançá-la.
    selecionar(escolherEm(pontoPrev(ev)) || S.sel);
    moverSel(ev);
  };
  $('#ed-prev').addEventListener('wheel', ev => {
    const c = S.p.camadas.find(x => x.id === S.sel && x.tipo === 'video');
    if (!c) return;
    ev.preventDefault();
    c.zoom = Math.round(limitar(c.zoom * (ev.deltaY < 0 ? 1.08 : 1 / 1.08), 1, 6) * 100) / 100;
    S.sujo = true;
    clearTimeout(S.tz); S.tz = setTimeout(() => { mudou(); pintarPainel(); }, 250);
  }, { passive: false });
  ligarTimeline(); UI().ligar(); pintarRegioes(); pintarPresets(); pintarPassos(); pintarPainel(); ajustarLayout();
}
addEventListener('resize', () => { if (S.ativo && S.d) ajustarLayout(); });
addEventListener('keydown', ev => {
  if (!S.ativo || !S.d || G.tela !== 'editor' || /INPUT|TEXTAREA|SELECT/.test(ev.target.tagName)) return;
  if (ev.code === 'Space') { ev.preventDefault(); tocar(); }
  if (ev.key === 'Delete' || ev.key === 'Backspace') {  // apaga o que estiver selecionado: camada da prévia ou bloco da timeline
    const p = S.p, fx = S.fx;
    if (S.sel && S.sel !== '__leg' && p.camadas.some(c => c.id === S.sel)) { p.camadas = p.camadas.filter(c => c.id !== S.sel); S.sel = null; S.fx = null; pintarSelecao(); pintarRegioes(); }
    else if (fx && fx.tipo === 'efeito') { p.efeitos = p.efeitos.filter(e => e.id !== fx.id); S.fx = null; }
    else if (fx && fx.tipo === 'clipe') { p.audio.clipes = p.audio.clipes.filter(c => c.id !== fx.id); S.fx = null; }
    else if (fx && fx.tipo === 'seg' && p.segmentos.length > 1) { p.segmentos = p.segmentos.filter(g => g.id !== fx.id); selSeg(p.segmentos[0].id); S.fx = null; S.tocando = 0; }
    else return;
    ev.preventDefault(); mudou(); pintarPainel(); avisar('Removido. Ctrl+Z desfaz.');
  }
  if (ev.key.toLowerCase() === 'z' && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); desfazer(); }
});

function espera(msg, progresso) {
  $('#tela-editor').replaceChildren(el('div', { className: 'espera' }, el('div', {}, el('h2', { className: 'tit', textContent: 'Abrindo o editor' }), el('p', { textContent: msg }),
    progresso !== undefined ? el('div', { className: 'barra', style: 'width:280px;margin:10px auto 0' }, el('i', { style: `width:${Math.round(progresso * 100)}%` })) : null)));
}
async function abrir(id) {
  cancelAnimationFrame(S.raf);
  if (S.audio) UI().som.parar();
  S.id = id; S.d = null; S.video = null; S.ctx = null; S.sel = null; S.hist = []; S.onda = []; S.audio = null; S.chatChave = ''; S.fx = null; S.seg = null; S.tocando = 0; S.frz = null;
  espera('Buscando o corte...');
  try {
    const url = `/api/editor/abrir?corte=${encodeURIComponent(id)}`;
    let d = await api(url);
    if (d.preparar) {
      const t = await api('/api/editor/preparar', { corte: id });
      await aguardarTarefa(t.id, x => espera(x.mensagem, x.progresso));
      d = await api(url);
    }
    S.d = d;
    const novo = !d.projeto;
    S.p = d.projeto || {
      formato: d.formato || '9:16', inicio: d.inicio, fim: d.fim, preset: 'jogo_cheio', fundo: '#000000', fps: 30, divisao: 0.42, volume: 1, qualidade: 'alta',
      regioes: { webcam: d.regioes?.webcam || null, gameplay: d.regioes?.gameplay || { x: 0, y: 0, w: 1, h: 1 }, chat: d.regioes?.chat || null }, camadas: PRESETS.jogo_cheio.f(),
      legenda: { ativa: true, ...ESTILOS[0].estilo, maxPalavras: 3, x: 540, y: 1500, offset: 0, blocos: [] },
    };
    Fx.completar(S.p); selSeg(S.p.segmentos[0].id);
    definirFormato(S.p.formato, false);
    if (novo) { S.p.camadas = PRESETS.jogo_cheio.f(); Object.assign(S.p.legenda, { x: W / 2, y: Math.round(H * 0.8) }); }
    Object.assign(S.p, { divisao: S.p.divisao ?? 0.42, volume: S.p.volume ?? 1, qualidade: S.p.qualidade || 'alta' });
    S.p.regioes.chat = S.p.regioes.chat || null;
    if (!S.p.legenda.blocos.length && d.palavras.length) S.p.legenda.blocos = agrupar(d.palavras, S.p.legenda);
    S.p.camadas.filter(c => c.tipo === 'texto').forEach(medirTitulo);
    montar();
    segs(); S.hist = [JSON.stringify(S.p)];
    S.sujo = true; laco();
    api(`/api/editor/onda?corte=${encodeURIComponent(id)}`).then(r => { S.onda = r.picos; pintarTimeline(); }).catch(() => {});
    if (novo) {
      const salvo = d.regioes?.layout;
      if (salvo && (S.p.regioes.webcam || !salvo.camadas.some(c => c.regiao === 'webcam'))) { aplicarLayoutSalvo(salvo); msgFonte(`Preset de ${d.streamer} aplicado: regiões e layout salvos. Troque o template se quiser.`); }
      else {
        const cam = S.p.regioes.webcam || await detectarWebcam();
        if (S.id === id) escolherTemplate(cam && serve(PRESETS.cam_titulo_jogo) ? 'cam_titulo_jogo' : cam ? 'jogo_cam_sobre' : 'jogo_cheio');
      }
    }
  } catch (e) {
    S.id = null;
    $('#tela-editor').replaceChildren(el('div', { className: 'espera' }, el('div', {}, el('h2', { className: 'tit', textContent: 'Não consegui abrir este corte' }), el('p', { textContent: e.message }),
      el('button', { className: 'btn', style: 'margin-top:12px', type: 'button', textContent: 'Voltar aos cortes', onclick: () => irPara('cortes') }))));
  }
}
async function escolher() {
  await carregarLives().catch(() => {});
  const cortes = todosCortes();
  G.visiveis = cortes;
  $('#tela-editor').replaceChildren(el('div', { className: 'tela', style: 'padding:12px' }, el('header', { className: 'cabeca' }, el('h1', { textContent: 'Editor' }), el('p', { textContent: 'Clique no corte que você quer editar para começar.' })),
    cortes.length ? el('div', { className: 'grade' }, ...cortes.map((c, i) => cartao(c, i, () => irPara('editor', { corte: c.id }))))
      : el('div', { className: 'vazio' }, el('p', { textContent: 'Você ainda não tem cortes para editar.' }), el('button', { className: 'btn', style: 'margin-top:12px', type: 'button', textContent: 'Gerar cortes', onclick: () => irPara('gerar') }))));
}
window.VCEditor = { S, Fx, get W() { return W; }, get H() { return H; }, segs, segSel, selSeg, durSaida, tempoSaida, irSaida, mudou, pintarPainel, pintarTimeline, pintarSelecao, pintarPresets,
  campoNum, campoCor, campoFaixa, campoSel, campoCheck, arrastar, fmt, limitar, medirTitulo, novoTitulo, estiloFaixa, selecionar, regiaoDe, efetivo, reorganizar, aplicarPreset, PRESETS, FAIXAS,
  legendaAgrupar: agrupar, reQuebrar, msgFonte, imagem, vid };
window.Editor = {
  mostrar(corte) {
    S.ativo = true;
    if (corte && corte !== S.id) return abrir(corte);
    if (S.d) { cancelAnimationFrame(S.raf); S.sujo = true; laco(); ajustarLayout(); } else escolher();
  },
  pausar() { S.ativo = false; if (S.video) { S.video.pause(); UI().som.parar(); } },
};
})();
