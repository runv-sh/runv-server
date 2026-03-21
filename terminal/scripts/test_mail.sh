#!/bin/sh
# Mostra no stdout o corpo que seria enviado via sendmail (sem executar sendmail).
# Uso: Ajuste variáveis e execute. Para enviar de verdade:
#   ... | /usr/sbin/sendmail -t -i
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REQUEST_ID="00000000-0000-0000-0000-000000000001"
export REQUEST_ID
printf '%s\n' "From: noreply@runv.club
To: admin@example.com
Subject: [runv] teste de notificação

Pedido de teste request_id=${REQUEST_ID}
"
