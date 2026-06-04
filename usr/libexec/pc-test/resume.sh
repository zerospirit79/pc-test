#!/bin/bash
# Copyright (C) 2024-2026, ALT Linux Team
d="$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")"
exec "$d/resume.py" "$@"
