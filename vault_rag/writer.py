"""Escrita no vault, com as travas que um arquivo de trabalho merece.

Quatro garantias, nesta ordem de importancia:

1. Nada e sobrescrito sem copia. A versao anterior vai para _historico/ antes
   de qualquer gravacao, entao nenhum erro aqui e irreversivel.
2. Edicao exige alvo unico. Trocar um trecho que aparece duas vezes na nota e
   recusado, porque nao da para saber qual era o certo.
3. Edicao concorrente e detectada. Se a nota mudou no disco depois da leitura
   (o Obsidian estava aberto, por exemplo), a gravacao para e avisa.
4. So dentro do vault, e so em pasta viva. Lixeira e arquivo morto sao
   recusados.
"""

from __future__ import annotations

import shutil
import time
from datetime import datetime
from pathlib import Path

from .api import _safe_path, resolve_note
from .config import Config

# Pastas onde escrever seria erro por definicao.
PASTAS_BLOQUEADAS = {
    "_to_delete",
    "_arquivo",
    "_historico",
    ".obsidian",
    ".git",
    "_tools",
    "Backups",
}

HISTORICO = "_historico"


class WriteError(RuntimeError):
    pass


class ConflitoDeEdicao(WriteError):
    """A nota mudou no disco entre a leitura e a gravacao.

    Separada das outras recusas porque pede outra reacao: nao e pedido
    errado, e preciso ler de novo antes de gravar.
    """


def _validar(cfg: Config, rel: str) -> tuple[Path, str]:
    """Resolve o caminho e recusa o que nao pode ser escrito."""
    rel = rel.replace("\\", "/").strip().lstrip("/")
    if not rel:
        raise WriteError("caminho vazio")
    if not rel.lower().endswith(".md"):
        rel += ".md"

    partes = rel.split("/")[:-1]
    for parte in partes:
        if parte in PASTAS_BLOQUEADAS or parte.startswith("."):
            raise WriteError(
                f"'{parte}' e pasta de lixeira, arquivo morto ou sistema — "
                "nao escrevo ali. Escolha uma secao viva do vault."
            )

    destino = _safe_path(cfg, rel)  # ja garante que nao sai do vault
    return destino, rel


def _guardar_historico(cfg: Config, destino: Path, rel: str) -> Path | None:
    """Copia a versao atual para _historico/ antes de mexer nela."""
    if not destino.is_file():
        return None
    agora = datetime.now()
    pasta = cfg.vault / HISTORICO / agora.strftime("%Y-%m-%d")
    pasta.mkdir(parents=True, exist_ok=True)
    base = rel.replace("/", "__")[:-3] + f".{agora:%H%M%S}"
    copia = pasta / f"{base}.md"
    # Duas edicoes no mesmo segundo colidiriam e a segunda copia apagaria a
    # primeira — justamente o historico que existe para nao se perder.
    sufixo = 2
    while copia.exists():
        copia = pasta / f"{base}-{sufixo}.md"
        sufixo += 1
    shutil.copy2(destino, copia)
    return copia


def _checar_mtime(destino: Path, esperado: float | None) -> None:
    if esperado is None or not destino.is_file():
        return
    atual = destino.stat().st_mtime
    # Tolerancia de 1s: alguns sistemas de arquivo arredondam o mtime.
    if abs(atual - esperado) > 1.0:
        raise ConflitoDeEdicao(
            f"a nota mudou no disco desde que foi lida "
            f"(esperava mtime {esperado:.0f}, achei {atual:.0f}). "
            "Provavelmente esta aberta no Obsidian. Leia de novo antes de gravar."
        )


def _reindexar(cfg: Config, rel: str) -> str:
    """Reindexa so a nota que acabou de mudar."""
    from .indexer import reindex_one

    try:
        chunks = reindex_one(cfg, rel)
        return f"{chunks} trecho(s) reindexado(s)"
    except Exception as exc:
        return f"gravado, mas a reindexacao falhou ({exc}) — rode 'vault-rag index'"


