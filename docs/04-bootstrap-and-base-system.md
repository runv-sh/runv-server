# Bootstrap e sistema base

[← Índice](README.md)

## Script: `scripts/admin/starthere.py`

**O que faz** (docstring do script): actualiza APT; instala pacotes úteis; limpeza `autoremove`/`autoclean`; activa Apache2; se UFW inactivo, permite SSH/80/443 e activa UFW; descobre o filesystem que contém `/home`; adiciona `usrquota` ao `fstab` em ext4; remount / quotacheck / quotaon; activa quotas de utilizador.

**O que não faz** (mesma docstring): não purga pacotes arbitrariamente; **não** configura email; **não** cria utilizadores; **não** mexe no SSH para além do contexto descrito; não instala stack de email.

## Execução

```bash
cd REPO/scripts/admin
sudo python3 starthere.py --help
sudo python3 starthere.py
```

## Ordem sugerida

O bootstrap é o **primeiro** passo lógico antes de `tools.py`, site, email e `entre` (ver [00-overview.md](00-overview.md) e ordem em documentação histórica absorvida).

## Pressupostos

- **ext4** no volume onde `/home` (ou path de sonda) reside — caso contrário o script aborta a parte de quotas automáticas.

Próximo: [05-tools-and-system-experience.md](05-tools-and-system-experience.md).
