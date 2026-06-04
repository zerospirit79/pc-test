#!/bin/bash -efu
# Validate pc-test Python package (PEP 8 via ruff, unit tests, legacy shell l10n).

set -o pipefail
ERROR=0
ROOT="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}${ROOT}/python3"

echo "*** Compiling Python modules..."
if ! python3 -m compileall -q "${ROOT}/python3/pc_test"; then
	ERROR=1
fi

if command -v ruff >/dev/null 2>&1; then
	echo "*** PEP 8 / style (ruff)..."
	if ! ruff check "${ROOT}/python3/pc_test"; then
		ERROR=1
	fi
	if ! ruff format --check "${ROOT}/python3/pc_test"; then
		ERROR=1
	fi
else
	echo "*** ruff not installed — skipping PEP 8 check (install: apt-get install python3-module-ruff)"
fi

if [ -d "${ROOT}/tests" ]; then
	echo "*** Unit tests..."
	if python3 -m pytest --version >/dev/null 2>&1; then
		python3 -m pytest "${ROOT}/tests" -q || ERROR=1
	else
		python3 -m unittest discover -s "${ROOT}/tests" -p 'test_*.py' -v || ERROR=1
	fi
fi

if [ -x /usr/bin/shellcheck ] || command -v shellcheck >/dev/null 2>&1; then
	echo "*** Checking remaining shell assets (l10n only)..."
	bindirs="SCRIPTDIR:usr/libexec/pc-test"
	mapfile -t l10n_sh < <(find usr/libexec/pc-test/l10n -type f -name '*.sh' | sort)
	for fname in "${l10n_sh[@]}"; do
		# l10n *.sh are bash snippets (sourced), not standalone scripts — no shebang
		shellcheck -s bash -P "$bindirs" -e SC2034,SC2154 "$fname" || ERROR=1
	done
fi

exit "$ERROR"
