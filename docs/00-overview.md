# Visão geral

[← Índice](README.md)

## O que é o runv-server

Repositório de **scripts (principalmente Python 3, biblioteca padrão)**, conteúdo estático web e documentação para operar um servidor **pubnix** estilo tilde (**runv.club**) em **Debian**. Não é uma aplicação web monolítica (sem `package.json` na raiz do produto).

## Âmbito do repositório

- **Infraestrutura:** bootstrap (`starthere.py`), quotas ext4, Apache, UFW, ferramentas globais (`tools.py`).
- **Site público:** landing estática em `site/public/`, geração de Apache (`genlanding.py`), dados públicos de membros (`build_directory.py`).
- **Email transacional:** Mailgun HTTP por defeito; modo legado SMTP/msmtp (`email/`).
- **Pedidos de conta:** fluxo SSH ao utilizador `entre` (`terminal/`) — **fila em JSON**, sem criar contas Unix automaticamente.
- **Provisionamento canónico:** `scripts/admin/create_runv_user.py` cria utilizador Unix, home, jail, quota, metadados.

## Resumo arquitetural

| Componente | Responsabilidade |
|------------|------------------|
| `terminal/` | Recolher, validar, enfileirar pedidos; **não** faz `adduser` de membros. |
| `create_runv_user.py` | **Única** fonte canónica do fluxo de criação de conta membro (ordem documentada na docstring). |
| `users.json` | Metadados dos membros no servidor (`/var/lib/runv/users.json`). |
| Fila `entre-queue/` | Pedidos pendentes de revisão humana antes do provisionamento. |
| `build_directory.py` | Lê `users.json` → gera `members.json` **filtrado** para o site. |

Diagrama: [diagrams/architecture.mmd](diagrams/architecture.mmd).

## Ciclo de vida de um novo membro

1. Visitante liga `ssh entre@…` e preenche o fluxo guiado.
2. Gera-se um ficheiro JSON na fila (`/var/lib/runv/entre-queue/`).
3. **Admin** revê o pedido e executa `create_runv_user.py` (root).
4. Actualiza-se `users.json`; opcionalmente regera-se `DocumentRoot/data/members.json` (constelação na landing).
5. O membro aparece na lista pública **só** com campos não sensíveis.

Diagrama: [diagrams/member-flow.mmd](diagrams/member-flow.mmd).

## Fronteira dados públicos / privados

- **Público (`members.json`):** apenas o que `build_directory.py` escreve: `username`, `since`, `path`, opcionalmente `homepage_mtime` (com `--homes-root`). Ver [07-public-members-directory.md](07-public-members-directory.md).
- **Privado:** email, fingerprint de chave, quotas detalhadas, campos internos de `users.json` **não** são copiados para o JSON público (garantido no código de `build_directory.py`).

## Fontes de verdade

1. **Código** dos scripts referidos neste índice.
2. O **`INSTALL.md` da raiz** e a documentação `.md` nos módulos foram **substituídos** por esta árvore `docs/` (conteúdo absorvido e harmonizado; ver `DOCS_REBUILD_CHANGELOG.md`).
3. Docstrings de `starthere.py`, `create_runv_user.py`, `setup_entre.py`, `genlanding.py`, etc.
