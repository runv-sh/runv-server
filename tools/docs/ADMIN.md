# Administração — módulo `tools/`

Operação contínua do runv.club em **Debian**.

## Atualizar a lista de pacotes

1. Edite **`tools/manifests/apt_packages.txt`** (um pacote por linha; comentários com `#`).
2. No servidor:

```bash
sudo python3 tools/tools.py --verbose
```

Use **`--skip-apt`** se quiser **não** rodar o apt nesta passada (por exemplo, durante janela de manutenção em que só atualiza arquivos).

## Trocar textos do MOTD

- Edite **`tools/motd/60-runv`** no repositório (shell `sh`, sem `figlet`). O logótipo **RUNV** usa as mesmas linhas UTF-8 que a landing e o `entre_app.py`; só esse bloco leva ANSI verde (`%b` + literais `\033`, não `echo -e`).
- Reaplique:

```bash
sudo python3 tools/tools.py --force --skip-apt
```

(`--force` força cópia mesmo sem mudança no conteúdo; sem ele, basta alterar o ficheiro no repo e rodar `tools.py`.)

**Boas práticas:** mantenha fallbacks (`command -v` / redirecionar stderr) para não quebrar o login se algum binário sumir.

## Editar `runv-help`, `runv-links`, `runv-status`

1. Altere os arquivos em **`tools/bin/`**.
2. Instale de novo:

```bash
sudo python3 tools/tools.py --force --skip-apt
```

Confirme permissões **755** em `/usr/local/bin/`.

## Reaplicar tudo com `tools.py`

Instalação completa (apt + arquivos):

```bash
sudo python3 tools/tools.py --force --verbose
```

Só arquivos (sem apt):

```bash
sudo python3 tools/tools.py --force --skip-apt
```

## Remover um script

O `tools.py` **não remove** arquivos do sistema. Para retirar, por exemplo, `runv-help`:

```bash
sudo rm -f /usr/local/bin/runv-help
```

Para o MOTD:

```bash
sudo rm -f /etc/update-motd.d/60-runv
```

Para modelos no skel (cuidado — afeta **novas** contas, não apaga homes existentes):

```bash
sudo rm -f /etc/skel/README.md
# etc.
```

Depois, se quiser reinstalar só a partir do repositório:

```bash
sudo python3 tools/tools.py --force --skip-apt
```

## Ajustar permissões manualmente

Se algo ficou com modo errado:

```bash
sudo chmod 755 /usr/local/bin/runv-help /usr/local/bin/runv-links /usr/local/bin/runv-status
sudo chmod 755 /etc/update-motd.d/60-runv
sudo chmod 644 /etc/skel/README.md /etc/skel/.bash_aliases /etc/skel/public_html/index.html
sudo chmod 755 /etc/skel/public_html
```

Dono típico: **root:root** (o script tenta `chown` após copiar).

## Byobu

- **Instalado** globalmente com o apt deste módulo.
- **Não** habilitado automaticamente para todos (evita surpresas no login).
- Usuários podem usar **`byobu-enable`** quando quiserem.
- Documentar ou automatizar no **onboarding** / `create_runv_user` é decisão futura — ver **`tools/README.md`**.

## Idempotência

- Rodar **`tools.py`** **sem `--force`** compara origem e destino: se forem **idênticos**, pula; se o repo tiver **versão nova**, copia e atualiza.
- **`apt-get install`** já é idempotente para pacotes instalados.
- Use **`--force`** para sobrescrever **sempre** (mesmo conteúdo igual), por exemplo para repor dono/permissões.
