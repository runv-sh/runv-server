# Administração — email runv.club

**Predefinição:** Mailgun HTTP API (`configure_mailgun.py`). Secção final: **legado SMTP/msmtp**.

## Mailgun — alterar remetente (From)

1. Edite `/etc/runv-email.json` — campo `default_from`.
2. O endereço deve estar autorizado no domínio Mailgun configurado.
3. Valide: `sudo python3 configure_mailgun.py --test`.

**Não** coloque a API key neste ficheiro.

## Mailgun — alterar email do administrador

1. Edite `admin_email` em `/etc/runv-email.json`.
2. Actualize também `admin_email` em `/opt/runv/terminal/config.toml` se usar o fluxo **entre**.

## Mailgun — rodar API key ou região

1. Para nova key: edite `/etc/runv-email.secrets.json` (0600) **ou** defina `RUNV_MAILGUN_API_KEY` no ambiente do processo.
2. Para mudar domínio/região: edite `/etc/runv-email.json` (`mailgun_domain`, `mailgun_region`, `api_base_url` coerente: `https://api.mailgun.net` vs `https://api.eu.mailgun.net`).
3. Recomendado: voltar a correr `sudo python3 configure_mailgun.py --force` para prompts guiados.

## Mailgun — reenviar teste

```bash
sudo python3 /caminho/runv-server/email/configure_mailgun.py --test
```

## Legado SMTP — alterar remetente (From)

1. Edite `/etc/msmtprc` na conta `runv`: linha `from ...`.
2. Actualize `/etc/runv-email.json` campo `default_from`.
3. Valide com `sudo python3 configure_msmtp_legacy.py --test` ou envio via `mail`.

## Legado SMTP — credenciais

- Senha/token **só** em `/root/.netrc` (ou `configure_msmtp_legacy.py` com `--force`).
- **Nunca** coloque senhas em `/etc/runv-email.json` em claro.

## Integrar outros scripts

Ver [INTEGRATION.md](INTEGRATION.md). Resumo: `RUNV_EMAIL_ROOT` ou `email_package_root` no JSON; usar `lib.mailer.send_mail`.

## Aliases msmtp (só legado)

- **msmtp** expande aliases — útil para `mail root` → admin.
- **`newaliases`** (estilo Sendmail) **não** actualiza `/etc/msmtp_aliases`.

## Log (legado)

- `/var/log/msmtp.log` quando usa msmtp.
