# terminal — pedido de entrada SSH (`entre@runv.club`)

Módulo **runv.club** para quem se liga por SSH ao utilizador Unix **`entre`**: em vez de shell normal, corre uma experiência **textual guiada** que recolhe nome de utilizador, email, **sítios ou perfis online** (onde te possamos ver) e chave pública SSH, grava um JSON na **fila local** e (opcionalmente) notifica o administrador por **sendmail**.

**Não cria contas Linux.** O provisionamento continua a ser manual (ou via [`scripts/admin/create_runv_user.py`](../scripts/admin/create_runv_user.md)).

## Ficheiros principais

| Ficheiro | Função |
|----------|--------|
| `entre_app.py` | Programa principal (ForceCommand SSH). |
| `entre_core.py` | Validação, fila JSON, log, email. |
| `setup_entre.py` | Instalação no servidor (root): utilizador `entre`, shell `/bin/sh`, `--auth-mode` (`shared-password` \| `key-only` \| `empty-password` estilo tilde.town), PAM opcional, drop-in SSH, `sshd -t` + `sshd -T -C`, reload. |
| `config.example.toml` | Modelo versionado; **não** editar como `config.toml` no git. |
| `gen_config_toml.py` | Gera `config.toml` a partir do example (evita conflitos em `git pull`). |
| `templates/*.txt` | Textos da experiência e do email ao admin. |
| `docs/USO.md` | **Instalação + uso** (admin, visitante, testes, checklist). |
| `docs/INSTALL.md` | Guia de instalação detalhado (Debian 13). |
| `docs/ADMIN.md` | Operação e aprovação de pedidos. |
| `docs/ARCHITECTURE.md` | Desenho e segurança. |

## Instalação e uso (resumo)

Guia unificado: **[`docs/USO.md`](docs/USO.md)**.

Em linhas:

1. Como root: `python3 setup_entre.py` (ou `scripts/install.sh`) — por omissão `--auth-mode shared-password`, shell `/bin/sh`, validação `sshd -T -C …`.
2. **Onboarding sem senha (estilo tilde.town):** `sudo python3 setup_entre.py --auth-mode empty-password` — **PAM** por omissão; SSH por omissão **keyboard-interactive** (melhor no **OpenSSH do Windows**). Teste: `ssh entre@runv.club`. Se a sessão fechar, veja PAM e logs em [INSTALL.md](docs/INSTALL.md). Para o modo README tilde (**password** + senha vazia), use **`--empty-password-tilde-password-auth`** (Linux/Git Bash).
3. Gerar ou ajustar `/opt/runv/terminal/config.toml` com `python3 gen_config_toml.py --install-root /opt/runv/terminal` (ou `--force` para repor o example). O ficheiro está em `.gitignore` no clone; só o **example** é versionado.
4. Modo default: `sudo passwd entre`. Modo `key-only`: `authorized_keys`.
5. Visitante: `ssh entre@runv.club` e seguir o fluxo até à despedida.

Opcional: `--skip-sshd` para aplicar o bloco `Match User entre` à mão (`INSTALL.md`).

## Teste local (sem SSH)

```bash
chmod +x scripts/test_local.sh
./scripts/test_local.sh
```

Usa `terminal/data/queue` e `config.example.toml`. Exige **`ssh-keygen`** no PATH (validação da chave).

## Variáveis de ambiente (opcional)

| Variável | Efeito |
|----------|--------|
| `RUNV_ENTRE_ROOT` | Raiz do módulo (default: pasta do `entre_core.py`). |
| `RUNV_ENTRE_CONFIG` | Caminho absoluto do `config.toml`. |
| `RUNV_ENTRE_QUEUE_DIR` | Sobrepõe `queue_dir` do TOML. |
| `RUNV_ENTRE_LOG_FILE` | Sobrepõe `log_file` do TOML. |
| `RUNV_ENTRE_TEMPLATES_DIR` | Sobrepõe `templates_dir`. |

## Checklist manual de teste

- [ ] `python3 -m py_compile entre_app.py entre_core.py setup_entre.py`
- [ ] `./scripts/test_local.sh` — percorrer fluxo até gravar JSON em `data/queue/`
- [ ] Confirmar que **não** sobrescreve se repetir o mesmo `request_id` (colisão improvável; o código regera UUID)
- [ ] Com `admin_email` preenchido e `mailutils`/`sendmail`: pedido gera tentativa de email (ver log)
- [ ] No servidor: após `setup_entre.py`, `sshd -t` OK e ficheiro `runv-entre.conf` (ou equivalente manual com `--skip-sshd`)
- [ ] `ssh entre@servidor` — fluxo completo e ficheiro em `/var/lib/runv/entre-queue/`
- [ ] Após aprovação: correr `create_runv_user.py` com dados do JSON (ver `docs/ADMIN.md`)

Versão da app: ver `python3 entre_app.py --version`.
