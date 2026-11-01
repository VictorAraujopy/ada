"""Memórias da ADA dentro da placa: o Modelo copia a conversa viva pra vagas no próprio contexto e retoma do maior começo de prompt já lido."""
import llama_cpp
import llama_cpp.llama_cpp
from llama_cpp import Llama


class Modelo(Llama):
    """Llama com vagas de memória: a sequência 0 é a conversa viva e cada vaga é uma cópia dela feita na própria placa (seq_cp), sem arquivo e sem rede."""

    def __init__(self, vagas, **kwargs):
        """Abre o modelo com uma sequência pra conversa viva mais uma por vaga, todas na mesma KV (kv_unified)."""
        parametros_padrao = llama_cpp.llama_cpp.llama_context_default_params

        def parametros_com_vagas():
            parametros = parametros_padrao()
            parametros.n_seq_max = 1 + vagas
            parametros.kv_unified = True
            return parametros

        llama_cpp.llama_cpp.llama_context_default_params = parametros_com_vagas
        try:
            super().__init__(**kwargs)
        finally:
            llama_cpp.llama_cpp.llama_context_default_params = parametros_padrao
        self.vagas = list(range(1, 1 + vagas))
        self.memorias = {}
        self.continuar = False
        self.olho = None

    def generate(self, tokens, **kwargs):
        """Gera a partir do estado retomado quando `continuar` está ligado, sem tentar reaproveitar o prefixo."""
        if self.continuar:
            kwargs["reset"] = False
        return super().generate(tokens, **kwargs)

    def retomar(self, tokens):
        """Apaga as memórias que não cobrem o começo de `tokens`, copia pra conversa viva a que cobre mais e devolve quantos tokens ela já leu (0 se nenhuma cobre)."""
        memoria_da_placa = llama_cpp.llama_get_memory(self._ctx.ctx)
        llama_cpp.llama_memory_seq_rm(memoria_da_placa, 0, -1, -1)
        for vaga, lidos in list(self.memorias.items()):
            if tokens[: len(lidos)] != lidos:
                llama_cpp.llama_memory_seq_rm(memoria_da_placa, vaga, -1, -1)
                del self.memorias[vaga]
        if not self.memorias:
            self.n_tokens = 0
            return 0
        vaga = max(self.memorias, key=lambda candidata: len(self.memorias[candidata]))
        lidos = self.memorias.pop(vaga)
        self.memorias[vaga] = lidos
        llama_cpp.llama_memory_seq_cp(memoria_da_placa, vaga, 0, -1, -1)
        self.n_tokens = len(lidos)
        self.input_ids[: len(lidos)] = lidos
        return len(lidos)

    def guardar(self, tokens):
        """Copia a conversa viva (que leu exatamente `tokens`) pra uma vaga; sem vaga livre, reusa a da memória menos usada, menos a do começo fixo."""
        memoria_da_placa = llama_cpp.llama_get_memory(self._ctx.ctx)
        tokens = list(tokens)
        vaga = next((v for v, lidos in self.memorias.items() if lidos == tokens), None)
        if vaga is None:
            livres = [v for v in self.vagas if v not in self.memorias]
            vaga = livres[0] if livres else self._vaga_que_sai()
        self.memorias.pop(vaga, None)
        llama_cpp.llama_memory_seq_rm(memoria_da_placa, vaga, -1, -1)
        llama_cpp.llama_memory_seq_cp(memoria_da_placa, 0, vaga, -1, -1)
        self.memorias[vaga] = tokens

    def _vaga_que_sai(self):
        """Devolve a vaga da memória menos usada, tirando a mais curta (o começo fixo, que serve pra qualquer conversa)."""
        mais_curta = min(self.memorias, key=lambda vaga: len(self.memorias[vaga]))
        return next(vaga for vaga in self.memorias if vaga != mais_curta)
