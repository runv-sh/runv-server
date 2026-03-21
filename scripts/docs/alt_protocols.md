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

## Execução (root)

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
| `--users-json PATH` | Fonte de usernames (lista JSON com `username`). Predefinido: `/var/lib/runv/users.json`. |
| `--homes-root PATH` | Fallback se JSON vazio/inexistente (varre UIDs ≥ 1000). |
| `--gemini-hostname HOST` | Predefinido: `runv.club`. |
| `--gemini-cert` / `--gemini-key` | Caminhos PEM para molly-brown. |

## Descoberta de utilizadores (backfill)

1. Se **`users.json`** existir e for uma lista JSON válida com objetos que tenham **`username`**, usa essa lista.
2. Caso contrário, varre **`--homes-root`** (predefinido `/home`), UIDs ≥ 1000, excluindo contas reservadas (`root`, `entre`, `pmurad-admin`, contas de sistema, etc.).

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
