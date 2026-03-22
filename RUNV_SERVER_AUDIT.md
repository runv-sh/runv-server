# RUNV_SERVER_AUDIT.md

Auditoria de saúde do repositório **runv-server** (foco: coerência arquitetural, segurança, operação, regressão pós-restauro).  
**Escopo:** código e documentação de produto sob `scripts/`, `terminal/`, `site/`, `tools/`, `email/`, `patches/`, raiz (`README.md`, `INSTALL.md`, `until.md`). A pasta `.cursor/` (skills do editor) **não** faz parte da stack runv em produção; se estiver versionada ou em staging em massa, tratar como ruído local (ver secção 9 e apêndice).

**Método:** leitura de ficheiros, `python -m compileall` nos pacotes do projeto, `git log` / `git status` / `HEAD`. Não foi executado `bandit`, `ruff`, `pytest` nem deploy real — onde não corremos ferramenta, está marcado **não verificado**.

**Data do snapshot:** árvore de trabalho com `HEAD` = `fecaf6bf8be44d261dfe989470b99feb5117147a` (*small note*).

---

## 1. Resumo executivo

O desenho **documentado** (fila SSH `entre` → revisão → `create_runv_user.py` → `users.json` → `build_directory.py` → `members.json` público) **bate com o código** nas áreas críticas verificadas. Não foi encontrado `shell=True` em `.py` do produto (apenas menções em comentários). A fila usa criação exclusiva de ficheiros (`O_EXCL`). O JSON público em `build_directory.py` **filtra** campos sensíveis conhecidos. Há **duplicação intencional** de regras de validação entre `terminal/entre_core.py` e `scripts/admin/create_runv_user.py`, com risco real de **deriva**. **Testes automatizados** quase inexistentes no produto; **CI** no repositório do projeto **não verificado** na raiz (não há workflow óbvio dedicado ao runv). O **restauro para um commit antigo** deixa o histórico local com commits posteriores não aplicados ao `HEAD` — risco de regressão **depende do diff não analisado linha-a-linha**. O estado `git` local mostra **staging massivo de `.cursor/skills/`** (milhares de ficheiros), o que é **incoerente** com um repositório de infraestrutura enxuto e deve ser corrigido antes de qualquer push.

---

## 2. Veredito global

**Salvageable with refactors** (pt: *salvável com refactors incrementais*).

**Justificativa:** a arquitetura não está “partida” no núcleo (separação entre fila e provisionamento mantém-se no código). Os problemas dominantes são **governança de repo** (staging `.cursor/`), **ausência de barreiras automáticas** (CI/testes), **deriva de validação** entre módulos, e **incerteza** sobre o que ficou para trás ao voltar o `HEAD` a `fecaf6b`. Nada disto exige “rebuild” total do sistema; exige **disciplina** e **pequenos hardenings** + eventual **cherry-pick** de commits posteriores após revisão.

---

## 3. O que já está correto (com evidência)

| Afirmação | Evidência |
|-----------|-----------|
| `terminal/` declara que não cria contas Linux; orquestra fila/log/email | Docstring `entre_app.py` L5–L6. |
| Provisionamento canónico documentado em `create_runv_user.py` | Docstring inicial L3–L37 (ordem adduser → chave → espaços públicos → jail → quota → JSON). |
| Fila com ficheiro novo não sobrescreve pedido existente | `entre_core.py` `save_request_json`: `os.open(..., O_CREAT\|O_EXCL)` L487–L490. |
| `build_directory.py` só emite `username`, `since`, `path`, opcional `homepage_mtime` | Loop `main()` L88–L105; não lê `email` nem fingerprint para o output público. |
| Caminhos canónicos alinhados entre `config.example.toml`, `INSTALL.md`, `until.md` | `queue_dir` `/var/lib/runv/entre-queue` — `terminal/config.example.toml` L5; `users.json` `/var/lib/runv/users.json` — `build_directory.py` default L32; email `/etc/runv-email.json` — `entre_core.py` L315 e docs email. |
| Locks em `users.json` no provisionamento/remoção/atualização | `create_runv_user.py` `fcntl.flock` ~L683; `del-user.py` ~L391; `update_user.py` ~L285. |
| `starthere.py` usa `subprocess.run` com lista; `shlex` para **quoting de mensagens**, não para executar shell composto | `starthere.py` L122–L125, L472, L510. |
| `python -m compileall` nos diretórios do produto concluiu sem erro (exit 0) | Comando executado: `scripts`, `terminal`, `site`, `tools`, `email`, `patches`. |