def edit_note(
    cfg: Config,
    ref: str,
    old_str: str,
    new_str: str,
    *,
    expected_mtime: float | None = None,
    replace_all: bool = False,
) -> dict:
    """Troca um trecho exato dentro de uma nota existente."""
    resolvido = resolve_note(cfg, ref) or ref
    destino, rel = _validar(cfg, resolvido)
    if not destino.is_file():
        raise WriteError(f"nota nao encontrada: {ref}")
    if not old_str:
        raise WriteError("old_str vazio — use vault_append para acrescentar")

    texto = destino.read_text(encoding="utf-8")
    ocorrencias = texto.count(old_str)
    if ocorrencias == 0:
        raise WriteError(
            "o trecho a substituir nao existe na nota. Confira espacos, "
            "acentos e quebras de linha."
        )
    if ocorrencias > 1 and not replace_all:
        raise WriteError(
            f"o trecho aparece {ocorrencias} vezes na nota. Inclua as linhas "
            "em volta para tornar o alvo unico, ou passe replace_all=true."
        )

    _checar_mtime(destino, expected_mtime)
    copia = _guardar_historico(cfg, destino, rel)
    destino.write_text(
        texto.replace(old_str, new_str) if replace_all else texto.replace(old_str, new_str, 1),
        encoding="utf-8",
    )
    return {
        "path": rel,
        "acao": f"substituiu {ocorrencias if replace_all else 1} ocorrencia(s)",
        "historico": str(copia.relative_to(cfg.vault)) if copia else None,
        "indice": _reindexar(cfg, rel),
    }


def append_note(
    cfg: Config, ref: str, content: str, *, expected_mtime: float | None = None
) -> dict:
    """Acrescenta texto ao fim de uma nota, criando se nao existir."""
    resolvido = resolve_note(cfg, ref) or ref
    destino, rel = _validar(cfg, resolvido)
    if not content.strip():
        raise WriteError("conteudo vazio")

    existia = destino.is_file()
    _checar_mtime(destino, expected_mtime)
    copia = _guardar_historico(cfg, destino, rel)

    if existia:
        atual = destino.read_text(encoding="utf-8").rstrip("\n")
        novo = f"{atual}\n\n{content.strip()}\n"
    else:
        destino.parent.mkdir(parents=True, exist_ok=True)
        novo = content.strip() + "\n"
    destino.write_text(novo, encoding="utf-8")

    return {
        "path": rel,
        "acao": "acrescentou ao fim" if existia else "criou a nota",
        "historico": str(copia.relative_to(cfg.vault)) if copia else None,
        "indice": _reindexar(cfg, rel),
    }


def write_note(
    cfg: Config,
    ref: str,
    content: str,
    *,
    overwrite: bool = False,
    expected_mtime: float | None = None,
) -> dict:
    """Cria uma nota. So sobrescreve com overwrite explicito."""
    destino, rel = _validar(cfg, ref.replace("\\", "/"))
    if not content.strip():
        raise WriteError("conteudo vazio")

    existia = destino.is_file()
    if existia and not overwrite:
        raise WriteError(
            f"'{rel}' ja existe. Use vault_edit para alterar um trecho, "
            "vault_append para acrescentar, ou passe overwrite=true se a "
            "intencao e mesmo substituir a nota inteira."
        )

    _checar_mtime(destino, expected_mtime)
    copia = _guardar_historico(cfg, destino, rel)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(content.rstrip("\n") + "\n", encoding="utf-8")

    return {
        "path": rel,
        "acao": "sobrescreveu" if existia else "criou",
        "historico": str(copia.relative_to(cfg.vault)) if copia else None,
        "indice": _reindexar(cfg, rel),
    }


