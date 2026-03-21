# Administração — email runv.club

## Alterar remetente padrão (From)

1. Edite `/etc/msmtprc` na conta `runv`: linha `from ...`.
2. Actualize `/etc/runv-email.json` campo `default_from` (consistência com `--test` e documentação interna).
3. Valide com `sudo python3 configure_msmtp.py --test` ou envio manual via `mail`.

Faça **cópia de segurança** antes: `sudo cp /etc/msmtprc /etc/msmtprc.bak.$(date +%s)`.

## Alterar email do administrador

1. Edite `/etc/msmtp_aliases` — linhas `root:`, `cron:`, `default:` para o novo endereço.
2. Actualize `admin_email` em `/etc/runv-email.json`.
3. Actualize também `admin_email` em `/opt/runv/terminal/config.toml` se usar o fluxo **entre**.

## Trocar host, porta ou TLS

1. Edite `/etc/msmtprc` (`host`, `port`, `tls`, `tls_starttls`, `user` se aplicável).
2. Se mudar o **hostname** SMTP, actualize `/root/.netrc`:
   - a linha `machine` deve coincidir com o novo `host`;
   - ou volte a correr `configure_msmtp.py` (com `--force`) para regenerar de forma coerente.

## Credenciais

- Senha/token **só** em `/root/.netrc` (ou volte a correr `configure_msmtp.py` para reprompt seguro).
- **Nunca** coloque senhas em `/etc/runv-email.json` nem em `msmtprc` em claro.

## Reenviar email de teste

```bash
sudo python3 /caminho/runv-server/email/configure_msmtp.py --test
```

Requer `/etc/runv-email.json` e configuração msmtp válida.

## Integrar outros scripts

Ver [INTEGRATION.md](INTEGRATION.md). Resumo: definir `RUNV_EMAIL_ROOT` e usar `lib.mailer.send_mail` ou funções de template.

## Aliases e limitações

- **msmtp** expande aliases conforme o seu ficheiro `aliases` — útil para `mail root` redirecionar para o admin.
- Isto **não** substitui um servidor de correio completo: endereços locais fictícios só funcionam na medida em que o `mail`/pipeline os passa e o msmtp resolve via aliases.
- **`newaliases`** (estilo Sendmail) **não** actualiza este ficheiro.

## Log

- Ficheiro configurado em `msmtprc`: por defeito `/var/log/msmtp.log`.
- Permissões: criado pelo instalador; ajuste se necessário para rotação (logrotate).
