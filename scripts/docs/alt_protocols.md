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

- **Comportamento actual do script (v0.05+):** instala o drop-in systemd **`/etc/systemd/system/molly-brown@.service.d/50-runv-logs.conf`** com `LogsDirectory=molly-brown`, para o systemd criar/ajustar **`/var/log/molly-brown`** com o dono correcto em cada arranque (necessário porque o pacote Debian usa **`DynamicUser=yes`** — um `chown` baseado em `getpwnam` ou no nome `User=` **não** coincide com o UID dinâmico real). Cria também os ficheiros `runv.club-access.log` e `runv.club-error.log` se faltarem, e grava os caminhos absolutos em `/etc/molly-brown/runv.club.conf`.
- **Servidor já provisionado com conf antiga:** o script só reescreve o `.conf` (e o drop-in, se já existir com outro conteúdo) se correr com **`--force`** (faz backup com timestamp onde aplicável). Exemplo:  
  `sudo python3 scripts/admin/setup_alt_protocols.py --verbose --force`
- **Correcção manual rápida (só `.conf`):** editar `AccessLog` / `ErrorLog` para caminhos absolutos sob `/var/log/molly-brown/`; garantir o drop-in `LogsDirectory=molly-brown` como acima; `sudo systemctl daemon-reload`; `sudo systemctl reset-failed molly-brown@runv.club.service` e `sudo systemctl start molly-brown@runv.club.service`.

## Erro `permission denied` em `/var/log/molly-brown/…-error.log`

Aparece quando os ficheiros de log ficaram com dono **root** ou outro UID que **não** é o do processo molly-brown. No Debian, o unit **`molly-brown@.service`** usa **`DynamicUser=yes`**: o utilizador de runtime é gerido pelo systemd, por isso **`sudo chown molly-brown:molly-brown`** (utilizador estático em `/etc/passwd`, se existir) **não** resolve de forma fiável.

- **Solução suportada:** o script **v0.05+** instala o drop-in com **`LogsDirectory=molly-brown`**; no arranque, o systemd corrige a propriedade de `/var/log/molly-brown`. Depois de actualizar o repo: `sudo python3 scripts/admin/setup_alt_protocols.py --verbose --force`, `sudo systemctl daemon-reload`, `sudo systemctl reset-failed molly-brown@runv.club.service`, `sudo systemctl start molly-brown@runv.club.service`.
- **Verificação:** `systemctl cat molly-brown@runv.club.service` deve mostrar o fragmento `50-runv-logs.conf` com `LogsDirectory=molly-brown`.

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
| `--force` | Sobrescreve configs de sistema (com backup com timestamp) e ficheiros modelo no backfill. Necessário para **regravar** `/etc/molly-brown/runv.club.conf` ou o drop-in **`50-runv-logs.conf`** após correcções (ex. logs Molly / `DynamicUser`). |
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
