#!/usr/bin/env python3
"""
Prepara /etc/skel para novos usuários do runv.club (Debian).
Executar como root. Não cria usuários, não altera Apache nem SSH.

Versão 0.02 — runv.club
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Final

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from admin_guard import ensure_admin_cli

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

SKEL_ROOT: Final[Path] = Path("/etc/skel")
PUBLIC_HTML_DIR: Final[Path] = SKEL_ROOT / "public_html"
INDEX_HTML: Final[Path] = PUBLIC_HTML_DIR / "index.html"
README_MD: Final[Path] = SKEL_ROOT / "README.md"

VERSION: Final[str] = "0.02"

EXIT_OK: Final[int] = 0
EXIT_ERROR: Final[int] = 1
EXIT_PRIVILEGE: Final[int] = 2


# ---------------------------------------------------------------------------
# Validação de privilégios
# ---------------------------------------------------------------------------


def validate_privileges() -> None:
    """Exige UID 0 (root) para alterar /etc/skel."""
    if os.geteuid() != 0:
        print(
            "Erro: este script precisa ser executado como root (sudo).",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_PRIVILEGE)


# ---------------------------------------------------------------------------
# Geração de conteúdo
# ---------------------------------------------------------------------------


def render_index_html() -> str:
    """HTML estático com CSS embutido; visual simples e textual, sem dependências externas."""
    return """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>A sua página no runv.club</title>
  <style>
    :root {
      --bg: #f4f0e8;
      --fg: #1a1a12;
      --muted: #5c5a52;
      --accent: #2d6a4f;
      --rule: #c4c0b8;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 1.5rem 1rem 3rem;
      font-family: "Georgia", "Times New Roman", serif;
      font-size: 1rem;
      line-height: 1.55;
      color: var(--fg);
      background: var(--bg);
      max-width: 38rem;
      margin-left: auto;
      margin-right: auto;
    }
    h1 {
      font-size: 1.35rem;
      font-weight: normal;
      letter-spacing: 0.02em;
      border-bottom: 1px solid var(--rule);
      padding-bottom: 0.5rem;
      margin-top: 0;
    }
    .tagline {
      font-style: italic;
      color: var(--muted);
      margin: 0.25rem 0 1.25rem;
      font-size: 0.95rem;
    }
    pre, code {
      font-family: ui-monospace, "Cascadia Mono", "Consolas", monospace;
      font-size: 0.88rem;
    }
    pre {
      background: #e8e4dc;
      border: 1px solid var(--rule);
      padding: 0.75rem 1rem;
      overflow-x: auto;
      margin: 0.75rem 0;
    }
    section {
      margin: 1.5rem 0;
    }
    h2 {
      font-size: 1.05rem;
      font-weight: normal;
      margin: 0 0 0.5rem;
      color: var(--accent);
    }
    .url-box {
      border-left: 3px solid var(--accent);
      padding-left: 0.75rem;
      margin: 0.75rem 0;
    }
    footer {
      margin-top: 2rem;
      padding-top: 0.75rem;
      border-top: 1px solid var(--rule);
      font-size: 0.85rem;
      color: var(--muted);
    }
  </style>
</head>
<body>
  <h1>Bem-vindo ao runv.club</h1>
  <p class="tagline">Um cantinho na rede — pubnix runv.club.</p>

  <p>
    Esta página foi gerada automaticamente quando sua conta foi criada.
    Você pode editá-la quando quiser: o arquivo fica em
    <code>~/public_html/index.html</code>.
  </p>

  <section>
    <h2>Próximos passos</h2>
    <ol>
      <li>Entrar no servidor por SSH.</li>
      <li>Ir para a pasta do site pessoal.</li>
      <li>Editar este HTML com um editor de texto.</li>
      <li>Salvar e recarregar a página no navegador.</li>
    </ol>
  </section>

  <section>
    <h2>Comandos úteis</h2>
    <pre>cd ~/public_html
nano index.html
ls -la</pre>
  </section>

  <section>
    <h2>Sua URL</h2>
    <p>Quando estiver no ar, seu site costuma aparecer em:</p>
    <div class="url-box">
      <code>http://runv.club/~SEU_USUARIO/</code>
    </div>
    <p>Substitua <code>SEU_USUARIO</code> pelo seu nome de usuário Unix.</p>
  </section>

  <footer>
    runv.club — servidor multiusuário. Edite esta página à vontade.
  </footer>
</body>
</html>
"""


def render_readme_md() -> str:
    """README em Markdown para a home inicial (copiado de /etc/skel)."""
    return """# Bem-vindo ao runv.club

O **runv.club** é um servidor multiutilizador: cada pessoa tem uma conta Unix e um
site pessoal servido pelo Apache.

## Onde fica o seu site

- **Pasta:** `~/public_html/`
- **Arquivo principal:** `~/public_html/index.html` — edite este primeiro.

## URL pública

Depois de publicar, seu site costuma ficar em:

```text
http://runv.club/~SEU_USUARIO/
```

Troque `SEU_USUARIO` pelo seu nome de usuário Unix (o mesmo do login).

## Permissões (referência)

Após a criação da conta, costuma ser assim para o site aparecer:

| Caminho | Permissão típica |
|---------|------------------|
| `~` (home) | `755` |
| `~/public_html` | `755` |
| `~/public_html/index.html` | `644` |

Se algo não carregar no navegador, peça ajuda a um admin e mencione estas pastas.

