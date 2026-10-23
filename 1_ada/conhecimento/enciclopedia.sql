
CREATE VIRTUAL TABLE trechos USING fts5(
    wiki UNINDEXED,
    pagina,
    secao,
    texto,
    -- unicode61 corta o texto em palavras, em minúscula e sem acento; porter reduz cada palavra à raiz em inglês (samples e sample viram sampl)
    tokenize = 'porter unicode61'
);
