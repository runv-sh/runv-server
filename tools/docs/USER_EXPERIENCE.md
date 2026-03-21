# Experiência do usuário — runv.club (`tools/`)

Visão para **quem entra no servidor** pela primeira vez (e para quem documenta suporte).

## O que aparece no login

1. **MOTD** — O Debian executa os scripts em `/etc/update-motd.d/`. O fragmento **`60-runv`** mostra:
   - logótipo **RUNV** (mesmo desenho UTF-8 da landing) **só nesse bloco** em verde;
   - tagline `.club — um computador para compartilhar` (sem bloco de estatísticas no MOTD; use **`runv-status`** para data, uptime, memória, disco, sessões);
   - lista curta de comandos (incluindo `lynx`, `tmux`, `byobu`, `mutt`, `weechat`, `adventure`);
   - linha final: **digite `runv-help` para começar**.

2. **Prompt da shell** — Depende do shell padrão (geralmente Bash no Debian). O que o usuário **herda** da home vem do **`/etc/skel`** no momento em que a conta foi criada.

## Comandos locais do runv

| Comando | Função |
|---------|--------|
| **`runv-help`** | Texto de ajuda: o que é o runv, comandos úteis, dicas, link do site. |
| **`runv-links`** | Links: runv.club, Portal IDEA, etc. |
| **`runv-status`** | Hostname, uptime, memória, disco, `who`, atalhos. |

Todos são **shell scripts** em **`/usr/local/bin`**, com cores ANSI simples, texto em **português**. Não dependem de Python na sessão do usuário.

## O que o usuário recebe na home (contas novas)

Quando um administrador cria a conta com **`adduser`**, o Debian copia **`/etc/skel`** para a home. Depois de rodar o módulo **`tools/`**, o skel inclui:

- **`README.md`** — explicação acolhedora: site em `~/public_html`, permissões, `runv-help`, aviso sobre arquivos públicos.
- **`.bash_aliases`** — atalhos (`ll`, `la`, `l`, `help-runv`).
- **`public_html/index.html`** — página inicial mínima em HTML estático (sem JS, sem CDN), em português.

**Observação:** no Bash do Debian, o arquivo **`~/.bashrc`** costuma ter (por padrão) um bloco que carrega **`~/.bash_aliases`** se existir. Se o usuário remover esse trecho do `.bashrc`, os aliases deixam de carregar — isso é comportamento padrão do Debian, não do runv.

## Programas globais (apt)

Pacotes como **tmux**, **lynx**, **weechat**, **mutt**, **git**, **tree**, etc. ficam **instalados no sistema**. O usuário **não** precisa de nada no skel para **executá-los**: após o admin rodar `tools.py`, eles passam a existir em `/usr/bin` (ou caminhos padrão). Ou seja:

- **Skel** ≠ instalar programas.
- **Skel** = arquivos iniciais na home.
- **apt** = programas para todos.

## Byobu

- Está **disponível** após a instalação dos pacotes.
- **Não** abre sozinho para todos no login.
- Quem quiser pode rodar **`byobu-enable`** na própria conta, quando fizer sentido.

## Como isso ajuda iniciantes

- **MOTD** orienta na hora do login (**`runv-help`**).
- **`README.md`** na home repete conceitos com calma (site, permissões).
- **`runv-links`** centraliza URLs oficiais.
- **`runv-status`** dá contexto do servidor sem precisar decorar comandos longos.

Juntos, reduzem fricção para quem nunca usou pubnix ou SSH no dia a dia.
