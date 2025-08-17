---
title: RDS Live M3U Generator
emoji: 📺
colorFrom: blue
colorTo: red
sdk: docker
pinned: false
---

# RDS Live M3U Generator with EPG Support

Servizio Flask che genera automaticamente playlist M3U con supporto EPG per i canali TV RDS Live.

## Utilizzo

- **Dashboard**: Interfaccia principale con statistiche
- **Playlist M3U**: `/m3u` - Per player IPTV
- **EPG XML**: `/epg.xml` - Guida programmi
- **Download**: `/playlist` e `/epg-download`

## Endpoints API

- `/api/stats` - Statistiche servizio
- `/api/channels` - Lista canali JSON
- `/api/update` - Aggiornamento manuale
