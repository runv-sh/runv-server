#!/usr/bin/env python3
"""
Aplicação de aviso quando os registos no runv.club estão fechados.
Operado via ForceCommand no OpenSSH.

ASCII ART CLOSED e mensagem amigável.
"""
import sys

def main() -> int:
    # Cores ANSI
    red = "\033[91m"
    green = "\033[92m"
    reset = "\033[0m"

    ascii_art = f"""{red}
                                    
                                    
 ▄▄▄▄ ▄▄     ▄▄▄   ▄▄▄▄ ▄▄▄▄▄ ▄▄▄▄  
██▀▀▀ ██    ██▀██ ███▄▄ ██▄▄  ██▀██ 
▀████ ██▄▄▄ ▀███▀ ▄▄██▀ ██▄▄▄ ████▀ 
                                    
{reset}"""

    print(ascii_art)
    print("  Olá, aguarde pela abertura dos registros :)\n")
    print(f"  Qualquer dúvida: {green}admin@runv.club{reset}\n")

    try:
        input("  [Pressione Enter para sair...]")
    except (EOFError, KeyboardInterrupt):
        pass

    return 0

if __name__ == "__main__":
    sys.exit(main())