---

## 4. Problemas críticos

1. **Estado Git com staging massivo em `.cursor/skills/`** — polui o repositório, dificulta review, risco de commit acidental de milhares de ficheiros não relacionados com runv. **Evidência:** `git status -sb` (saída local; primeiras linhas mostram `A .cursor/skills/...` em cascata). **Não verificado** se `.gitignore` deveria excluir `.cursor/skills` no teu fluxo; o facto de estarem **staged** é o problema operacional imediato.

2. **`HEAD` fixado em `fecaf6b` com histórico linear contendo commits posteriores** — qualquer “restauro” a este ponto **remove** do working tree correções que possam existir em commits como `42f7676` (*fixed a lot of stuff*), etc. **Evidência:** `git log --oneline -20` (primeira entrada `fecaf6b`, segunda `42f7676`). **Não verificado:** conteúdo exacto desses commits (seria necessário `git show` / diff).

3. **Deriva de validação duplicada** — `USERNAME_PATTERN`, `EMAIL_PATTERN`, `RESERVED_USERNAMES`, `ALLOWED_KEY_TYPES` repetidos em `entre_core.py` (L33–L74 aprox.) e `create_runv_user.py` (L72–L80 aprox.). Comentário admite não importar em runtime (L31–L32 `entre_core.py`). Qualquer alteração unilateral **quebra** a promessa de alinhamento.

---

## 5. Achados por severidade

### Alta

- **H1 — Governança Git / `.cursor/skills` em staging:** ver crítico 1.

- **H2 — Regressão por checkout antigo:** ver crítico 2. Até comparar diff com `origin/main` ou commits intermediários, o estado de “segurança e arquitectura mais novos” é **incerto**.

### Média

- **M1 — Ausência de suite de testes no núcleo:** apenas `email/tests/test_mailgun_client.py` encontrado sob `email/`; **não verificado** execução `pytest`. Não há testes automatizados evidentes para `entre_core`, `build_directory`, ou locks de `users.json`.

- **M2 — Documentação “cron vs sem cron”:** [INSTALL.md](INSTALL.md) L87–L91 recomenda cron para `build_directory.py`; [site/README.md](site/README.md) L19 afirma regeneração via `create_runv_user.py` e `genlanding.py` “(sem cron)”. **Não é contradição lógica** (são modos alternativos), mas **operadores novos** podem interpretar mal o que é obrigatório.

- **M3 — `create_runv_user.py` refresh da landing:** default `--landing-document-root` = `/var/www/runv.club/html` (L1562–L1568). Se o path **não existir**, o refresh é **omitido** (L1886–L1887). [site/README.md](site/README.md) L23 sugere fluxo “automático” — na prática depende do DocumentRoot existir.

### Baixa

- **L1 — Ficheiros JSON na fila contêm PII** (email, fingerprint) — **esperado**; mitigado por directório `entre-queue` `0o700` em `setup_entre.py` ~L909. Não é leak web; é superfície em disco para root/`entre`.

- **L2 — `until.md` é documento humano** — coerente com o código verificado nas secções de caminhos e separação entre módulos; não substitui ADRs versionadas.

---

## 6. Documentação vs código

| Tópico | Doc | Código | Avaliação |
|--------|-----|--------|-----------|
| `entre` não provisiona Unix | `terminal/README.md`, `entre_app.py` | Sem `adduser`/`useradd` em `entre_app.py` (grep sem matches); `setup_entre.py` usa `useradd` **só** para criar a conta de sistema `entre` (L246–L254) | **Coerente** (distinção: bootstrap do utilizador `entre` vs membro). |
| Membros públicos filtrados | `site/README.md`, `build_directory.md` | `build_directory.py` L96–L105 | **Coerente**. |
| Ordem de instalação | `INSTALL.md` L22–L31 | Scripts existem nos caminhos citados | **Coerente** a nível de inventário; dependências finas (ex. Apache antes de TLS) são assunto operacional, **não verificado** em ambiente real. |
| Regeneração `members.json` | `site/README.md` L19–L23 | `create_runv_user.py` `try_refresh_landing_members_json` L1100–L1145; `genlanding.py` `refresh_members_json_in_document_root` L148+ | **Coerente** com **nuance:** refresh em `create_runv_user` só corre se `landing_document_root` existir. |
| Cron | `INSTALL.md` L87–L91 | Não é imposto pelo código | **Opcional**; doc correta como recomendação, não como invariante. |

