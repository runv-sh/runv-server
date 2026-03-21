# runv-server

Repositório de automação e documentação para **runv.club** (pubnix Debian).

## Gemini (Molly Brown)

O capsule de cada utilizador **não** está em `gemini://runv.club/USERNAME` (isso seria o path `/USERNAME`, que no servidor não corresponde à home). O formato correcto é **`gemini://runv.club/~/USERNAME/`** (path **`/~/USERNAME/`**), ou **`gemini://runv.club/~USERNAME/`** (redirect para o anterior). Requer Molly a correr, symlink em `/var/gemini/users/USERNAME`, home e `public_gemini` atravessáveis pelo utilizador do serviço — ver [`scripts/docs/alt_protocols.md`](scripts/docs/alt_protocols.md).
