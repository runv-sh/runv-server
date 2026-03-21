# tools — experiência base runv.club (Debian)

Módulo para **automatizar** no servidor Debian 13 (ou compatível):

1. **Pacotes globais** via `apt` (lista em `manifests/apt_packages.txt`) — para todos os usuários, **sem** passar pelo `/etc/skel`.
2. **Comandos locais** em `/usr/local/bin`: `runv-help`, `runv-links`, `runv-status`, **`chat`** (IRC; rede da casa provisionada com **`patches/patch_irc.py`** — utilizadores usam só `chat`).
3. **MOTD dinâmico** em `/etc/update-motd.d/60-runv` (arte ASCII verde, texto em português).
4. **Arquivos padrão** copiados para `/etc/skel/` (README, `.bash_aliases`, `public_html/index.html`, `public_gopher/gophermap`, `public_gemini/index.gmi`) — **somente modelos de home**, nunca instaladores de sistema.

## Regras

- **`/etc/skel`** = apenas arquivos que **novas contas** recebem na home (via `adduser`). **Não** instala programas.
- **Programas** = sempre **`apt`** (globais).
- **Scripts do projeto** = **`/usr/local/bin`**.
- **MOTD** = script executável em **`/etc/update-motd.d/`**.
- Python **stdlib** apenas; **`subprocess` sem `shell=True`**; sem Docker, sem web, sem DB.

## Execução rápida

No servidor, a partir da raiz do repositório (ou com caminho absoluto):

```bash
sudo python3 tools/tools.py
```

Simular sem alterar nada:

```bash
sudo python3 tools/tools.py --dry-run --verbose
```

Sem `--force`, o script **atualiza** MOTD, `bin/` e skel quando o ficheiro no repositório **mudou** em relação ao destino. Para sobrescrever **sempre** (mesmo idêntico):

```bash
sudo python3 tools/tools.py --force
```

Reaplicar só scripts/MOTD/skel **sem** rodar `apt`:

```bash
sudo python3 tools/tools.py --skip-apt
```

## Conteúdo

| Caminho | Função |
|---------|--------|
| `tools.py` | Orquestra apt, cópias e permissões |
| `manifests/apt_packages.txt` | Um pacote Debian por linha |
| `bin/` | Scripts shell instalados em `/usr/local/bin` |
| `motd/60-runv` | Fragmento MOTD (verde, pubnix) |
| `skel/` | Modelos copiados para `/etc/skel/` |
| `docs/` | Instalação, administração, experiência do usuário |

## Byobu

O pacote **byobu** é instalado **globalmente** com os demais, mas **não** é ativado automaticamente para todos os usuários. Quem quiser pode habilitar depois com **`byobu-enable`** na própria conta. Integrar isso ao fluxo de **provisionamento** (`create_runv_user` / onboarding) fica para uma etapa futura — não é papel deste módulo forçar Byobu no login.

## Documentação

- **[docs/INSTALL.md](docs/INSTALL.md)** — dependências, flags, verificação.
- **[docs/ADMIN.md](docs/ADMIN.md)** — operação e manutenção.
- **[docs/USER_EXPERIENCE.md](docs/USER_EXPERIENCE.md)** — o que o usuário vê e recebe.
