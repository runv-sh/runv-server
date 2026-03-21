# Bem-vindo(a) ao runv.club

O **runv.club** é um servidor compartilhado (pubnix) pensado para a comunidade brasileira: você acessa por **SSH**, usa a **shell** e pode publicar uma **página web** simples.

## Sua página na internet

- Os arquivos públicos do site ficam em **`~/public_html/`**.
- A página principal é **`~/public_html/index.html`** (HTML estático).
- A URL pública será algo como **`https://runv.club/~seu_usuario/`** (o nome após `~` é o seu login).

Edite o HTML com um editor no terminal, por exemplo:

```bash
nano ~/public_html/index.html
```

## Permissões (importante)

Para o servidor web enxergar seu site:

| Local | Modo sugerido |
|-------|----------------|
| Sua home (`~`) | `755` |
| `~/public_html` | `755` |
| Arquivos dentro de `public_html` | `644` |

Exemplo:

```bash
chmod 755 ~ ~/public_html
chmod 644 ~/public_html/index.html
```

## Ajuda rápida no servidor

Digite no terminal:

```bash
runv-help
```

Você verá uma lista de **comandos úteis** (navegação no terminal, e-mail, IRC, jogos, etc.) e dicas para quem está começando.

Outros comandos locais:

- **`runv-links`** — links do projeto e do mantenedor.

## Arquivos públicos

Tudo o que você colocar em **`public_html`** pode ser lido pelo mundo via HTTP. **Não coloque** chaves privadas, senhas ou dados sensíveis nessa pasta.

## Aliases

Este diretório pode incluir um arquivo **`.bash_aliases`** (já sugerido no skel) com atalhos como `ll` e `help-runv`. Se o seu shell for Bash, ele costuma carregar aliases desse arquivo se a linha correspondente existir no `~/.bashrc` (no Debian isso costuma vir comentado — você pode descomentar).

---

Seja gentil com a máquina e com a comunidade. Bom uso do runv.club.
