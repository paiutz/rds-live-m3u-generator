#!/bin/bash
# run_container.sh

echo "Costruendo l'immagine Podman..."
podman build -t rds-live-epg .

echo "Fermando il container esistente (se presente)..."
podman stop rds-live-epg 2>/dev/null || true
podman rm rds-live-epg 2>/dev/null || true

echo "Avviando il container..."
podman run -d \
    --name rds-live-epg \
    -p 5000:5000 \
    --restart unless-stopped \
    rds-live-epg

echo "Container avviato con successo!"
echo "Accedi all'interfaccia web: http://localhost:5000"
echo "Per vedere i log: podman logs -f rds-live-epg"
