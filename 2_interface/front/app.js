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
const mkThink = window.ADA_criarThink;

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

const REGEX_RECUSA = /n[ãa]o (vou|posso|toco|faço)|recus|irrevers[íi]vel|desarmad|destrutiv|sem confirmar/i;

/* ---------- markdown leve (escapa primeiro, depois formata) ---------- */

function md(t) {
  let h = t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  h = h.replace(/```\w*\n?([\s\S]*?)```/g, (_, c) => `<pre><code>${c.trim()}</code></pre>`);
  h = h.replace(/`([^`\n]+)`/g, '<code>$1</code>');
  h = h.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
  h = h.replace(/\*([^*\n]+)\*/g, '<em style="color:var(--bloodink)">$1</em>');
  return h;
}

const fmtTempo = (ts) => {
  const s = (Date.now() / 1000) - ts;
  if (s < 90) return 'agora';
  if (s < 3600) return Math.round(s / 60) + 'min';
  if (s < 86400) return Math.round(s / 3600) + 'h';
  return new Date(ts * 1000).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
};

/* deriva a "decisão" (carimbo) a partir do que a ADA fez — o backend não a emite */
function derivarDecisao(tools, resposta) {
  if (tools.length) return 'AÇÃO · ' + tools.map(t => t.nome).join(' → ');
  return REGEX_RECUSA.test(resposta) ? 'TEXTO · recusou — ação desarmada' : 'TEXTO · sem ferramenta';
}

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

/* mensagem da ADA: avatar + linha do raciocínio (clicável) + resposta */
function addAda() {
  const m = el('msg ada');
  const av = el('avatar'); av.textContent = 'A';
  const body = el('body');
  const drv = mkThink();
  drv.root.onclick = () => { if (m._op) Painel.mostrarCenario(m._op); };
  const answer = el('answer');
  body.append(drv.root, answer);
  m.append(av, body);
  chat.appendChild(m);
  return { m, body, think: drv, answer, t0: performance.now() };
}

function addVotos(container, n, atual) {
  const linha = el('votos');
  for (const [voto, simbolo] of [["up", "✓ boa"], ["down", "✕ ruim"]]) {
    const b = document.createElement('button');
    b.className = 'voto' + (atual === voto ? ' ativo' : '');
    b.textContent = simbolo;
    b.title = voto === 'up' ? 'resposta boa (vira exemplo de treino)' : 'resposta ruim (vira correção no treino)';
    b.onclick = async () => {
      const novo = b.classList.contains('ativo') ? null : voto;   // clicar de novo desfaz
      await fetch('/avaliar', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conversa, n, voto: novo }) });
      linha.querySelectorAll('.voto').forEach(x => x.classList.remove('ativo'));
      if (novo) b.classList.add('ativo');
    };
    linha.appendChild(b);
  }
  container.appendChild(linha);
}

function addErro(txt) {
  chat.appendChild(el('erro', txt));
  scroll();
}

/* ---------- abrir conversa (restaura do banco) ---------- */

async function abrir(id) {
  if (ocupado) aborto?.abort();
  Painel.fechar();
  const r = await fetch('/conversas/' + id);
  if (!r.ok) { conversa = null; marcarAtiva(); telaVazia(); return; }
  const c = await r.json();
  conversa = id;
  chat.textContent = '';
  for (const msg of c.mensagens) {
    if (msg.role === 'user') { addUser(msg.content); continue; }
    const g = addAda();
    const meta = msg.meta || {};
    const tools = (meta.tools || []).map(t => ({ nome: t.nome, res: t.res }));
    const pensouS = meta.pensou_s ?? 0, respondeuS = meta.respondeu_s ?? 0;
    const total = (Number(pensouS) + Number(respondeuS)).toFixed(1);
    g.think.concluir(total);
    g.answer.innerHTML = md(msg.content);
    const tok = respondeuS > 0 ? Math.round((msg.content.length / 4) / respondeuS) : 0;
    g.m._op = {
      think: (meta.think || '').trim(),
      decisao: derivarDecisao(tools, msg.content),
      tools,
      stats: { rac: pensouS, resp: respondeuS, tok, passos: tools.length },
      recusa: !tools.length && REGEX_RECUSA.test(msg.content),
    };
    addVotos(g.body, msg.n ?? null, meta.voto ?? null);
  }
  marcarAtiva();
  scroll();
  appEl.classList.remove('menu-aberto');
  input.focus();
}

function novaConversa() {
  if (ocupado) aborto?.abort();
  Painel.fechar();
  conversa = null;
  marcarAtiva();
  telaVazia();
  appEl.classList.remove('menu-aberto');
  input.focus();
}

/* ---------- envio + leitura do stream SSE (dirige chat E painel) ---------- */

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
  Painel.reset();              // abre o painel, limpa, fase "raciocinando"
  const cur = document.createElement('span'); cur.className = 'cursor';
  g.answer.appendChild(cur);
  aborto = new AbortController();

  // se tem outra geração na frente (outra aba), avisa em vez de parecer travado
  fetch('/info').then(r => r.json()).then(i => {
    if (i.fila > 0) g.think.root.before(el('fila-aviso', 'na fila — outra geração na frente…'));
  }).catch(() => {});

  let pensouS = null, t_resp = null, resposta = '', prosa = '', fimRac = false;
  const tools = [];
  const fecharRaciocinio = () => { if (!fimRac) { fimRac = true; g.think.collapse(); } };

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
        if (ev.t === 'think') {
          prosa += ev.d;
          Painel.pensa(prosa);               // a prosa vai pro painel; a linha do chat fica "raciocinando…"
        } else if (ev.t === 'tool') {
          fecharRaciocinio();
          Painel.setFase('<span class="ph">executando</span> <span class="arr">·</span> ' + ev.nome);
          Painel.toolFeito(ev.nome, ev.res);  // a tool já rodou no backend: card nasce concluído
          tools.push({ nome: ev.nome, res: ev.res });
        } else if (ev.t === 'resp') {
          if (!t_resp) { t_resp = performance.now(); pensouS = ((t_resp - g.t0) / 1000).toFixed(1); }
          fecharRaciocinio();
          Painel.setFase('<span class="ph">respondendo</span>');
          resposta += ev.d;
          cur.before(document.createTextNode(ev.d));
        } else if (ev.t === 'erro') {
          fecharRaciocinio();
          addErro(ev.d);
          Painel.bloqueio('bad', 'erro', ev.d);
        }
        scroll();
      }
    }
    fecharRaciocinio();

    if (resposta.trim()) {
      cur.remove();
      g.answer.innerHTML = md(resposta);   // troca o texto cru pelo markdown renderizado
      const respondeuS = t_resp ? Number(((performance.now() - t_resp) / 1000).toFixed(1)) : 0;
      const total = (Number(pensouS ?? 0) + respondeuS).toFixed(1);
      const tok = respondeuS > 0 ? Math.round((resposta.length / 4) / respondeuS) : 0;
      g.think.concluir(total);

      // fecha o painel daquele turno: decisão (carimbo) + métricas + bloqueio se sem tool
      const recusa = !tools.length && REGEX_RECUSA.test(resposta);
      Painel.decisao(derivarDecisao(tools, resposta));
      Painel.stats(pensouS ?? 0, respondeuS, tok, tools.length);
      if (tools.length) {
        Painel.setFase('<span class="ph">concluído</span> <span class="arr">·</span> ' + tools.length + (tools.length === 1 ? ' operação' : ' operações'));
      } else {
        Painel.setFase('<span class="ph">concluído</span> <span class="arr">·</span> sem ferramenta');
        Painel.bloqueio(recusa ? 'bad' : 'ok',
          recusa ? 'ação bloqueada' : 'resposta direta',
          recusa ? 'gatilho irreversível — desarmado por segurança. ela parou e devolveu a decisão pra você.'
                 : 'nada de ferramenta aqui — é conversa. ela respondeu de dentro.');
      }
      Painel.fim();

      g.m._op = {
        think: prosa.trim(),
        decisao: derivarDecisao(tools, resposta),
        tools,
        stats: { rac: pensouS ?? 0, resp: respondeuS, tok, passos: tools.length },
        recusa,
      };
      addVotos(g.body, null, null);
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
document.getElementById('pnlX').onclick = () => Painel.fechar();
btnExp.onclick = () => { if (conversa) window.location = `/conversas/${conversa}/export`; };

(async () => {
  await carregarLista();
  if (conversa) await abrir(conversa); else telaVazia();
  esperarPronta();
})();
