#!/bin/bash
# tmx4ml+reup start script

PID_FILE="server.pid"
LOG_FILE="server.log"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "⚠️ Server is already running (PID: $PID)."
        exit 1
    else
        echo "🧹 Removing stale PID file."
        rm -f "$PID_FILE"
    fi
fi

echo "🚀 Starting tmx4ml+reup server in headless background mode..."
nohup uv run main.py > "$LOG_FILE" 2>&1 &
NEW_PID=$!

# Give it a second to see if it crashed immediately
sleep 1
if ps -p "$NEW_PID" > /dev/null 2>&1; then
    echo "$NEW_PID" > "$PID_FILE"
    echo "✔️ Server started successfully in the background!"
    echo "  - Process ID (PID): $NEW_PID"
    echo "  - Output log:       $LOG_FILE"
    echo "  - You can now safely close your SSH session."
else
    echo "❌ Server failed to start. Check $LOG_FILE for details."
    exit 1
fi
