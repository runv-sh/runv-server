# runv.club — runv-server

Repositório de scripts e documentação para o servidor **runv.club** (Debian, pubnix).

## Conteúdo principal

| Área | Descrição |
|------|-----------|
| **`scripts/admin/create_runv_user.py`** | Provisiona contas Unix: SSH, `~/public_html` (HTTP), **`~/public_gopher`** (Gopher), **`~/public_gemini`** (Gemini), symlink em `/var/gemini/users/`, README, quota, metadados. |
| **`scripts/admin/setup_alt_protocols.py`** | Instala/configura **gophernicus** (porta 70) e **molly-brown** (Gemini, TLS, porta 1965), UFW se ativo, backfill para utilizadores existentes. Ver **`scripts/docs/alt_protocols.md`**. |
| **`patches/patch_irc.py`** | IRC (estilo tilde.club): comando **`chat`** para utilizadores; rede por defeito `irc.portalidea.com.br`. Ver **`scripts/docs/irc_patch.md`**. |
| **`tools/tools.py`** | Pacotes globais (incl. IRC), MOTD, `/usr/local/bin` (**`chat`**, `runv-help`, …), **`/etc/skel`**. |
| **`terminal/`** | Fluxo SSH «entre» (pedidos de conta). |

## Protocolos públicos por utilizador

- **HTTP:** ficheiros em `~/public_html/` (Apache `mod_userdir`).
- **Gopher:** `~/public_gopher/` (ficheiro inicial `gophermap`); URL típica `gopher://runv.club/1/~usuario`.
- **Gemini:** `~/public_gemini/` (`index.gmi`); URL típica `gemini://runv.club/~usuario/` (serviço global + TLS).

— ~pmurad