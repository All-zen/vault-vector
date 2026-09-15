"""Reranker por modelo de instrucao local, via Ollama.

Existe porque a faixa media nao se resolve com numero de similaridade. Ruido
ocupa 0.387-0.527 e pergunta legitima com vocabulario diferente ocupa
0.435-0.607: as duas populacoes se sobrepoem e nenhum corte as separa. O que
falta ao cosseno e ler a pergunta e o trecho JUNTOS, e e exatamente isso que
um cross-encoder faz.

Por que nao um cross-encoder de verdade (bge-reranker-v2-m3): o Ollama 0.34
nao tem endpoint de rerank. Medido em 15/09 com o GGUF da comunidade:
/api/generate devolve 500 'the current context does not logits computation',
/api/embed e /v1/embeddings devolvem 501 'This server does not support
embeddings'. Um cross-encoder nao emite token, emite o logit de uma cabeca de
classificacao, e nenhum caminho do Ollama expoe esse logit. Sem porta de
saida, o modelo certo para a tarefa fica inutilizavel aqui.

A saida foi um modelo de instrucao pequeno julgando o par. Duas medicoes de
15/09 decidiram o formato:

  - NOTA DE 0 A 10, nao rotulo. Com SIM/PARCIAL/NAO o juiz reprovou as DUAS
    perguntas legitimas do teste (uma 'NAO', outra 'PARCIAL') e acertou so o
    ruido. E a mesma falha do piso de similaridade: regua binaria derruba
    pergunta boa. Com nota numerica: legitimas 6 e 6, ruido 0 e 0.

  - CORTE EM 600 CARACTERES. Com 350, a resposta certa sobre queda de energia
    caiu de 6 para 3 e mudaria de faixa. Com 600 volta para 6 sem custo
    perceptivel de latencia.

Custo medido, CPU pura, sem GPU, qwen2.5:3b-instruct, cache quente:
0,3 a 1,7 s por trecho, ~300 tokens de prompt. O gargalo e o processamento do
prompt a ~90 tokens/s, nao a geracao, que leva ~200 ms. Por isso o trecho vai
cortado e so a faixa media e julgada.

Falha aqui nunca derruba a busca. Ollama fora do ar, modelo ausente, timeout
ou resposta ilegivel devolvem None e o resultado sai como saia antes, com a
ressalva de faixa media que ja existia.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

SISTEMA = (
    "Voce avalia o quanto um trecho de nota ajuda a responder uma pergunta. "
    "Responda APENAS um numero inteiro de 0 a 10. "
    "10 = responde direto. "
    "6 a 9 = contem parte da resposta ou o dado que a pergunta pede. "
    "3 a 5 = mesmo assunto, sem a resposta. "
    "0 a 2 = assunto diferente, apesar de palavras em comum."
)

# \d+ e nao \d{1,2} de proposito: com {1,2} a resposta "100" casaria "10" e
# viraria nota maxima. Pega o numero INTEIRO e deixa a faixa reprovar.
_NUM_RE = re.compile(r"\d+")


class OllamaJudge:
    """Julga pares (pergunta, trecho) com um modelo de instrucao local."""

    def __init__(
        self,
        url: str = "http://127.0.0.1:11434",
        model: str = "qwen2.5:3b-instruct",
        timeout: float = 30.0,
        max_chars: int = 600,
        num_thread: int = 0,
    ):
        self.url = url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_chars = max_chars
        self.num_thread = num_thread

    # ----------------------------------------------------------------- http
    def _gerar(self, prompt: str) -> str | None:
        opcoes = {"temperature": 0, "num_predict": 3}
        if self.num_thread:
            opcoes["num_thread"] = self.num_thread
        corpo = json.dumps(
            {
                "model": self.model,
                "system": SISTEMA,
                "prompt": prompt,
                "stream": False,
                "options": opcoes,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.url}/api/generate",
            data=corpo,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8")).get("response")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
            # Fail-open de proposito: o reranker melhora a resposta, nao e
            # requisito dela. Ollama fora do ar nao pode derrubar a busca.
            return None
        except (ValueError, json.JSONDecodeError):
            return None

    # ------------------------------------------------------------------ api
    def nota(self, query: str, texto: str) -> int | None:
        """Nota de 0 a 10, ou None se o juiz nao respondeu coisa legivel."""
        prompt = (
            f"PERGUNTA:\n{query}\n\n"
            f"TRECHO:\n{texto[: self.max_chars]}\n\n"
            "Nota (0-10):"
        )
        bruto = self._gerar(prompt)
        if not bruto:
            return None
        achado = _NUM_RE.search(bruto)
        if not achado:
            return None
        valor = int(achado.group())
        # Modelo pequeno as vezes devolve 100 ou 55. Fora da escala e resposta
        # invalida, nao nota alta: descartar e melhor que inventar sentido.
        return valor if 0 <= valor <= 10 else None

    def notas(self, query: str, textos: list[str]) -> list[int | None]:
        return [self.nota(query, t) for t in textos]

    def disponivel(self) -> bool:
        """O modelo do juiz esta baixado neste Ollama."""
        try:
            with urllib.request.urlopen(f"{self.url}/api/tags", timeout=5) as resp:
                tags = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return False
        nomes = [m.get("name", "") for m in tags.get("models", [])]
        base = {n.split(":")[0] for n in nomes}
        return self.model in nomes or self.model.split(":")[0] in base
