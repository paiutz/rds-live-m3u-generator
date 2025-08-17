# Usa Python come base
FROM python:3.11-slim

# Imposta la directory di lavoro
WORKDIR /app

# Installa dipendenze
RUN pip install flask requests

# Copia lo script (il nome ha spazi, quindi usiamo le virgolette)
COPY "rdslive.epg.py" .

# Rinomina il file per rimuovere gli spazi
RUN mv "rdslive.epg.py" app.py

# Espone la porta
EXPOSE 5000

# Esegui l'applicazione
CMD ["python", "app.py"]
