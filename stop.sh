#!/bin/bash
# tmx4ml+reup stop script

PID_FILE="server.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "⚠️ No running server detected (missing $PID_FILE)."
    # Fallback search for a running process
    PID=$(pgrep -f "main.py")
    if [ -n "$PID" ]; then
        echo "🔍 Found main.py running on PID: $PID. Stopping..."
        kill "$PID"
        echo "✔️ Server stopped."
    else
        echo "❌ Server does not appear to be running."
    fi
    exit 0
fi

PID=$(cat "$PID_FILE")
if ps -p "$PID" > /dev/null 2>&1; then
    echo "🛑 Stopping tmx4ml+reup server (PID: $PID)..."
    kill "$PID"
    # Wait for process to fully terminate
    for i in {1..5}; do
        if ! ps -p "$PID" > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    rm -f "$PID_FILE"
    echo "✔️ Server stopped successfully."
else
    echo "🧹 Server process was not running, cleaning up stale PID file."
    rm -f "$PID_FILE"
fi
