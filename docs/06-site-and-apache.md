# Site público e Apache

[← Índice](README.md)

## Conteúdo estático

- **`site/public/`:** HTML, CSS, JS servidos como DocumentRoot após `genlanding.py`.
- A landing faz `fetch("data/members.json")` **relativo à URL** — o ficheiro efectivo é **`DocumentRoot/data/members.json`** (ver `site/public/assets/app.js`).

## Script: `site/genlanding.py`

- Configura VirtualHost Apache, `mod_userdir`, `mod_rewrite`, copia `site/public` → DocumentRoot.
- Modo produção: domínio predefinido `runv.club`, DocumentRoot predefinido `/var/www/runv.club/html`.
- Modo `--dev`: `runv.local`, `/var/www/runv-dev/html`.
- Opcional: `--certbot` (incompatível com `--dev`).
- Após cópia, por omissão chama `build_directory.py` para gravar `data/members.json` no DocumentRoot (`--no-refresh-members` para omitir).
- **`--sync-public-only`:** só copia `site/public/` → DocumentRoot, `chown www-data` e regenera `members.json`; **não** altera Apache (uso típico após `create_runv_user.py` e disponível para correr à mão).
- Versão actual do script: constante `VERSION` no ficheiro (ex.: `0.05`).

## TLS e DNS

- **Recomendação:** DNS a apontar para o servidor antes de Certbot (documentado historicamente).

## Constelação (bolhas)

- Depende de `members.json` no DocumentRoot.
- Após **`create_runv_user.py`:** se `--landing-document-root` existir como directório, o script corre **`genlanding.py --sync-public-only`** (cópia de `site/public/` + `members.json`) e imprime **`landing (public + bolhas)`** ou **AVISO** se faltar path ou falhar (**evidência:** `create_runv_user.py`).

Próximo: [07-public-members-directory.md](07-public-members-directory.md).
