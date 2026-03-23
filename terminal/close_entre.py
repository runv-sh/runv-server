#!/usr/bin/env python3
"""
Script para fechar temporariamente os registros do terminal `entre`.
Ele edita o ficheiro de drop-in do SSH para usar `closed_app.py` em vez de `entre_app.py`.

Executar como root no servidor Debian.
"""
import os
import sys
import subprocess
from pathlib import Path

def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)

def require_root() -> None:
    if os.geteuid() != 0:
        eprint("Execute como root (sudo).")
        raise SystemExit(1)

def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        raise RuntimeError(f"Falhou: {' '.join(cmd)}\n{err}")

def main() -> int:
    require_root()
    
    dropin_path = Path("/etc/ssh/sshd_config.d/runv-entre.conf")
    if not dropin_path.is_file():
        eprint(f"Erro: o ficheiro de configuração SSH {dropin_path} não foi encontrado.")
        eprint("Parece que o setup do terminal `entre` ainda não foi executado ou está corrompido.")
        return 1

    content = dropin_path.read_text(encoding="utf-8")
    
    if "closed_app.py" in content:
        print("Os registros já parecem estar fechados (closed_app.py detetado na config).")
        return 0

    if "entre_app.py" not in content:
        eprint("Aviso: 'entre_app.py' não encontrado na configuração. Modificação ignorada por segurança.")
        return 1

    # Substitui a app principal pela fechada
    new_content = content.replace("entre_app.py", "closed_app.py")
    
    # Grava novamente
    dropin_path.write_text(new_content, encoding="utf-8")
    print(f"Modificado {dropin_path.name}: entre_app.py -> closed_app.py")

    # Testa as confiugrações do ssh
    print("Testando a configuração com 'sshd -t'...")
    try:
        run(["sshd", "-t"])
    except RuntimeError as e:
        # Tenta reverter
        eprint(f"Erro de sshd detectado: {e}")
        eprint("Revertendo as mudanças.")
        dropin_path.write_text(content, encoding="utf-8")
        return 1

    print("sshd -t: OK.")

    # Recarrega o SSH
    try:
        run(["systemctl", "reload", "ssh"])
        print("Serviço SSH recarregado (reload).")
    except RuntimeError:
        try:
            run(["systemctl", "reload", "sshd"])
            print("Serviço SSH recarregado (reload).")
        except RuntimeError as e:
            eprint(f"Aviso: Não foi possível fazer o recarregamento do SSH de forma automática: {e}")
            eprint("Por favor recarregue manualmente: systemctl reload ssh")
            
    print("\n[+] Fechado com sucesso! Agora as ligações serão encaminhadas para o ecrã CLOSED.")
    print("Para reabrir os registros no futuro, basta correr 'sudo ./setup_entre.py' novamente.")

    return 0

if __name__ == "__main__":
    sys.exit(main())
