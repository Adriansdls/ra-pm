#!/bin/bash
# ra-pm installer — run once per machine
# Registers the MCP server and UserPromptSubmit hook with Claude Code.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${RA_PYTHON:-python3}"

echo "ra-pm: installing..."

# 1. Dependencies
"$PYTHON" -m pip install -q -r "$SCRIPT_DIR/requirements.txt"

# 2. MCP server
claude mcp add ra-pm "$PYTHON" "$SCRIPT_DIR/server.py"
echo "  ✓ MCP server registered (ra-pm)"

# 3. UserPromptSubmit hook
SETTINGS="$HOME/.claude/settings.json"
HOOK_CMD="$PYTHON $SCRIPT_DIR/hook.py"

if [ ! -f "$SETTINGS" ]; then
    echo '{}' > "$SETTINGS"
fi

# Check if hook already registered
if grep -q "hook.py" "$SETTINGS" 2>/dev/null; then
    echo "  ✓ Hook already registered — skipping"
else
    # Use Python to safely patch the JSON
    "$PYTHON" - <<PYEOF
import json, sys
with open("$SETTINGS") as f:
    s = json.load(f)
hook_entry = {
    "hooks": [{"type": "command", "command": "$HOOK_CMD", "timeout": 8}]
}
hooks = s.setdefault("hooks", {})
ups = hooks.setdefault("UserPromptSubmit", [])
ups.append(hook_entry)
with open("$SETTINGS", "w") as f:
    json.dump(s, f, indent=2)
print("  ✓ Hook registered (UserPromptSubmit)")
PYEOF
fi

echo ""
echo "ra-pm installed. Restart Claude Code to activate."
echo "Data stored in: ~/.ra/"
echo "Quickstart: call mcp__ra-pm__ra_boot in any Claude session."
