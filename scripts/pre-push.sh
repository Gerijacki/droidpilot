#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/pre-push.sh — DroidPilot pre-push hook
#
# Instala este hook una sola vez:
#   ln -sf "$(pwd)/scripts/pre-push.sh" .git/hooks/pre-push
#
# Replica la pipeline CI (lint → tests → build) antes de cada git push.
# Si cualquier paso falla, el push queda bloqueado.
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

PASS="${GREEN}✔${RESET}"
FAIL="${RED}✖${RESET}"
ARROW="${CYAN}▶${RESET}"

fail() {
    echo -e "\n${RED}${BOLD}✖ Pre-push abortado:${RESET} $1"
    echo -e "${YELLOW}  Corrige los errores y vuelve a hacer push.${RESET}\n"
    exit 1
}

step() {
    echo -e "\n${ARROW} ${BOLD}$1${RESET}"
}

ok() {
    echo -e "  ${PASS} $1"
}

echo -e "\n${BOLD}╔══════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║       DroidPilot · Pre-push checks       ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${RESET}"

# ── 1. Ruff (linter) ─────────────────────────────────────────────────────────
step "Ruff — linter"
ruff check droidpilot/ tests/ || fail "ruff encontró errores de estilo/lint."
ok "ruff OK"

# ── 2. Black (formato) ───────────────────────────────────────────────────────
step "Black — formato"
black --check droidpilot/ tests/ || fail "black detectó ficheros sin formatear. Ejecuta: black droidpilot/ tests/"
ok "black OK"

# ── 3. Mypy (tipos) ──────────────────────────────────────────────────────────
step "Mypy — type check"
mypy droidpilot/ || fail "mypy encontró errores de tipos."
ok "mypy OK"

# ── 4. Pytest con coverage ───────────────────────────────────────────────────
step "Pytest — tests unitarios"
pytest \
    --tb=short \
    --cov=droidpilot \
    --cov-report=term-missing \
    -q \
    || fail "pytest: hay tests fallando."
ok "pytest OK"

# ── 5. Build check ───────────────────────────────────────────────────────────
step "Build — verificación del paquete"
TMP_BUILD=$(mktemp -d)
python3 -m build --outdir "$TMP_BUILD" --wheel 2>/dev/null \
    || { rm -rf "$TMP_BUILD"; fail "python3 -m build falló."; }
if command -v twine &>/dev/null; then
    twine check "$TMP_BUILD"/* || { rm -rf "$TMP_BUILD"; fail "twine check falló."; }
else
    echo -e "  ${YELLOW}(twine no instalado — omitiendo check de metadatos)${RESET}"
fi
rm -rf "$TMP_BUILD"
ok "build OK"

echo -e "\n${GREEN}${BOLD}✔ Todos los checks pasaron — push autorizado.${RESET}\n"
exit 0