def versoes(cfg: Config, ref: str) -> list[dict]:
    """Copias desta nota guardadas em _historico/, da mais nova para a mais velha.

    O nome da copia e o caminho com '/' trocado por '__' mais a hora
    (_guardar_historico), dentro de uma pasta por dia. A lixeira fica de
    fora: nota apagada nao tem "versao anterior", tem recuperacao.
    """
    resolvido = resolve_note(cfg, ref) or ref
    _, rel = _validar(cfg, resolvido)
    base = rel.replace("/", "__")[:-3] + "."
    raiz = cfg.vault / HISTORICO
    if not raiz.is_dir():
        return []

    achadas = []
    for dia in raiz.iterdir():
        if not dia.is_dir() or dia.name == "lixeira":
            continue
        for copia in dia.iterdir():
            # startswith, e nao glob: nome de nota pode ter [ ] e * dentro.
            if not copia.name.startswith(base) or not copia.name.endswith(".md"):
                continue
            hora = copia.name[len(base):-3].split("-")[0]
            if len(hora) != 6 or not hora.isdigit():
                continue  # outra nota cujo nome comeca igual a este
            achadas.append({
                "versao": copia.relative_to(cfg.vault).as_posix(),
                "quando": f"{dia.name} {hora[:2]}:{hora[2:4]}:{hora[4:]}",
                "bytes": copia.stat().st_size,
            })
    return sorted(achadas, key=lambda v: (v["quando"], v["versao"]), reverse=True)


def restaurar(cfg: Config, ref: str, versao: str, *, expected_mtime: float | None = None) -> dict:
    """Volta a nota para uma copia do historico.

    Passa pelo write_note, entao a versao atual vai para o historico antes:
    restaurar tambem tem volta.
    """
    resolvido = resolve_note(cfg, ref) or ref
    _, rel = _validar(cfg, resolvido)
    if not any(v["versao"] == versao for v in versoes(cfg, rel)):
        raise WriteError(f"'{versao}' nao e uma versao guardada de {rel}")
    conteudo = (cfg.vault / versao).read_text(encoding="utf-8")
    r = write_note(cfg, rel, conteudo, overwrite=True, expected_mtime=expected_mtime)
    r["acao"] = f"restaurou a versao de {versao.split('/')[1]}"
    return r


def note_mtime(cfg: Config, ref: str) -> float | None:
    """mtime atual da nota, para usar depois como expected_mtime."""
    resolvido = resolve_note(cfg, ref) or ref
    try:
        destino, _ = _validar(cfg, resolvido)
    except WriteError:
        return None
    return destino.stat().st_mtime if destino.is_file() else None


