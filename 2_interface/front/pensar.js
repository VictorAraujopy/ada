/* ADA — a linha do raciocínio no chat.
   chat enxuto: uma linha só (raciocinando… → respondendo… → respondeu em Xs ›).
   a prosa, as tools e as métricas vivem no PAINEL. clicar nela reabre o painel. */

function criarThink() {
  const root = document.createElement('div');
  root.className = 'think-nota live';
  root.innerHTML = `<span class="tn-led"></span><span class="tn-txt">raciocinando…</span>`;
  const txt = root.querySelector('.tn-txt');
  return {
    root,
    // fim do raciocínio (chegou a 1ª tool ou a 1ª resposta): vira "respondendo…"
    collapse() { root.classList.remove('live'); root.classList.add('feito'); txt.textContent = 'respondendo…'; },
    // turno terminou: vira "respondeu em Xs"
    concluir(total) { root.classList.remove('live'); root.classList.add('feito'); txt.textContent = `respondeu em ${total}s`; },
  };
}

window.ADA_criarThink = criarThink;
