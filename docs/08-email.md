# Email (saída)

[← Índice](README.md)

## Arquitectura actual

- **Predefinição:** envio via **Mailgun HTTP API** (`email/configure_mailgun.py`).
- **Estado:** `/etc/runv-email.json`
- **Segredos:** `/etc/runv-email.secrets.json` (permissões restritas; não versionar).

## Modo legado

- SMTP via `msmtp` / `sendmail`: flags `--legacy-smtp` ou `configure_msmtp_legacy.py` (detalhes nas docstrings e `--help` dos scripts em `email/`).

## Biblioteca

- `email/lib/mailer.py` — envio reutilizável; templates em `email/templates/`.
- Variável `RUNV_EMAIL_ROOT` ou `email_package_root` no JSON para o fluxo `entre` localizar templates.

## Integração com `entre`

- Notificações ao admin usam `admin_email` no `config.toml` do terminal **ou** fallback em `/etc/runv-email.json` (comportamento verificado no código de `terminal/` + `email/lib`).

## O que o repo não é

- **Não** é MTA completo (não recebe correio para caixas locais de membros como produto deste repositório).

## Testes

- Existem testes em `email/tests/` (ex.: `test_mailgun_client.py`). Ver [14-smoke-tests-and-validation.md](14-smoke-tests-and-validation.md).

Próximo: [09-terminal-entre.md](09-terminal-entre.md).
