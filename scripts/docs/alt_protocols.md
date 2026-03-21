# Gopher e Gemini — `setup_alt_protocols.py`

Script em **`scripts/admin/setup_alt_protocols.py`**: instala e configura **gophernicus** (Gopher, porta **70**) e **molly-brown** (Gemini, TLS, porta **1965**) no Debian, alinhado ao runv.club.

## Modelo de conteúdo

| Protocolo | Pasta na home | Ficheiro inicial | URL típica |
|-----------|---------------|------------------|------------|
| **HTTP** (já existente) | `~/public_html/` | `index.html` | `http://runv.club/~user/` |
| **Gopher** | `~/public_gopher/` | `gophermap` | `gopher://runv.club/1/~user` |
| **Gemini** | `~/public_gemini/` | `index.gmi` | `gemini://runv.club/~user/` |

**Gemini (molly-brown):** `DocBase = /var/gemini`, `HomeDocBase = users`, symlinks **`/var/gemini/users/<user>` → `~/public_gemini`**.

## Utilizadores antigos vs novos

- **Novos:** recebem modelos via **`/etc/skel`** (após `tools/tools.py`) e via **`create_runv_user.py`** (sempre que o provisionador corre).
- **Antigos:** correr **`setup_alt_protocols.py`** (backfill completo) ou só pastas/symlinks com **`patches/yetgg.py`** (mesma lista de contas que `patch_irc.py`: união JSON + `/home`) se a infraestrutura de sistema já existir.

## Requisitos Gemini

- **TLS obrigatório** (certificado + chave PEM). Por defeito o script tenta Let's Encrypt em `/etc/letsencrypt/live/runv.club/`; use **`--gemini-cert`** e **`--gemini-key`** se forem noutro sítio.
- Sem certificados válidos, o script **não** ativa o serviço `molly-brown@`, mas pode criar `/var/gemini` e symlinks.

## Molly não sobe ou fica em «activating»

- **`journalctl` sem mensagens:** os logs do serviço do sistema exigem **root** — use `sudo journalctl -u molly-brown@runv.club.service -b --no-pager -n 80`.
- **Estado e porta:** `sudo systemctl status molly-brown@runv.club.service --no-pager` e `sudo ss -tlnp | grep 1965` (deve haver um processo a escutar em **1965/tcp**).
- **Permissões TLS (frequente):** o Molly corre como utilizador não-root; se `privkey.pem` for só `root:root` `0600`, o arranque falha. Verifique `sudo namei -l /etc/letsencrypt/live/runv.club/privkey.pem` e compare com o utilizador do unit (`systemctl cat molly-brown@runv.club.service`). Soluções típicas: grupo `ssl-cert`, ACL, ou certificados num path legível pelo utilizador do serviço (mantendo segurança).
- **Teste local:** `openssl s_client -connect 127.0.0.1:1965 -servername runv.club </dev/null 2>/dev/null | head -20`
- **Cliente (Lagrange, etc.):** teste `gemini://runv.club/~user/` **depois** de `systemctl is-active molly-brown@runv.club.service` devolver `active`.

## Execução (root)

Use a **raiz do repositório** clonada; o script carrega `patches/patch_irc.py` para a lista de utilizadores (união JSON + `/home`). Sem esse ficheiro, o comando falha com mensagem explícita.

```bash
cd /caminho/para/runv-server
sudo python3 scripts/admin/setup_alt_protocols.py --dry-run --verbose
sudo python3 scripts/admin/setup_alt_protocols.py --verbose
```

### Flags úteis

| Flag | Efeito |
|------|--------|
| `--dry-run` | Simula; não grava (validação de root ignorada em alguns passos só se documentado). |
| `--verbose` | Log detalhado. |
| `--force` | Sobrescreve configs de sistema (com backup com timestamp) e ficheiros modelo no backfill. |
| `--skip-install` | Não corre `apt-get`. |
| `--skip-gopher` / `--skip-gemini` | Ignora pacote, config e serviço desse protocolo. |
| `--skip-firewall` | Não altera UFW. |
| `--skip-backfill` | Não cria pastas/symlinks por utilizador. |
| `--skip-services` | Não `systemctl enable --now`. |
| `--skip-system-config` | Não escreve `/etc/default/gophernicus`, nem `molly-brown`, nem gophermap raiz. |
| `--users-json PATH` | Parte da fonte de usernames (lista JSON com `username`). Predefinido: `/var/lib/runv/users.json`. |
| `--homes-root PATH` | Parte da fonte de usernames (directórios em `/home` com UID ≥ 1000). O backfill usa a **união** JSON + homes (igual a `patches/patch_irc.py`). |
| `--gemini-hostname HOST` | Predefinido: `runv.club`. |
| `--gemini-cert` / `--gemini-key` | Caminhos PEM para molly-brown. |

## Descoberta de utilizadores (backfill)

A lista de contas para criar `~/public_gopher`, `~/public_gemini` e symlinks em `/var/gemini/users/` é a **união** de:

1. Usernames em **`users.json`** (lista de objetos com campo `username`), quando o ficheiro existe e o JSON é válido; e
2. Nomes em **`--homes-root`** com UID ≥ 1000 e entrada em `passwd`.

Depois aplicam-se as mesmas exclusões que em **`patches/patch_irc.py`** (`IRC_PATCH_SKIP_USERS` — contas de sistema, `entre`, etc.; **não** exclui `pmurad-admin` por defeito). Para só pastas/symlinks sem reinstalar serviços, pode usar **`patches/yetgg.py`**.

## Relação com outros scripts

- **`create_runv_user.py`**: após `public_html`, cria `public_gopher`, `public_gemini` e tenta o symlink em `/var/gemini/users/`.
- **`del-user.py`**: remove o symlink `/var/gemini/users/<user>` se existir e for symlink.
- **`tools/tools.py`**: copia modelos para `/etc/skel` (só contas futuras).

## Testes manuais sugeridos

1. `sudo python3 scripts/admin/setup_alt_protocols.py --dry-run --verbose`
2. `sudo python3 scripts/admin/setup_alt_protocols.py --verbose`
3. `dpkg -l gophernicus molly-brown`
4. `systemctl is-active gophernicus.socket` e `systemctl is-active molly-brown@runv.club.service`
5. `ufw status` (se ativo, confirmar 70/tcp e 1965/tcp permitidos)
6. Verificar `/etc/skel/public_gopher` e `public_gemini` após `tools.py`
7. Criar utilizador de teste com `create_runv_user.py`
8. `ls -la /home/teste/public_gopher/gophermap /home/teste/public_gemini/index.gmi` e `ls -la /var/gemini/users/teste`
9. Cliente Gopher/Gemini: `gopher://runv.club/1/~teste` e `gemini://runv.club/~teste/`

Versão do script: ver `python3 scripts/admin/setup_alt_protocols.py --version`.