## Comandos básicos

```bash
cd ~/public_html
nano index.html
ls -la
```

## Servidor multiusuário

- Muitas pessoas usam a mesma máquina. **Não guarde segredos** em arquivos dentro de
  `public_html` ou em qualquer lugar que o site possa expor.
- O que está em `public_html` é pensado para ser **público na web**.

## Dúvidas

Leia também a documentação do projeto ou fale com a equipe no canal indicado pelo runv.club.

— Equipe runv.club
"""


# ---------------------------------------------------------------------------
# Diretórios e ficheiros
# ---------------------------------------------------------------------------


def ensure_directories(
    dry_run: bool,
    verbose: bool,
) -> tuple[list[Path], list[Path]]:
    """
    Garante que os diretórios necessários existem.
    Retorna (criados, já existentes).
    """
    created: list[Path] = []
    existed: list[Path] = []
    for d in (SKEL_ROOT, PUBLIC_HTML_DIR):
        if d.is_dir():
            existed.append(d)
            if verbose:
                print(f"  [dir] já existe: {d}")
            continue
        if dry_run:
            created.append(d)
            print(f"  [dry-run] criaria diretório: {d}")
            continue
        d.mkdir(parents=True, exist_ok=True)
        created.append(d)
        print(f"  [dir] criado: {d}")
    return created, existed


def apply_permissions(paths: list[Path], verbose: bool) -> None:
    """Aplica modos 755 para diretórios e 644 para ficheiros."""
    for p in paths:
        if not p.exists():
            continue
        if p.is_dir():
            mode = 0o755
        else:
            mode = 0o644
        if verbose:
            print(f"  [chmod] {oct(mode)} {p}")
        try:
            p.chmod(mode)
        except OSError as e:
            print(f"Erro ao definir permissões em {p}: {e}", file=sys.stderr)
            raise SystemExit(EXIT_ERROR) from e


def write_file_safe(
    path: Path,
    content: str,
    *,
    force: bool,
    dry_run: bool,
    verbose: bool,
) -> str:
    """
    Escreve conteúdo se o ficheiro não existir ou se force=True.
    Retorna: 'created' | 'updated' | 'preserved'
    """
    existed_before = path.is_file()

    if dry_run:
        if existed_before and not force:
            print(f"  [dry-run] preservaria (sem alterar; use --force para regenerar): {path}")
            return "preserved"
        verb = "atualizaria" if existed_before else "criaria"
        print(f"  [dry-run] {verb} arquivo: {path}")
        return "updated" if existed_before else "created"

    if existed_before and not force:
        hint = " (use --force para sobrescrever)" if verbose else ""
        print(f"  [file] preservado{hint}: {path}")
        return "preserved"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    label = "atualizado" if existed_before else "criado"
    print(f"  [file] {label}: {path}")
    return "updated" if existed_before else "created"


def run_dry_run(verbose: bool) -> int:
    """Mostra o plano sem escrever em disco (não exige root)."""
    print("Modo dry-run — nenhuma alteração em disco.\n")
    ensure_directories(dry_run=True, verbose=verbose)
    write_file_safe(
        INDEX_HTML, render_index_html(), force=False, dry_run=True, verbose=verbose
    )
    write_file_safe(
        README_MD, render_readme_md(), force=False, dry_run=True, verbose=verbose
    )
    print("\nResumo: nada foi gravado. Execute sem --dry-run como root para aplicar.")
    return EXIT_OK


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepara /etc/skel para novos usuários do runv.club (Debian).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="mostra o que seria feito sem alterar arquivos",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="mais detalhes na saída",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="sobrescreve index.html e README.md se já existirem",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION} — runv.club",
    )
    args = parser.parse_args()
    ensure_admin_cli(
        script_name=Path(__file__).name,
        dry_run=bool(args.dry_run),
    )

    if args.dry_run:
        return run_dry_run(args.verbose)

    validate_privileges()

    print("skel.py — preparando /etc/skel para runv.club\n")

    dirs_created, _dirs_existed = ensure_directories(dry_run=False, verbose=args.verbose)

    results: dict[str, str] = {}
    for label, path, content in (
        ("index.html", INDEX_HTML, render_index_html()),
        ("README.md", README_MD, render_readme_md()),
    ):
        results[label] = write_file_safe(
            path,
            content,
            force=args.force,
            dry_run=False,
            verbose=args.verbose,
        )

    # Permissões
    to_chmod = [PUBLIC_HTML_DIR, INDEX_HTML, README_MD]
    print("\nAplicando permissões...")
    apply_permissions(to_chmod, verbose=args.verbose)

    # Resumo
    print("\n--- Resumo ---")
    print(f"  Diretórios criados agora: {len(dirs_created)}")
    if dirs_created:
        for d in dirs_created:
            print(f"    - {d}")
    print(f"  index.html: {results.get('index.html', '?')}")
    print(f"  README.md:  {results.get('README.md', '?')}")
    print("  Permissões: public_html → 755; index.html e README.md → 644")

    print("\n--- Próximos passos sugeridos ---")
    print("  1. Crie um usuário de teste: sudo adduser --disabled-password testuser")
    print("  2. Verifique se a home copiou de /etc/skel:")
    print("       ls -la ~/  (como esse usuário)")
    print("       ls -la ~/public_html/")
    print("  3. Teste no navegador: http://runv.club/~testuser/ (ajuste DNS/host)")

    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
