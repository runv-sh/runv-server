# Documentação runv-server

Índice canónico do repositório **runv-server** (automação para pubnix Debian / runv.club). Tudo em **pt-BR**. Esta pasta é a **porta de entrada**; não dependa de ficheiros `.md` antigos nos módulos (foram removidos nesta reconstrução — ver `DOCS_REBUILD_CHANGELOG.md` na raiz).

## Ordem de leitura sugerida

1. [Visão geral](00-overview.md)
2. [Baseline Debian](01-server-baseline-debian.md)
3. [Acesso admin e SSH](02-admin-access-and-ssh.md)
4. [Caminhos e estado](03-paths-files-and-state.md)
5. [Bootstrap](04-bootstrap-and-base-system.md)
6. [Ferramentas globais](05-tools-and-system-experience.md)
7. [Site e Apache](06-site-and-apache.md)
8. [Membros públicos](07-public-members-directory.md)
9. [Email](08-email.md)
10. [Terminal entre](09-terminal-entre.md)
11. [Provisionamento e admin](10-user-provisioning-and-admin-ops.md)
12. [Operação diária](11-daily-operations.md)
13. [Segurança e privacidade](12-security-and-privacy.md)
14. [Resolução de problemas](13-troubleshooting.md)
15. [Smoke tests](14-smoke-tests-and-validation.md)
16. [Glossário e referência](15-glossary-and-reference.md)

## Mapa rápido

| Quero… | Documento |
|--------|-----------|
| Entender o que é o projeto | [00-overview.md](00-overview.md) |
| Preparar o servidor Debian | [01](01-server-baseline-debian.md), [04](04-bootstrap-and-base-system.md) |
| Instalar landing Apache | [06-site-and-apache.md](06-site-and-apache.md) |
| Lista de bolhas / `members.json` | [07-public-members-directory.md](07-public-members-directory.md) |
| Pedidos SSH `entre` | [09-terminal-entre.md](09-terminal-entre.md) |
| Criar conta membro | [10-user-provisioning-and-admin-ops.md](10-user-provisioning-and-admin-ops.md) |
| Email Mailgun / legado | [08-email.md](08-email.md) |

## Diagramas (Mermaid)

- [diagrams/architecture.mmd](diagrams/architecture.mmd)
- [diagrams/member-flow.mmd](diagrams/member-flow.mmd)

## Código-fonte

A documentação descreve scripts em `scripts/`, `terminal/`, `site/`, `tools/`, `email/`. As docstrings e `--help` dos scripts são fonte de verdade complementar (ver [14-smoke-tests-and-validation.md](14-smoke-tests-and-validation.md)).
