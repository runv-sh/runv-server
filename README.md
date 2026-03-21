# runv-server

Repositório de automação e documentação para **runv.club** (pubnix Debian).

## Gemini (Molly Brown)

O capsule de cada utilizador **não** está em `gemini://runv.club/USERNAME` (path `/USERNAME`). O formato correcto no Molly Brown é **`gemini://runv.club/~USERNAME/`** (path **`/~USERNAME/`**, tilde **colado** ao nome). Links com slash extra (`gemini://runv.club/~/USERNAME/`) devem redireccionar após **`setup_alt_protocols.py` v0.11+** com **`--force`** no servidor. Requer Molly a correr, symlink em `/var/gemini/users/USERNAME`, home e `public_gemini` atravessáveis — ver [`scripts/docs/alt_protocols.md`](scripts/docs/alt_protocols.md).
