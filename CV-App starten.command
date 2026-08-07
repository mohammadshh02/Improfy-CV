#!/bin/bash
cd "/Users/ikromsdikiy/Desktop/Improfy/cv_system"
# schon laufenden Server beenden
pkill -f "server.py" 2>/dev/null
sleep 1
# App starten
PORT=8000 python3 server.py &
sleep 2
# Browser öffnen
open "http://localhost:8000"
echo ""
echo "  Die CV-App läuft jetzt. Browser sollte sich öffnen."
echo "  Zum Beenden dieses Fenster schließen."
wait
