/* ADA — PAINEL DE OPERAÇÃO (controlador + widgets).
   mostra ao vivo o que a ADA faz: o córtex raciocinando (prosa), a decisão e cada
   tool virando uma tela de operação. dirigido pelo app.js (fluxo SSE) e reaberto
   pelo clique na linha do raciocínio (mostrarCenario, estático).

   FASE 1: as tools devolvem o resultado como TEXTO → cai no widget genérico.
   Quando as tools passarem a devolver lista estruturada [[chave,valor,kind?], …],
   o mesmo card vira o widget rico (medidores, relógio, player…) sem mexer aqui. */
(function () {
  const ico = window.ADA_ICO;
  const E = (cls, html) => { const d = document.createElement('div'); if (cls) d.className = cls; if (html != null) d.innerHTML = html; return d; };
  const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const acha = (res, k) => { const r = (res || []).find(x => x[0] === k); return r ? r[1] : ''; };
  const num = (s) => parseFloat(String(s).replace(',', '.').replace(/[^\d.]/g, '')) || 0;

  let app, painel, fase, corpo;
  function refs() {
    app = document.querySelector('.app');
    painel = document.getElementById('painel');
    fase = document.getElementById('pnlFase');
    corpo = document.getElementById('pnlCorpo');
  }

  function abrir() { refs(); app.classList.add('painel-aberto'); app.classList.remove('painel-fim'); }
  function fechar() { refs(); app.classList.remove('painel-aberto'); }
  function setFase(html) { refs(); fase.innerHTML = html; }
  function limpar() { refs(); corpo.textContent = ''; app.classList.remove('painel-fim'); }
  function fim() { refs(); app.classList.add('painel-fim'); }

  /* ---------- cartão HUD genérico (rótulo + estado + corpo) ---------- */
  function wHud(nome, estado, inner) {
    const card = E('hud' + (estado === 'exec' ? ' exec' : ''));
    const stt = estado === 'exec' ? '● executando' : '✓ concluído';
    card.appendChild(E('hud-rot', `<span class="ico">${ico(nome)}</span><span class="tag">${nome}</span><span class="stt">${stt}</span>`));
    const body = E('hud-body'); if (inner) body.appendChild(inner); card.appendChild(body);
    return card;
  }

  function medidor(lbl, pct, valHtml, nota, tipo) {
    const m = E('medidor');
    m.appendChild(E('medidor-top', `<span class="medidor-lbl">${lbl}</span><span class="medidor-val">${valHtml}</span>`));
    const tr = E('medidor-trilho'); const f = E('medidor-fill' + (tipo ? ' ' + tipo : '')); tr.appendChild(f); m.appendChild(tr);
    if (nota) m.appendChild(E('medidor-nota', nota));
    f.style.width = Math.max(2, Math.min(100, pct)) + '%';
    return m;
  }

  /* widgets ricos — usados quando a tool devolve lista estruturada (fase 2) */
  const WIDGET = {
    status_mac(res) {
      const wrap = E('');
      const cpu = acha(res, 'cpu'), cpuPct = num(cpu.split('·')[0]);
      const ram = acha(res, 'ram'), ru = num(ram.split('/')[0]), rt = num(ram.split('/')[1]) || 16, ramPct = (ru / rt) * 100;
      const disco = acha(res, 'disco');
      wrap.appendChild(medidor('processador', cpuPct, `${cpuPct}<span class="un">%</span>`, '8 núcleos', cpuPct > 80 ? 'alto' : ''));
      wrap.appendChild(medidor('memória', ramPct, `${ram}`, null, ramPct > 85 ? 'alto' : ''));
      wrap.appendChild(medidor('disco', 64, `${disco}`, 'volume principal', ''));
      return wrap;
    },
    que_horas(res) {
      return E('relogio', `<div class="relogio-hora">${acha(res, 'hora')}</div><div class="relogio-data">${acha(res, 'data')}</div>`);
    },
    tocar_musica(res) {
      const eq = '<div class="eq">' + Array.from({ length: 12 }, () => '<i></i>').join('') + '</div>';
      return E('', `<div class="player-faixa">${acha(res, 'tocando')}</div>${eq}<div class="player-meta">${acha(res, 'saída')} · vol ${acha(res, 'volume')}</div>`);
    },
    ajustar_brilho(res) {
      const now = num(acha(res, 'brilho')), antes = num(acha(res, 'antes'));
      const d = E('dial');
      d.innerHTML = `<div class="dial-anel" style="--p:${now}"><span>${now}%</span></div>
        <div class="dial-info"><div class="dial-de"><b>${antes}%</b><span class="dial-seta">→</span><b style="color:var(--bloodink)">${now}%</b></div>
        <div class="medidor-nota" style="margin-top:8px">brilho da tela ajustado</div></div>`;
      return d;
    },
    buscar_arquivo(res) {
      const cam = acha(res, 'caminho'), achados = acha(res, 'achados');
      const list = E('arqs');
      list.appendChild(E('arq hit', `<span class="a-ico">${ico('buscar_arquivo')}</span><span class="a-cam">${esc(cam)}</span><span class="a-chk">✓</span>`));
      const wrap = E(''); wrap.appendChild(list); if (achados) wrap.appendChild(E('medidor-nota', esc(achados))); return wrap;
    },
    abrir_app(res) {
      const appn = acha(res, 'app'), arq = acha(res, 'arquivo');
      const j = E('janela');
      j.innerHTML = `<div class="janela-barra"><span class="luz r"></span><span class="luz y"></span><span class="luz g"></span><span class="tt">${esc(appn)}</span></div>
        <div class="janela-tela"><div class="doc">${esc(arq)}</div><div class="sub">aberto no ${esc(appn)}</div></div>`;
      return j;
    },
  };

  /* genérico — resultado cru da tool (string na fase 1, ou lista chave/valor) */
  function widgetGenerico(res) {
    const wrap = E('kv-lista');
    if (Array.isArray(res)) {
      res.forEach(([k, v]) => wrap.appendChild(E('medidor-nota',
        `<span style="color:var(--apagado)">${esc(k)}</span>&nbsp;&nbsp;<span style="color:var(--ink2)">${esc(v)}</span>`)));
    } else if (res != null && String(res).trim()) {
      wrap.appendChild(E('medidor-nota', esc(res)));
    }
    return wrap;
  }

  function widgetTool(nome, res, estado) {
    let inner;
    if (estado === 'exec') inner = E('medidor-nota', 'executando…');
    else if (Array.isArray(res) && WIDGET[nome]) inner = WIDGET[nome](res);
    else inner = widgetGenerico(res);
    return wHud(nome, estado, inner);
  }

  /* ---------- API incremental (fluxo ao vivo) ---------- */
  let racEl = null, toolEls = {};
  function reset() {
    abrir(); limpar(); racEl = null; toolEls = {};
    setFase('<span class="ph">raciocinando</span>');
  }
  function cardRac() {
    const card = E('hud rac');
    card.appendChild(E('hud-rot',
      '<span class="ico"><svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="5.5"/><circle cx="8" cy="8" r="1.6"/></svg></span>' +
      '<span class="tag">raciocínio · córtex</span><span class="stt rac-stt">● pensando</span>'));
    card.appendChild(E('prosa-pnl'));
    return card;
  }
  function pensa(prosa) {
    refs();
    if (!racEl) { racEl = cardRac(); corpo.appendChild(racEl); }
    racEl.querySelector('.prosa-pnl').textContent = prosa;
    corpo.scrollTop = corpo.scrollHeight;
  }
  function decisao(text) {
    refs();
    if (!racEl) { racEl = cardRac(); corpo.appendChild(racEl); }
    if (racEl.querySelector('.linha.dec')) return;   // uma decisão só por card
    const c = text.indexOf('·'); const rot = c > 0 ? text.slice(0, c).trim() : 'decisão'; const corpoT = c > 0 ? text.slice(c + 1).trim() : text;
    const st = racEl.querySelector('.rac-stt'); if (st) st.textContent = '✓ decidido';
    racEl.appendChild(E('linha dec', `<span class="rot">${esc(rot)}</span>${esc(corpoT)}`));
  }
  function stats(rac, resp, tok, passos) {
    refs();
    if (!racEl) return;
    racEl.querySelector('.rac-meta')?.remove();
    const partes = [`raciocinou ${rac}s`, `respondeu ${resp}s`];
    if (passos) partes.push(`${passos} ${passos === 1 ? 'passo' : 'passos'}`);
    if (tok) partes.push(`~${tok} tok/s`);
    racEl.appendChild(E('rac-meta', partes.join(' &nbsp;·&nbsp; ')));
  }
  function toolExec(nome) {
    refs();
    setFase('<span class="ph">executando</span> <span class="arr">·</span> ' + nome);
    const card = widgetTool(nome, null, 'exec');
    corpo.appendChild(card); toolEls[nome] = card; corpo.scrollTop = corpo.scrollHeight;
  }
  function toolFeito(nome, res) {
    refs();
    const card = widgetTool(nome, res, 'feito');
    if (toolEls[nome]) { toolEls[nome].replaceWith(card); } else { corpo.appendChild(card); }
    toolEls[nome] = card; corpo.scrollTop = corpo.scrollHeight;
  }
  function bloqueio(tipo, titulo, sub) {
    refs();
    const neutro = tipo === 'ok';
    const cad = neutro
      ? '<path d="M14 21V15a9 9 0 0 1 18 0v6"/><rect x="9" y="21" width="28" height="20" rx="2"/><circle cx="23" cy="30" r="2.4"/>'
      : '<path d="M14 21V15a9 9 0 0 1 18 0"/><rect x="9" y="21" width="28" height="20" rx="2"/><path d="M19 31l8 0M23 27v8"/>';
    const card = E('hud ' + (neutro ? 'neutro' : 'vermelho'));
    card.appendChild(E('bloqueio',
      `<div class="bloqueio-cad"><svg viewBox="0 0 46 46">${cad}</svg></div>
       <div class="bloqueio-tit">${esc(titulo)}</div><div class="bloqueio-sub">${esc(sub)}</div>`));
    corpo.appendChild(card);
  }

  /* ---------- estático: reabrir o painel de uma mensagem já concluída ----------
     op = { think, decisao, tools:[{nome,res}], stats:{rac,resp,tok,passos}, recusa } */
  function mostrarCenario(op) {
    reset();
    if (op.think) pensa(op.think);
    if (op.decisao) decisao(op.decisao);
    if (op.stats) stats(op.stats.rac, op.stats.resp, op.stats.tok, op.stats.passos);
    const tools = op.tools || [];
    if (tools.length) {
      setFase('<span class="ph">concluído</span> <span class="arr">·</span> ' + tools.length + (tools.length === 1 ? ' operação' : ' operações'));
      tools.forEach(t => corpo.appendChild(widgetTool(t.nome, t.res, 'feito')));
    } else {
      setFase('<span class="ph">concluído</span> <span class="arr">·</span> sem ferramenta');
      if (op.recusa) bloqueio('bad', 'ação bloqueada', 'gatilho irreversível — desarmado por segurança. ela parou e devolveu a decisão pra você.');
      else bloqueio('ok', 'resposta direta', 'nada de ferramenta aqui — é conversa. ela respondeu de dentro.');
    }
    fim();
  }

  window.Painel = { abrir, fechar, setFase, reset, pensa, decisao, stats, toolExec, toolFeito, bloqueio, fim, mostrarCenario };
})();
