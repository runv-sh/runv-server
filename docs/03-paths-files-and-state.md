# Caminhos, ficheiros e estado

[← Índice](README.md)

## Caminhos canónicos no servidor

| Caminho | Função | Gerado / versionado |
|---------|--------|---------------------|
| `/var/lib/runv/users.json` | Lista de metadados dos membros (fonte para `build_directory.py`) | **Gerado** na primeira operação que use; **nunca** commitar com dados reais |
| `/var/lib/runv/users.lock` | Lock `flock` para escrita segura em `users.json` | Gerado em uso |
| `/var/lib/runv/entre-queue/` | Fila de pedidos JSON do SSH `entre` | Gerado; ficheiros por `request_id` |
| `/var/log/runv/entre.log` | Log do fluxo `entre` (configurável via TOML) | Gerado |
| `/opt/runv/terminal/` | Instalação do módulo `terminal/` (`setup_entre.py`) | Cópia a partir do repo; `config.toml` gerado localmente |
| `/etc/runv-email.json` | Estado público de configuração de email | Gerado por `configure_mailgun.py` |
| `/etc/runv-email.secrets.json` | Segredos (API keys, etc.) | Gerado; **0600**, root; **nunca** commitar |
| `/var/www/runv.club/html` | DocumentRoot **predefinido** em produção (`genlanding.py`, default `--landing-document-root` em `create_runv_user.py`) | Gerado no servidor; não é o mesmo que `site/public/` no clone |

**Evidência:** `docs/04-bootstrap-and-base-system.md`, `terminal/config.example.toml`, defaults em `site/genlanding.py`, `site/build_directory.py`, `scripts/admin/create_runv_user.py`.

## No clone do Git

- **`site/public/data/members.json`:** no repositório deve permanecer lista vazia `[]` (placeholder); dados reais vêm de `build_directory.py` no deploy.
- **`terminal/config.toml`:** no `.gitignore`; usar `config.example.toml` + `gen_config_toml.py` / `setup_entre.py`.

## O que nunca commitar

- `runv-email.secrets.json` (qualquer cópia)
- `users.json` com dados reais
- Ficheiros JSON da fila com PII
- Chaves privadas SSH

Próximo: [04-bootstrap-and-base-system.md](04-bootstrap-and-base-system.md).