---

## 7. Riscos do “restauro do shell antigo”

- **R1:** Commits posteriores no mesmo ramo podem conter correções de segurança, MOTD, email ou landing; com `HEAD` em `fecaf6b`, o clone **não** as inclui. **Mitigação:** `git log --oneline HEAD..origin/main` (ou ramo relevante) + revisão selectiva. **Não executado** na íntegra nesta auditoria.

- **R2:** Documentação no disco (`until.md`, `RUNV_SERVER_AUDIT.md`) pode ser **mais nova** que o `HEAD` se foram criadas após o reset; isso gera **aparente** inconsistência “docs descrevem X, histórico antigo não tem Y”. Tratar como problema de **processo** (tag/branch de docs vs código).

- **R3:** Expectativas “nova arquitectura” vs árvore antiga — sem diff, qualquer afirmação sobre regressão específica é **especulação**; apenas o desalinhamento `HEAD`/histórico é **facto**.

---

## 8. Segurança (síntese)

| Área | Resultado |
|------|-----------|
| `shell=True` em Python do produto | **Não encontrado** (grep em `z:\Code\runv-server\**\*.py` excluindo skills embutidas no grep inicial; matches eram `.cursor/skills` ou comentários em `tools.py` / `mailer.py`). |
| Fila — colisão / overwrite | **Mitigado** — `O_EXCL` (`entre_core.py` L487–L490). |
| Dados públicos | **Filtragem explícita** em `build_directory.py`; campos sensíveis do pedido **não** são copiados para `members.json`. |
| Entrada SSH / chaves | Normalização + rejeição de chave privada (`entre_core.py` L189–L216); limites de tamanho (L88–L92). |
| `users.json` concorrente | **flock** em scripts admin principais (ver secção 3). |
| SSH `entre` modes vazios / PAM | `setup_entre.py` documenta riscos (L6–L86 docstring); **hardening depende** de flags e política operacional — **não auditoria de configuração em produção** (não verificado). |

---

## 9. Operação / deploy

- **Ordem INSTALL:** faz sentido: bootstrap → ferramentas globais → site → dados públicos → email → terminal → operações diárias — alinhada com dependências lógicas (Apache antes de publicar; `users.json` antes de consumo).

- **Paths hardcoded:** presentes mas **consistentes** entre docs e defaults (`/var/lib/runv`, `/opt/runv/terminal`, `/etc/runv-email.json`). Flags permitem override.

- **CI/CD:** **não verificado** workflow em `.github/workflows` na raiz do projeto runv (glob não devolveu pipelines do produto; apenas skills sob `.cursor`). Tratar como **lacuna** se o remoto depender de disciplina manual.

- **Smoke compile:** `compileall` OK nos pacotes listados.

---

## 10. Matriz: manter / corrigir leve / refactor / rebuild

