#!/bin/sh
# Diagnóstico rápido: pacotes, sendmail, msmtp, permissões, estado runv.
# Não imprime segredos.

set -e
echo "=== Pacotes ==="
dpkg -l msmtp msmtp-mta ca-certificates bsd-mailx 2>/dev/null || true

echo ""
echo "=== sendmail ==="
if [ -e /usr/sbin/sendmail ]; then
  ls -l /usr/sbin/sendmail
  readlink -f /usr/sbin/sendmail || true
else
  echo "Falta /usr/sbin/sendmail"
fi

echo ""
echo "=== msmtp ==="
command -v msmtp >/dev/null 2>&1 && msmtp --version || echo "msmtp não no PATH"

echo ""
echo "=== Ficheiros de configuração ==="
for f in /etc/msmtprc /etc/msmtp_aliases /root/.netrc /etc/runv-email.json; do
  if [ -f "$f" ]; then
    ls -l "$f"
  else
    echo "(ausente) $f"
  fi
done

echo ""
echo "=== Log msmtp (últimas 15 linhas, se existir) ==="
if [ -f /var/log/msmtp.log ]; then
  tail -n 15 /var/log/msmtp.log
else
  echo "(sem /var/log/msmtp.log)"
fi

echo ""
echo "=== passwordeval helper ==="
if [ -f /usr/local/lib/runv-email/netrc_password.py ]; then
  ls -l /usr/local/lib/runv-email/netrc_password.py
else
  echo "(ausente) /usr/local/lib/runv-email/netrc_password.py"
fi
