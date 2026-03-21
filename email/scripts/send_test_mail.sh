#!/bin/sh
# Envia um email de teste mínimo via mail(1) -> sendmail (msmtp).
# Uso: ./send_test_mail.sh destino@exemplo.com
# Requer: bsd-mailx, msmtp-mta (sendmail).

set -e
if [ -z "${1:-}" ]; then
  echo "Uso: $0 destino@exemplo.com" >&2
  exit 1
fi
DEST="$1"
SUBJ="[runv.club] Teste send_test_mail.sh"
BODY="Mensagem de teste gerada em $(date -u +%Y-%m-%dT%H:%M:%SZ)."

if ! command -v mail >/dev/null 2>&1; then
  echo "Comando 'mail' não encontrado. Instale bsd-mailx." >&2
  exit 1
fi

printf '%s\n' "$BODY" | mail -s "$SUBJ" "$DEST"
echo "Pedido de envio feito para $DEST (verifique caixa e /var/log/msmtp.log)."
