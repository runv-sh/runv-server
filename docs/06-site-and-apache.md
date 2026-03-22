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
- Versão actual do script: constante `VERSION` no ficheiro (ex.: `0.04`).

## TLS e DNS

- **Recomendação:** DNS a apontar para o servidor antes de Certbot (documentado historicamente).

## Constelação (bolhas)

- Depende de `members.json` no DocumentRoot.
- Após **`create_runv_user.py`:** se `--landing-document-root` existir como directório, o script tenta regerar `data/members.json` e imprime linha **`constelação (bolhas)`** ou **AVISO** se faltar path ou falhar o refresh (**evidência:** código actual em `create_runv_user.py`).

Próximo: [07-public-members-directory.md](07-public-members-directory.md).
