# Baseline do servidor Debian

[← Índice](README.md)

## Obrigatório (implícito nos scripts)

- **Sistema:** **Debian** (o projecto referencia Debian 13 “trixie” em vários README históricos e docstrings; **não verificado** em cada release).
- **Acesso:** capacidade de executar comandos como **root** (`sudo` ou sessão root) para bootstrap, `tools.py`, `genlanding.py`, `setup_entre.py`, `create_runv_user.py`.
- **Python 3** instalado (scripts usam shebang `python3`).

## Recomendação operacional (não imposta pelo repo)

- **Hostname** coerente com DNS público se for servir `runv.club` ou outro domínio.
- **Hora:** NTP/chrony para timestamps correctos em logs e `created_at` (o repo **não** configura NTP por si).
- **Locale UTF-8** para terminais e logs legíveis — padrão Debian moderno.

## Sistema de ficheiros e quotas

- **`starthere.py`** e a lógica de quota em `create_runv_user.py` assumem **ext4** com **usrquota** no mount que contém `/home` (ou path de sonda). Se o FS não for ext4, a automatização de quota em `starthere.py` **falha de propósito** (mensagem de erro no script). **Evidência:** docstring `scripts/admin/starthere.py` (filesystem ext4).

## O que o repositório não faz

- Não escolhe hostname por si.
- Não configura NTP, locale ou timezone como passo dedicado (tratar como **pré-requisito de exploração** ou configuração manual Debian).

## Próximo passo

[04-bootstrap-and-base-system.md](04-bootstrap-and-base-system.md) após garantir Debian + root + Python 3.
