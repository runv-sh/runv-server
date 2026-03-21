# Site público (landing runv.club)

Conteúdo estático inspirado em [tilde.town](https://tilde.town) e [tilde.club](https://tilde.club): landing com constelação de links por membro (`members.json`), rotas **`/news/`** e **`/wiki/`** (placeholders por agora), e **`/junte-se/`** — guia de chave SSH (Linux, macOS, Windows) e acesso a **`entre@runv.club`**.

## O que significa “membro” na página

- **Membro listado** = conta presente em `/var/lib/runv/users.json` (criada por `create_runv_user.py`).
- **Não** é “sessão SSH ativa neste momento” nem “logged in”; isso exigiria outra fonte de dados (ex. `lastlog`).

## Privacidade

- `build_directory.py` **filtra** o JSON interno: só escreve `username`, `since` (data de criação), `path` (`/~user/`) e, opcionalmente, `homepage_mtime` se você usar `--homes-root`.
- **Nunca** copia email, fingerprint de chave nem quotas para `members.json`.

## Stack

- **HTML/CSS/JS** estáticos em `public/`.
- **Rodapé:** em todas as páginas HTML em `public/` deve constar o **contato** da administração — `admin@runv.club` (bloco `<footer class="site-footer">` como em `index.html`).
- **Geração de dados**: Python 3 (stdlib) — adequado a **cron** no servidor; sem CGI.

## Gerar `public/data/members.json`

**No Git**, `public/data/members.json` fica **`[]`**: a landing não deve mostrar utilizadores fictícios. Quem aparece na constelação vem **só** de `build_directory.py` a ler **`/var/lib/runv/users.json`** (produção, via cron) ou, em desenvolvimento, uma cópia de teste com **`--users-json site/example-users.json`** — sem commit do JSON gerado como se fosse produção. Se **`users.json` ainda não existir** no servidor, o `build_directory.py` assume **zero membros** (aviso em stderr) em vez de falhar.

Manual detalhado do script: **[`build_directory.md`](build_directory.md)**.

No servidor (como root), após provisionar contas:

```bash
sudo python3 /caminho/ao/repo/site/build_directory.py \
  --users-json /var/lib/runv/users.json \
  --homes-root /home \
  -o /caminho/deploy/public/data/members.json
```

Sem acesso a `/home` (ex.: build na **sua** máquina só para pré-visualizar):

```bash
python3 site/build_directory.py \
  --users-json site/example-users.json \
  -o site/public/data/members.json
```

Dry-run:

```bash
python3 site/build_directory.py --users-json site/example-users.json --dry-run
```

## Configurar Apache (`genlanding.py`)

Para **gerar o VirtualHost**, **ativar** `mod_userdir` / `mod_rewrite`, copiar **`public/`** para o `DocumentRoot` e (opcional) rodar **Certbot**, use o script **[`genlanding.py`](genlanding.py)**. Manual completo: **[`genlanding.md`](genlanding.md)**.

Exemplos:

```bash
# Produção (runv.club, /var/www/runv.club/html)
sudo python3 site/genlanding.py

# Pré-visualização
python3 site/genlanding.py --dry-run

# VM / teste local (runv.local; por padrão desativa 000-default para IP servir a landing)
sudo python3 site/genlanding.py --dev
# Manter página Debian em paralelo: --dev --keep-default-site

# TLS após HTTP correto (não combinar com --dev)
sudo python3 site/genlanding.py --certbot
```

## Deploy no Apache (manual)

Alternativa ao genlanding: copiar o conteúdo de **`public/`** para o `DocumentRoot` do VirtualHost do domínio (ex. `/var/www/runv.club/html/`), ou configurar `DocumentRoot` para apontar diretamente para esta pasta.

**Certifique-se** de que `mod_userdir` continua a servir `~/public_html` para cada **usuário**; a landing é só a **raiz** do site.

### Cron (exemplo)

```cron
*/15 * * * * root python3 /opt/runv-server/site/build_directory.py --users-json /var/lib/runv/users.json --homes-root /home -o /var/www/runv/html/data/members.json
```

(Ajuste os caminhos.)

## Arquivos

| Caminho | Função |
|---------|--------|
| `genlanding.py` | Configura Apache (vhost, cópia de `public/`, opcional Certbot); ver `genlanding.md` |
| `build_directory.py` | Gera `members.json` público; ver **`build_directory.md`** |
| `build_directory.md` | Como usar `build_directory.py` (flags, cron, exemplos) |
| `public/index.html` | Landing |
| `public/junte-se/index.html` | Pedir entrada: gerar chave SSH e `ssh entre@runv.club` |
| `public/assets/style.css` | Estilos |
| `public/assets/app.js` | Constelação, lista, filtro, shuffle |
| `public/data/members.json` | Dados públicos (regenerado; exemplo no repo) |
| `example-users.json` | Amostra para testes locais |
