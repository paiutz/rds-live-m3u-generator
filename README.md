# RDS Live M3U Generator with EPG Support

![Python](https://img.shields.io/badge/python-3.11-blue.svg)
![Flask](https://img.shields.io/badge/flask-2.3.3-green.svg)
![Podman](https://img.shields.io/badge/podman-4.0-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

Servizio Flask che genera automaticamente playlist M3U con supporto EPG (Electronic Program Guide) per i canali TV RDS Live.

## Caratteristiche

- 📺 **Estrazione Canali Live TV**: Estrazione automatica delle informazioni sui canali dalla piattaforma RDS Live.
- 🔄 **Aggiornamento Automatico**: Playlist e dati EPG sempre aggiornati.
- 🎬 **Estrazione URL Streaming**: Ottieni gli URL dei flussi di ogni canale.
- 📋 **Supporto EPG**: Generazione della guida elettronica ai programmi in formato XMLTV.
- 🌐 **Interfaccia Web**: Dashboard intuitiva con statistiche e controlli.
- 🐳 **REST API**: Accesso programmabile a playlist e dati.
- 📦 **Pronto per Container**: Include gestione tramite Podman per il deploy.

## Avvio Rapido

### Con Podman (Consigliato)

1. Clona il repository:
    ```
    git clone https://github.com/yourusername/rds-live-m3u-generator.git
    cd rds-live-m3u-generator
    ```
2. Costruisci ed avvia il container:
    ```
    chmod +x run_container.sh
    ./run_container.sh
    ```
3. Accedi all'interfaccia web:
    ```
    http://localhost:5000
    ```

### Avvio diretto con Python

1. Installa le dipendenze:
    ```
    pip install -r requirements.txt
    ```
2. Avvia l'applicazione:
    ```
    python rdslive.epg.py
    ```

## Utilizzo

### Interfaccia Web

- **Dashboard:** `http://localhost:5000`
- **Playlist M3U:** `http://localhost:5000/m3u`
- **EPG XMLTV:** `http://localhost:5000/epg.xml`
- **Scarica M3U:** `http://localhost:5000/playlist`
- **Scarica EPG:** `http://localhost:5000/epg-download`

### API Endpoints

| Endpoint          | Metodo | Descrizione                       |
|-------------------|--------|-----------------------------------|
| `/`               | GET    | Dashboard web                     |
| `/m3u`            | GET    | Playlist M3U per IPTV             |
| `/epg`            | GET    | Guida EPG XMLTV                   |
| `/playlist`       | GET    | Scarica M3U con URL streaming     |
| `/epg-download`   | GET    | Scarica EPG XMLTV                 |
| `/api/stats`      | GET    | Statistiche servizio              |
| `/api/update`     | POST   | Aggiornamento manuale             |
| `/api/channels`   | GET    | Lista canali in JSON              |

## Gestione Container

./manage.sh build # Crea immagine
./manage.sh run # Avvia container
./manage.sh stop # Ferma container
./manage.sh restart # Riavvia container
./manage.sh logs # Visualizza log
./manage.sh shell # Entra nella shell del container
./manage.sh remove # Rimuove container e immagine

text

## Configurazione

### Variabili d'Ambiente

| Variabile               | Default                         | Descrizione                       |
|------------------------ |---------------------------------|-----------------------------------|
| `SECRET_KEY`            | your_strong_secret_key_here     | Chiave segreta per token          |
| `BASE_URL`              | https://rds.live                | URL base RDS Live                 |
| `UPDATE_INTERVAL`       | 300                             | Intervallo aggiornamento (sec)    |
| `MAX_WORKERS`           | 5                               | Worker concorrenti massimi        |
| `REQUEST_TIMEOUT`       | 15                              | Timeout richieste (sec)           |
| `CACHE_EXPIRY`          | 180                             | Scadenza cache (sec)              |
| `PORT`                  | 5000                            | Porta del servizio                |
| `DEBUG`                 | False                           | Modalità debug                    |
| `EPG_URL`               | http://epg.iptv.ro/epg.xml      | Fonte guida EPG                   |
| `EPG_UPDATE_INTERVAL`   | 3600                            | Intervallo update EPG (sec)       |

**Utilizzo fonte EPG personalizzata:**

export EPG_URL="https://your-epg-source.com/epg.xml"

text

## Integrazione con IPTV Player

### VLC Media Player
1. Apri VLC
2. Vai su Media > Apri flusso di rete
3. Inserisci la URL M3U: `http://localhost:5000/m3u`
4. In Preferenze > Input/Codec aggiungi fonte EPG: `http://localhost:5000/epg.xml`

### Kodi
1. Installa l'addon IPTV Simple Client
2. Imposta:
   - Playlist: `http://localhost:5000/m3u`
   - EPG: `http://localhost:5000/epg.xml`

### Altri lettori

Quasi tutti i player IPTV moderni supportano M3U + EPG:
- **Playlist URL:** `http://localhost:5000/m3u`
- **EPG URL:** `http://localhost:5000/epg.xml`

## Sviluppo

### Prerequisiti

- Python 3.11+
- Flask 2.3.3+
- Requests
- Podman (opzionale per container)

### Setup Ambiente di Sviluppo

git clone https://github.com/yourusername/rds-live-m3u-generator.git
cd rds-live-m3u-generator
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python rdslive.epg.py
