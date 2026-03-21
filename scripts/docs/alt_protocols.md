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

## Erro `Error opening error log file: open /-` (read-only file system)

O **molly-brown** trata `AccessLog` e `ErrorLog` como **caminhos de ficheiro**. Valores como `"-"` (estilo «stdout» noutros programas) são interpretados de forma errada e o processo tenta abrir `/-`, falhando de imediato.

- **Comportamento actual do script (v0.06+):** grava `AccessLog` / `ErrorLog` em **`/var/lib/molly-brown/`** (`runv.club-access.log`, `runv.club-error.log`). Esse caminho coincide com **`StateDirectory=molly-brown`** do unit Debian: o systemd cria o directório com o dono correcto (**`DynamicUser=yes`**) **antes** do `ExecStart`, sem `chown` manual. **Não** pré-cria pastas nem ficheiros de log (evita conflitos com `LogsDirectory` em `/var/log`).
- **Versões antigas (v0.05):** usavam o drop-in `50-runv-logs.conf` com `LogsDirectory=molly-brown`. Se `/var/log/molly-brown` já existia como root, o systemd podia **migrar** para `/var/log/private/molly-brown` e o serviço falhava. O **v0.06+** **remove** esse drop-in e muda os caminhos no `.conf` para `/var/lib/molly-brown/`.
- **Servidor já provisionado:** correr com **`--force`** para regravar o `.conf` e remover o drop-in obsoleto (com backup do drop-in se usar `--force`). Exemplo:  
  `sudo python3 scripts/admin/setup_alt_protocols.py --verbose --force`
- **Correcção manual rápida (só `.conf`):** `AccessLog` / `ErrorLog` com caminhos absolutos sob **`/var/lib/molly-brown/`**; **sem** `LogsDirectory` extra em drop-in; `sudo systemctl daemon-reload`; `sudo systemctl reset-failed molly-brown@runv.club.service` e `start`.

## Erro `permission denied` em `/var/log/molly-brown/…` ou migração para `/var/log/private/molly-brown`

No Debian, **`DynamicUser=yes`** faz o UID de runtime ser dinâmico; `chown` estático não bate. Se viu **`migrating to /var/log/private/molly-brown`** ou **`permission denied`** em `/var/log/molly-brown`, actualize para **v0.06+** com **`--force`**.

**Limpeza recomendada (serviço parado):**

```bash
sudo systemctl stop 'molly-brown@runv.club.service'
sudo rm -f /etc/systemd/system/molly-brown@.service.d/50-runv-logs.conf
sudo rm -rf /var/log/molly-brown /var/log/private/molly-brown
sudo systemctl daemon-reload
sudo python3 /opt/runv/src/scripts/admin/setup_alt_protocols.py --verbose --force
```

(ajuste o caminho do script ao seu clone). Os logs passam a ficar só em **`/var/lib/molly-brown/`** (legível com `sudo`).

## Erro `permission denied` em `/var/lib/molly-brown/…`

Raro se o `.conf` aponta para `/var/lib/molly-brown/` e não há override que desactive `StateDirectory`. Confirme `grep StateDirectory /lib/systemd/system/molly-brown@.service` e caminhos no `.conf`; veja também **TLS** (`privkey` legível pelo grupo `ssl-cert`).

## Checklist rápido (conf antiga, UFW, «activating»)

1. **Ainda vê `open /-` no journal?** O `/etc/molly-brown/runv.club.conf` no servidor pode continuar com `ErrorLog = "-"` até correr o script com **`--force`** (ou editar à mão). Confirme: `grep -E 'AccessLog|ErrorLog' /etc/molly-brown/runv.club.conf`.
2. **UFW:** o script só executa `ufw allow` automaticamente quando **`ufw status`** mostra o firewall **activo** na altura da execução. Se activou o UFW **depois**, ou usa outro firewall, abra **70/tcp** (Gopher) e **1965/tcp** (Gemini) manualmente:
   ```bash
   sudo ufw allow 70/tcp comment 'gopher'
   sudo ufw allow 1965/tcp comment 'gemini'
   sudo ufw reload
   ```
   Com `--skip-firewall` ou UFW inactivo, o script regista no log os mesmos comandos sugeridos para copiar.
3. **`molly-brown@runv.club: activating` no fim do script:** **não** indica sucesso — só que o unit ainda não estava `active` nesse instante (p.ex. crash loop). Use `systemctl is-active molly-brown@runv.club.service`, `systemctl is-failed …` e `sudo ss -tlnp | grep 1965`. Se `is-failed` for positivo, veja `journalctl` como abaixo.

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
| `--force` | Sobrescreve configs de sistema (com backup com timestamp) e ficheiros modelo no backfill. Necessário para **regravar** `/etc/molly-brown/runv.club.conf` e remover o drop-in obsoleto **`50-runv-logs.conf`** (v0.05) ao migrar logs para `/var/lib/molly-brown/`. |
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
