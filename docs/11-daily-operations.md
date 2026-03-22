# Operação diária (dia 2+)

[← Índice](README.md)

## Adicionar membro

1. Pedido via `entre` ou processo interno.
2. `sudo python3 scripts/admin/create_runv_user.py …` (ver `--help` no servidor).
3. Confirmar linha **constelação (bolhas)** ou corrigir com `build_directory.py` manual.

## Actualizar lista pública sem novo membro

```bash
sudo python3 REPO/site/build_directory.py \
  --users-json /var/lib/runv/users.json \
  -o /var/www/runv.club/html/data/members.json
```
(Ajustar paths ao teu DocumentRoot.)

## Após `git pull` no servidor

- `sudo python3 tools/tools.py` para MOTD/skel/bin conforme alterações.

## Notícias

- Colocar `.md` em `site/news/`, executar `site/news/publish_news.py`; depois voltar a copiar `public/` ou correr `genlanding.py` se aplicável.

## Wiki

- Fontes em `site/wiki/` com gerador `build_wiki.py` (estrutura no repo).

## Email

- Testes documentados no módulo `email/` (`send_test_mail.sh`, etc., se presentes).

Próximo: [12-security-and-privacy.md](12-security-and-privacy.md).
