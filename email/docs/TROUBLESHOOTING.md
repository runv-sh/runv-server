# Resolução de problemas — email runv.club

## Mailgun API — 401 / 403

- API key errada ou revogada; ou key sem permissão para o **domínio** indicado.
- Confirme região **US vs EU** (URL base no JSON deve coincidir com a conta).

## Mailgun API — 400

- `From` não autorizado para o domínio; campos obrigatórios em falta; domínio não verificado no Mailgun.

## Mailgun API — 404

- Domínio incorrecto no path `/v3/.../messages` ou região trocada (US/EU).

## Mailgun — timeout / rede

- Firewall de saída, DNS, ou problemas TLS. Teste conectividade HTTPS ao host `api.mailgun.net` ou `api.eu.mailgun.net`.

## Mailgun — `entre` não envia

- Confirme `email_package_root` em `/etc/runv-email.json` aponta para a pasta `email/` do deploy **ou** defina `RUNV_EMAIL_ROOT` no ambiente do serviço.
- Confirme `backend` é `mailgun` (ou domínio+região presentes sem `backend: sendmail`).

## Legado — autenticação SMTP falha

- Confirme `user` no `msmtprc` e `login` no `.netrc` para o mesmo `machine <host>` que o **host** SMTP.
- Ver `/var/log/msmtp.log` (sem publicar dados sensíveis).

## Legado — TLS / STARTTLS

- Porta **587** + `tls on` + `tls_starttls on`; **465** muitas vezes `tls on` + `tls_starttls off`.
- Confirme `ca-certificates` instalado.

## `sendmail` não encontrado (modo legado)

- Instale `msmtp-mta`: `apt-get install -y msmtp-mta`.
- Em modo **Mailgun**, `sendmail` não é necessário para `lib.mailer.send_mail`.

## `mail` não funciona (legado)

- Instale `bsd-mailx`.

## Template ausente (`lib/mailer.py`)

- Defina `RUNV_EMAIL_ROOT` para a pasta **`email/`** do repositório.

## Permissões em `/root/.netrc` (legado)

- **600**, root. `sudo chmod 600 /root/.netrc && sudo chown root:root /root/.netrc`.

## Permissões em segredos Mailgun

- `/etc/runv-email.secrets.json` deve ser **0600** root. Nunca world-readable.

## `passwordeval` / `netrc_password.py` (legado)

- `/usr/local/lib/runv-email/netrc_password.py` — reinstalar com `configure_msmtp_legacy.py`.

## `--test` diz que falta estado

- Corra primeiro `configure_mailgun.py` (ou `configure_msmtp_legacy.py` no modo SMTP) **sem** `--test` para criar `/etc/runv-email.json`.
