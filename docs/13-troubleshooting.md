# Resolução de problemas

[← Índice](README.md)

## Bolhas / constelação não aparecem

1. Confirmar que existe **`DocumentRoot/data/members.json`** (não só `site/public/data/members.json` no clone).
2. Ver mensagem de **`create_runv_user.py`**: AVISO se DocumentRoot inexistente ou se `genlanding --sync-public-only` falhou (ver log / comando manual sugerido).
3. Browser: em viewport ≤768px o JS **omitido** de propósito (`app.js`).

## `members.json` vazio

- `users.json` inexistente → `build_directory.py` assume `[]` com aviso em stderr.
- JSON inválido → script termina com erro.

## Email não envia (entre / Mailgun)

- Verificar `/etc/runv-email.json`, segredos, `admin_email`, `email_package_root` / `RUNV_EMAIL_ROOT`.

## Apache

- `apache2ctl configtest` após alterações de vhost.
- `genlanding.py` imprime erros se `build_directory` falhar.

## Feed RSS descarrega em vez de abrir no browser

- Com `genlanding` ≥ 0.07: confirme que existe **`/etc/apache2/conf-available/runv-landing-rss-mime.conf`**, que o symlink em `conf-enabled` está activo (`a2enconf runv-landing-rss-mime`) e que o `<Directory>` aponta ao **DocumentRoot correcto**; depois `sudo systemctl reload apache2`. O snippet cobre **HTTPS** sem tocar no ficheiro do Certbot (ver [06-site-and-apache.md](06-site-and-apache.md)).
- Instalações antigas só com `ForceType` no `:80`: acrescente o mesmo bloco `<Directory …/news><Files "feed.rss">ForceType text/xml</Files></Directory>` no VirtualHost **:443** ou migre correr o `genlanding` completo de novo.

## Quotas

- FS não ext4 → automatização de `starthere.py` pode recusar; configurar manualmente ou usar volume ext4.

## SSH `entre`

- Sessão fecha de imediato: rever PAM / modo `empty-password` / logs em `/var/log/runv/entre.log`.

Próximo: [14-smoke-tests-and-validation.md](14-smoke-tests-and-validation.md).
