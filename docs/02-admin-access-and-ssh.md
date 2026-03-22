# Acesso administrativo e SSH

[← Índice](README.md)

## Modelo operacional

- A maioria dos scripts de infraestrutura exige **root** no servidor alvo.
- O repositório **não** define um “utilizador admin” específico além do que o Debian/OpenSSH já permitem: tipicamente **root com chave SSH** ou utilizador em `sudo`.

## Facto do repositório

- **`starthere.py`** documenta que **não** reconfigura SSH além do contexto do bootstrap (ver docstring: não mexe em SSH).
- **`setup_entre.py`** configura SSH **só** para o utilizador especial `entre` (drop-in, PAM opcional, modos de auth documentados no script).

## Recomendação de segurança (genérica, não codificada no repo)

- Preferir **autenticação por chave** para a conta que usa para administrar o servidor.
- Desactivar login root por palavra-passe em produção se a política o exigir — **não** é alteração feita automaticamente por estes scripts.

## Distinção

| Tema | Origem |
|------|--------|
| Chaves do **admin** no servidor | Política do operador / Debian |
| Chave pública no **pedido `entre`** | Recolhida pelo fluxo `entre`, instalada **só** quando `create_runv_user.py` cria o membro |

## Relação com scripts

Sem root/sudo não é possível: `starthere.py`, `tools.py`, `genlanding.py` (sem `--dry-run`), `setup_entre.py`, `create_runv_user.py`.

Próximo: [03-paths-files-and-state.md](03-paths-files-and-state.md).
