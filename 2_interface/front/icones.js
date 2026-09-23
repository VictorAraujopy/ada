/* ADA — ícones monoline das tools (offline, sem dependências).
   usados pelo painel (rótulo de cada card de ferramenta) e pela busca de arquivo.
   os nomes batem com tools_pool.json do núcleo. */

const ICONES = {
  status_mac: '<path d="M2 4h12v8H2z"/><path d="M5.5 14h5"/>',
  que_horas:  '<circle cx="8" cy="8" r="6"/><path d="M8 4.5V8l2.4 1.6"/>',
  verificar_wifi: '<path d="M2 6.2a9 9 0 0 1 12 0"/><path d="M4.4 8.6a6 6 0 0 1 7.2 0"/><path d="M6.7 11a3 3 0 0 1 2.6 0"/><circle cx="8" cy="13" r=".5"/>',
  abrir_app:  '<rect x="2.5" y="2.5" width="4.5" height="4.5"/><rect x="9" y="2.5" width="4.5" height="4.5"/><rect x="2.5" y="9" width="4.5" height="4.5"/><rect x="9" y="9" width="4.5" height="4.5"/>',
  fechar_app: '<rect x="2.5" y="2.5" width="11" height="11"/><path d="M5.5 5.5l5 5M10.5 5.5l-5 5"/>',
  tocar_musica: '<path d="M6 12.5V4l7-1.5V11"/><circle cx="4.2" cy="12.5" r="1.8"/><circle cx="11.2" cy="11" r="1.8"/>',
  pausar_musica: '<rect x="4" y="3" width="2.6" height="10"/><rect x="9.4" y="3" width="2.6" height="10"/>',
  proxima_musica: '<path d="M3 3l7 5-7 5z"/><rect x="11" y="3" width="2" height="10"/>',
  ajustar_volume: '<path d="M2 6v4h2.5L8 13V3L4.5 6z"/><path d="M11 6a3 3 0 0 1 0 4"/>',
  ajustar_brilho: '<circle cx="8" cy="8" r="3"/><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3 3l1.4 1.4M11.6 11.6 13 13M13 3l-1.4 1.4M4.4 11.6 3 13"/>',
  tirar_screenshot: '<rect x="2" y="4" width="12" height="9" rx="1"/><circle cx="8" cy="8.5" r="2.3"/><path d="M5.5 4l1-1.5h3l1 1.5"/>',
  mudar_tema: '<path d="M8 2a6 6 0 1 0 5.2 9A5 5 0 0 1 8 2z"/>',
  bloquear_tela: '<rect x="3.5" y="7" width="9" height="6.5" rx="1"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2"/>',
  buscar_arquivo: '<circle cx="6.8" cy="6.8" r="4"/><path d="M9.8 9.8 14 14"/>',
  criar_lembrete: '<path d="M3 5.5h10v8.5H3z"/><path d="M3 5.5 8 9l5-3.5"/><path d="M5 2.5v3M11 2.5v3"/>',
  definir_alarme: '<circle cx="8" cy="9" r="5"/><path d="M8 6.5V9l1.8 1.2"/><path d="M3 4 5 2.2M13 4l-2-1.8"/>',
  listar_lembretes: '<path d="M5.5 4h8M5.5 8h8M5.5 12h8"/><circle cx="2.6" cy="4" r=".7"/><circle cx="2.6" cy="8" r=".7"/><circle cx="2.6" cy="12" r=".7"/>',
  listar_apps_abertos: '<rect x="2.5" y="2.5" width="4.5" height="4.5"/><rect x="9" y="2.5" width="4.5" height="4.5"/><rect x="2.5" y="9" width="4.5" height="4.5"/><rect x="9" y="9" width="4.5" height="4.5"/>',
  esvaziar_lixeira: '<path d="M3.5 4.5h9l-.8 9.5H4.3z"/><path d="M2.5 4.5h11M6 4.5V3h4v1.5"/>',
};

const icoSVG = (n) => `<svg viewBox="0 0 16 16">${ICONES[n] || '<circle cx="8" cy="8" r="5"/>'}</svg>`;

window.ADA_ICO = icoSVG;