def list_dir(cfg: Config, rel: str = "") -> dict:
    """Lista o conteudo de uma pasta do vault."""
    limpo = rel.replace("\\", "/").strip("/")
    if limpo:
        # Mesma regra da escrita: lixeira, arquivo morto e pasta de sistema
        # ficam fora da navegacao. O caminho exato de uma copia sai no
        # retorno do vault_delete, para quem precisar recuperar.
        for parte in limpo.split("/"):
            if parte in PASTAS_BLOQUEADAS or parte.startswith("."):
                raise WriteError(
                    f"'{parte}' e pasta de lixeira, arquivo morto ou sistema — "
                    "fica fora da navegacao."
                )
    base = cfg.vault if not limpo else _safe_path(cfg, limpo)
    if not base.is_dir():
        raise WriteError(f"pasta nao encontrada: {rel or '(raiz)'}")

    pastas, notas = [], []
    for item in sorted(base.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if item.name.startswith(".") or item.name in PASTAS_BLOQUEADAS:
            continue
        if item.is_dir():
            quantas = sum(1 for _ in item.rglob("*.md"))
            pastas.append({"nome": item.name, "notas": quantas})
        elif item.suffix.lower() == ".md":
            notas.append({"nome": item.name, "bytes": item.stat().st_size})
    return {
        "pasta": rel or "(raiz)",
        "subpastas": pastas,
        "notas": notas,
    }


def _reescrever_links(cfg: Config, de: str, para: str) -> int:
    """Aponta para o novo caminho os wikilinks que citavam o antigo.

    Mover uma nota sem isso deixa link quebrado espalhado pelo vault - e o
    Obsidian faz esse acerto ao renomear, entao a ferramenta tem que fazer.
    """
    import re as _re

    alvo_antigo = de[:-3] if de.endswith(".md") else de
    alvo_novo = para[:-3] if para.endswith(".md") else para
    stem_antigo = alvo_antigo.rsplit("/", 1)[-1]

    # Casa tanto o caminho completo quanto o nome curto, preservando o alias.
    padrao = _re.compile(
        r"\[\[(" + _re.escape(alvo_antigo) + "|" + _re.escape(stem_antigo) + r")((?:#|\|)[^\]]*)?\]\]"
    )
    tocadas = 0
    for caminho in cfg.vault.rglob("*.md"):
        rel_atual = caminho.relative_to(cfg.vault).as_posix()
        if any(p in PASTAS_BLOQUEADAS or p.startswith(".") for p in rel_atual.split("/")[:-1]):
            continue
        try:
            texto = caminho.read_text(encoding="utf-8")
        except OSError:
            continue
        novo = padrao.sub(lambda m: f"[[{alvo_novo}{m.group(2) or ''}]]", texto)
        if novo != texto:
            _guardar_historico(cfg, caminho, rel_atual)
            caminho.write_text(novo, encoding="utf-8")
            _reindexar(cfg, rel_atual)
            tocadas += 1
    return tocadas


def move_note(cfg: Config, origem: str, destino: str, *, atualizar_links: bool = True) -> dict:
    """Move ou renomeia uma nota, corrigindo os wikilinks que apontavam nela."""
    from .indexer import reindex_one
    from .store import Store

    resolvida = resolve_note(cfg, origem) or origem
    de_path, de_rel = _validar(cfg, resolvida)
    if not de_path.is_file():
        raise WriteError(f"nota nao encontrada: {origem}")
    para_path, para_rel = _validar(cfg, destino.replace("\\", "/"))
    if para_path.exists():
        raise WriteError(f"'{para_rel}' ja existe - escolha outro nome")

    _guardar_historico(cfg, de_path, de_rel)
    para_path.parent.mkdir(parents=True, exist_ok=True)
    de_path.rename(para_path)

    store = Store(cfg.db_path, cfg.embed_dim)
    try:
        store.delete_file(de_rel)
        store.commit()
    finally:
        store.close()
    reindex_one(cfg, para_rel)

    tocadas = _reescrever_links(cfg, de_rel, para_rel) if atualizar_links else 0
    return {
        "de": de_rel,
        "para": para_rel,
        "links_atualizados": tocadas,
        "indice": "reindexado",
    }


def delete_note(cfg: Config, ref: str) -> dict:
    """Manda a nota para a lixeira do historico e tira do indice.

    Nao apaga de verdade: o arquivo vai para _historico/lixeira/, de onde da
    para trazer de volta. Apagar mesmo fica a cargo de voce, no Explorer.
    """
    from .store import Store

    resolvida = resolve_note(cfg, ref) or ref
    caminho, rel = _validar(cfg, resolvida)
    if not caminho.is_file():
        raise WriteError(f"nota nao encontrada: {ref}")

    agora = datetime.now()
    lixeira = cfg.vault / HISTORICO / "lixeira" / agora.strftime("%Y-%m-%d")
    lixeira.mkdir(parents=True, exist_ok=True)
    base = rel.replace("/", "__")[:-3] + f".{agora:%H%M%S}"
    alvo = lixeira / f"{base}.md"
    sufixo = 2
    while alvo.exists():
        alvo = lixeira / f"{base}-{sufixo}.md"
        sufixo += 1
    shutil.move(str(caminho), str(alvo))

    store = Store(cfg.db_path, cfg.embed_dim)
    try:
        store.delete_file(rel)
        store.commit()
    finally:
        store.close()

    citacoes = sum(
        1
        for p in cfg.vault.rglob("*.md")
        if HISTORICO not in p.parts and rel[:-3].rsplit("/", 1)[-1] in p.read_text(
            encoding="utf-8", errors="replace"
        )
    )
    return {
        "path": rel,
        "lixeira": str(alvo.relative_to(cfg.vault)),
        "citada_por": citacoes,
    }
