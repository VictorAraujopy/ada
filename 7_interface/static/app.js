/* ADA — frontend do chat.
   Conversas persistentes: a sidebar lista o que tá no SQLite do backend;
   abrir uma conversa re-renderiza tudo (think, tools, resposta, métricas)
   a partir do banco. Cada envio abre um stream SSE e desenha ao vivo. */

const chat    = document.getElementById('chat');
const form    = document.getElementById('form');
const input   = document.getElementById('msg');
const send    = document.getElementById('send');
const badge   = document.getElementById('badge');
const estado  = document.getElementById('estado');
const lista   = document.getElementById('lista');
const btnExp  = document.getElementById('exportar');
const appEl   = document.querySelector('.app');
const tplEmpty = document.getElementById('tpl-empty');

let conversa = localStorage.adaConversa || null;  // id da conversa aberta
let ocupado = false;        // true enquanto uma resposta streama
let aborto = null;          // AbortController do stream atual

const scroll = () => chat.scrollTop = chat.scrollHeight;
const el = (cls, txt) => {
  const d = document.createElement('div');
  d.className = cls;
  if (txt) d.textContent = txt;
  return d;
};

/* ---------- markdown leve (escapa primeiro, depois formata) ---------- */

function md(t) {
  let h = t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  h = h.replace(/```\w*\n?([\s\S]*?)```/g, (_, c) => `<pre><code>${c.trim()}</code></pre>`);
  h = h.replace(/`([^`\n]+)`/g, '<code>$1</code>');
  h = h.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
  return h;
}

const fmtTempo = (ts) => {
  const s = (Date.now() / 1000) - ts;
  if (s < 90) return 'agora';
  if (s < 3600) return Math.round(s / 60) + 'min';
  if (s < 86400) return Math.round(s / 3600) + 'h';
  return new Date(ts * 1000).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
};

/* ---------- prontidão: pergunta ao /info até o modelo carregar ---------- */

async function esperarPronta() {
  while (true) {
    try {
      const i = await (await fetch('/info')).json();
      if (i.pronta) {
        badge.classList.remove('off');
        estado.textContent = i.fake ? 'fake' : i.adapter.replace('ada_', '');
        form.classList.remove('off');
        input.disabled = send.disabled = false;
        input.placeholder = 'fala.';
        input.focus();
        return;
      }
    } catch (e) { /* servidor ainda subindo — tenta de novo */ }
    await new Promise(r => setTimeout(r, 1500));
  }
}

/* ---------- sidebar ---------- */

async function carregarLista() {
  const convs = await (await fetch('/conversas')).json();
  lista.textContent = '';
  convs.forEach((c, i) => {
    const item = el('conv' + (c.id === conversa ? ' ativa' : ''));
    const num = el('num', String(convs.length - i).padStart(3, '0'));
    const tit = el('tit', c.titulo);
    tit.title = c.titulo;
    const qd = el('qd', fmtTempo(c.atualizada));
    const ren = document.createElement('button');
    ren.className = 'ren'; ren.textContent = '✎'; ren.title = 'renomear';
    ren.onclick = (e) => { e.stopPropagation(); renomear(item, c); };
    const del = document.createElement('button');
    del.className = 'del'; del.textContent = '✕'; del.title = 'apagar';
    del.onclick = (e) => { e.stopPropagation(); apagar(c.id); };
    item.append(num, tit, qd, ren, del);
    item.onclick = () => abrir(c.id);
    tit.ondblclick = (e) => { e.stopPropagation(); renomear(item, c); };
    lista.appendChild(item);
  });
}

function renomear(item, c) {
  const tit = item.querySelector('.tit');
  if (!tit) return;
  const inp = document.createElement('input');
  inp.className = 'renome';
  inp.value = c.titulo;
  inp.onclick = (e) => e.stopPropagation();
  tit.replaceWith(inp);
  inp.focus(); inp.select();
  let feito = false;
  const salvar = async () => {
    if (feito) return;
    feito = true;
    const novo = inp.value.trim();
    if (novo && novo !== c.titulo) {
      await fetch('/conversas/' + c.id, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ titulo: novo }),
      });
    }
    carregarLista();
  };
  inp.onblur = salvar;
  inp.onkeydown = (e) => {
    if (e.key === 'Enter') { e.preventDefault(); salvar(); }
    if (e.key === 'Escape') { feito = true; carregarLista(); }
  };
}

async function apagar(id) {
  await fetch('/conversas/' + id, { method: 'DELETE' });
  if (id === conversa) novaConversa();
  carregarLista();
}

function marcarAtiva() {
  carregarLista();
  btnExp.disabled = !conversa;
  if (conversa) localStorage.adaConversa = conversa;
  else localStorage.removeItem('adaConversa');
}

/* ---------- blocos da conversa ---------- */

function telaVazia() {
  chat.textContent = '';
  chat.appendChild(tplEmpty.content.cloneNode(true));
  ligarChips();
}

function addUser(txt) {
  document.getElementById('empty')?.remove();
  const m = el('msg user');
  m.appendChild(el('bubble', txt));
  chat.appendChild(m);
  scroll();
}

function addAda() {
  const m = el('msg ada');
  const av = el('avatar'); av.textContent = 'A';
  const body = el('body');
  const think = el('thinking live');
  const head = el('thinking-head');
  head.appendChild(el('', 'pensando'));
  const tbody = el('thinking-body');
  think.append(head, tbody);
  head.onclick = () => think.classList.toggle('collapsed');
  const tools = el('tools');
  const answer = el('answer');
  body.append(think, tools, answer);
  m.append(av, body);
  chat.appendChild(m);
  return { m, body, think, head, tbody, tools, answer, t0: performance.now(), pensou: false };
}

function addTool(g, nome, res) {
  const c = el('tool');
  const nm = document.createElement('span'); nm.className = 'nm'; nm.textContent = nome;
  const rs = document.createElement('span'); rs.className = 'rs'; rs.textContent = '→ ' + String(res).slice(0, 80);
  const ok = document.createElement('span'); ok.className = 'ok'; ok.textContent = '✓';
  c.append(nm, rs, ok);
  g.tools.appendChild(c);
  scroll();
}

function addErro(txt) {
  chat.appendChild(el('erro', txt));
  scroll();
}

function colapsaThink(g, segundos) {
  if (g.pensou) return;
  g.pensou = true;
  const s = segundos ?? ((performance.now() - g.t0) / 1000).toFixed(1);
  g.think.classList.remove('live');
  g.think.classList.add('collapsed');
  g.head.textContent = '';
  g.head.appendChild(el('', `pensou por ${s}s`));
  const caret = document.createElement('span'); caret.className = 'caret'; caret.textContent = '▾';
  g.head.appendChild(caret);
  if (!g.tbody.textContent.trim()) g.think.remove();   // não pensou nada: some o bloco
}

function addMetricas(g, pensouS, respondeuS, chars) {
  const toks = respondeuS > 0 ? Math.round((chars / 4) / respondeuS) : null;
  const partes = [`pensou ${pensouS}s`, `respondeu ${respondeuS}s`];
  if (toks) partes.push(`~${toks} tok/s`);
  g.body.appendChild(el('metricas', partes.join(' · ')));
}

/* ---------- abrir conversa (restaura do banco) ---------- */

async function abrir(id) {
  if (ocupado) aborto?.abort();
  const r = await fetch('/conversas/' + id);
  if (!r.ok) { conversa = null; marcarAtiva(); telaVazia(); return; }
  const c = await r.json();
  conversa = id;
  chat.textContent = '';
  for (const msg of c.mensagens) {
    if (msg.role === 'user') { addUser(msg.content); continue; }
    const g = addAda();
    const meta = msg.meta || {};
    g.tbody.textContent = meta.think || '';
    colapsaThink(g, meta.pensou_s ?? '?');
    for (const t of meta.tools || []) addTool(g, t.nome, t.res);
    g.answer.innerHTML = md(msg.content);
    if (meta.pensou_s != null) addMetricas(g, meta.pensou_s, meta.respondeu_s, msg.content.length);
  }
  marcarAtiva();
  scroll();
  appEl.classList.remove('menu-aberto');
  input.focus();
}

function novaConversa() {
  if (ocupado) aborto?.abort();
  conversa = null;
  marcarAtiva();
  telaVazia();
  appEl.classList.remove('menu-aberto');
  input.focus();
}

/* ---------- envio + leitura do stream SSE ---------- */

async function enviar(txt) {
  if (ocupado || input.disabled) return;
  ocupado = true;
  send.disabled = true;
  input.value = '';

  try {
    if (!conversa) {   // primeira mensagem: cria a conversa (título = a mensagem)
      const c = await (await fetch('/conversas', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ titulo: txt }),
      })).json();
      conversa = c.id;
      marcarAtiva();
    }
  } catch (e) {
    addErro('falhou criando a conversa: ' + e.message);
    ocupado = false; send.disabled = input.disabled;
    return;
  }

  addUser(txt);
  const g = addAda();
  g.m.classList.add('viva');   // avatar pulsa enquanto ela gera
  const cur = document.createElement('span'); cur.className = 'cursor';
  g.answer.appendChild(cur);
  aborto = new AbortController();

  // se tem outra geração na frente (outra aba), avisa em vez de parecer travado
  fetch('/info').then(r => r.json()).then(i => {
    if (i.fila > 0 && !g.pensou) g.tbody.before(el('fila-aviso', 'na fila — outra geração na frente…'));
  }).catch(() => {});

  let pensouS = null, t_resp = null, resposta = '';
  try {
    const resp = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ msg: txt, conversa }),
      signal: aborto.signal,
    });
    if (!resp.ok) {
      const e = await resp.json().catch(() => ({}));
      throw new Error(e.erro || `HTTP ${resp.status}`);
    }

    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const partes = buf.split('\n\n');
      buf = partes.pop();
      for (const p of partes) {
        if (!p.startsWith('data: ')) continue;
        const ev = JSON.parse(p.slice(6));
        if (ev.t === 'think') g.tbody.append(document.createTextNode(ev.d));
        else if (ev.t === 'tool') { colapsaThink(g); addTool(g, ev.nome, ev.res); }
        else if (ev.t === 'resp') {
          if (!t_resp) { t_resp = performance.now(); pensouS = ((t_resp - g.t0) / 1000).toFixed(1); }
          colapsaThink(g, pensouS);
          resposta += ev.d;
          cur.before(document.createTextNode(ev.d));
        }
        else if (ev.t === 'erro') { colapsaThink(g); addErro(ev.d); }
        scroll();
      }
    }
    colapsaThink(g);
    if (resposta.trim()) {
      cur.remove();
      g.answer.innerHTML = md(resposta);   // troca o texto cru pelo markdown renderizado
      const respondeuS = t_resp ? ((performance.now() - t_resp) / 1000).toFixed(1) : 0;
      addMetricas(g, pensouS ?? 0, Number(respondeuS), resposta.length);
    }
    g.m.querySelector('.fila-aviso')?.remove();
    carregarLista();   // atualiza "agora" / ordem na sidebar
  } catch (e) {
    if (e.name !== 'AbortError') {
      g.m.remove();
      addErro('falhou: ' + e.message);
    }
  } finally {
    cur.remove();
    g.m.classList.remove('viva');
    aborto = null;
    ocupado = false;
    send.disabled = input.disabled;
    input.focus();
  }
}

/* ---------- amarrações ---------- */

function ligarChips() {
  document.querySelectorAll('.chips button').forEach(b => b.onclick = () => enviar(b.textContent));
}

form.onsubmit = (e) => {
  e.preventDefault();
  const t = input.value.trim();
  if (t) enviar(t);
};
document.getElementById('nova').onclick = novaConversa;
document.getElementById('menu').onclick = () => appEl.classList.toggle('menu-aberto');
btnExp.onclick = () => { if (conversa) window.location = `/conversas/${conversa}/export`; };

(async () => {
  await carregarLista();
  if (conversa) await abrir(conversa); else telaVazia();
  esperarPronta();
})();
