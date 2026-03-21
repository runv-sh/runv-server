# Resolução de problemas — email runv.club

## Autenticação SMTP falha

- Confirme `user` no `msmtprc` e `login` no `.netrc` para o mesmo `machine <host>` que o **host** SMTP.
- Teste credenciais com outro cliente (mesmo host/porta/TLS) para isolar.
- Ver `/var/log/msmtp.log` (sem publicar conteúdo com dados sensíveis).

## TLS / STARTTLS a falhar

- Combinações típicas: porta **587** + `tls on` + `tls_starttls on`; porta **465** muitas vezes `tls on` + `tls_starttls off`.
- Confirme `tls_trust_file /etc/ssl/certs/ca-certificates.crt` e pacote `ca-certificates` instalado.

## Erro de certificado

- Relógio do sistema correcto (`timedatectl`).
- Se o servidor usar certificado não padrão, a política de msmtp pode exigir ajuste (documentação msmtp — fora do âmbito normal runv).

## `sendmail` não encontrado

- Instale `msmtp-mta`: `apt-get install -y msmtp-mta`.
- Verifique `ls -l /usr/sbin/sendmail`.

## `mail` não funciona

- Instale `bsd-mailx` (não confundir com ausência total de `mail`).
- Sem `sendmail` funcional, `mail` também falha.

## Template ausente (`lib/mailer.py`)

- Defina `RUNV_EMAIL_ROOT` para a pasta **`email/`** do repositório (que contém `templates/`).
- Ou execute scripts a partir da árvore completa do repositório.

## Permissões em `/root/.netrc`

- Deve ser **600** e dono **root**. Corrigir: `sudo chmod 600 /root/.netrc && sudo chown root:root /root/.netrc`.

## Permissões em `/etc/msmtprc`

- Recomendado **600** root. `msmtp` em modo system-wide exige que o ficheiro não seja legível por utilizadores não privilegiados.

## `passwordeval` / `netrc_password.py`

- Deve existir `/usr/local/lib/runv-email/netrc_password.py` executável.
- Reinstale com `configure_msmtp.py` ou copie manualmente desde `email/scripts/netrc_password.py`.

## Senha com caracteres especiais no `.netrc`

- O formato `.netrc` clássico **não** trata bem todos os caracteres; senhas muito complexas podem exigir escape ou outro método (ver documentação netrc). Em caso de dúvida, use token SMTP dedicado com caracteres seguros para ficheiros texto.

## `--test` diz que falta estado

- Corra primeiro `configure_msmtp.py` sem `--test` para criar `/etc/runv-email.json`.