| Área | Classificação | Justificativa |
|------|---------------|---------------|
| **terminal/** | **FIX LIGHTLY** + **REFACTOR** (validação) | Núcleo correcto; extrair/shared policy ou testes contractuais reduziria deriva. |
| **scripts/admin/** | **KEEP AS IS** (com disciplina) | `create_runv_user.py` é grande mas é a fonte canónica; mexer sem testes é arriscado. |
| **site/** | **KEEP AS IS** | `build_directory.py` é claro; `genlanding.py` integra bem. |
| **tools/** | **KEEP AS IS** | Manifest + cópias; risco baixo se mantiver `no shell=True`. |
| **email/** | **FIX LIGHTLY** | Boa separação Mailgun/legado; falta é mais **testes/CI** do que redesign. |
| **docs/** | **FIX LIGHTLY** | Harmonizar narrativa cron vs hooks; referenciar condição do DocumentRoot. |
| **patches/** | **KEEP AS IS** | Auxiliar; depende de contexto IRC/protocolos. |

**Rebuild:** nenhuma área justifica rebuild total com base nesta auditoria.

---

## 11. Ficheiros que merecem atenção primeiro

1. **Estado Git** — limpar unstaging de `.cursor/skills/` (ou mover skills para fora do repo).  
2. `terminal/entre_core.py` + `scripts/admin/create_runv_user.py` — política de validação duplicada.  
3. `scripts/admin/create_runv_user.py` — `--landing-document-root` / refresh silencioso.  
4. `site/README.md` + `INSTALL.md` — alinhar linguagem sobre cron e pré-requisitos do DocumentRoot.  
5. `email/tests/test_mailgun_client.py` — expandir padrão de testes ou documentar como única suite.  
6. **Histórico Git** — decidir se `fecaf6b` é alvo de trabalho ou se devem integrar commits posteriores.  
7. `until.md` — útil; manter como índice, não como substituto de testes.

---

## 12. Próximas 10 acções (ordenadas)

1. Resolver staging de `.cursor/skills/` (reset/unstage ou `.gitignore` + remoção do índice).  
2. `git log --oneline HEAD..origin/main` e listar commits a rever para possível cherry-pick.  
3. Correr `pytest email/tests/` no ambiente (confirmar dependências).  
4. Teste manual: fluxo `entre` até gerar JSON na fila; confirmar permissões `0700` no directório da fila.  
5. Teste manual: `build_directory.py --dry-run` com cópia sanitizada de `users.json`.  
6. Teste manual: `create_runv_user.py --help` e validar que `--landing-document-root` aponta para o DocumentRoot real em produção.  
7. Documentar em runbook: “se DocumentRoot não existir, members não atualiza”.  
8. Adicionar checklist de release: comparar regex `USERNAME_PATTERN` / listas reservadas entre os dois ficheiros.  
9. (Opcional) Introduzir CI mínimo: `python -m compileall` + `pytest email/tests`.  
10. Revisão de `setup_entre.py` em ambiente de staging com o modo de auth escolhido (empty-password vs shared-password).

---

## 13. Smoke tests manuais seguros (próximos)

- `python3 -m py_compile terminal/entre_app.py terminal/entre_core.py terminal/setup_entre.py`  
- `python3 site/build_directory.py --users-json site/example-users.json --dry-run`  
- `python3 -m compileall -q scripts terminal site tools email patches`  
- `sshd -t` **apenas** após alterações de configuração SSH em VM de teste (não em produção sem janela).  
- Ler um `.json` da fila com `jq` no servidor (root) para validar schema esperado pelo runbook admin.

---

## 14. Questões abertas / incertezas

- **Conteúdo exacto** dos commits entre `fecaf6b` e `origin/main` — **não verificado** (diff não feito).  
- **Configuração real** em produção (PAM, firewall, Mailgun allowlist) — **não verificado**.  
- **Bandit / Ruff / mypy** — **não executados**; ausência de config no repo não foi provada formalmente além de não haver `pyproject.toml` na raiz.  
- Se `public/` HTML cumpre 100% a regra do rodapé `admin@runv.club` — **não verificado** página a página.

---

## 15. Apêndice de evidências (afirmações não triviais)

| ID | Afirmação | Ficheiro:código |
|----|-----------|-----------------|
| E1 | `entre` não provisiona membro | `terminal/entre_app.py` L5–L6 |
| E2 | Fila atómica | `terminal/entre_core.py` L478–L498 |
| E3 | Payload inclui email + fingerprint (fila, não público) | `terminal/entre_core.py` L512–L519 |
| E4 | Output público mínimo | `site/build_directory.py` L96–L105 |
| E5 | Default `users.json` | `site/build_directory.py` L31–L33 |
| E6 | Lock metadata | `scripts/admin/create_runv_user.py` L117, L683 |
| E7 | Refresh landing | `scripts/admin/create_runv_user.py` L1100–L1145, L1562–L1568, L1872–L1876 |
| E8 | `subprocess` lista em refresh | `scripts/admin/create_runv_user.py` L1119–L1130 |
| E9 | `useradd` só para `entre` bootstrap | `terminal/setup_entre.py` L240–L255 |
| E10 | Queue dir mode | `terminal/setup_entre.py` ~L909 (`qd.chmod(0o700)`) |
| E11 | Duplicação regex username | `terminal/entre_core.py` L33; `scripts/admin/create_runv_user.py` L72 |
| E12 | `mkstemp` para ssh-keygen | `terminal/entre_core.py` L218–L242 |
| E13 | `members.json` repo placeholder | `site/public/data/members.json` → `[]` |
| E14 | HEAD commit | `git rev-parse` → `fecaf6bf8be44d261dfe989470b99feb5117147a` |
| E15 | Staging `.cursor/skills` | `git status -sb` (primeiras entradas `A .cursor/skills/...`) |

---

*Fim do relatório.*
