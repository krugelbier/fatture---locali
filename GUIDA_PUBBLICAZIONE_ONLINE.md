# Guida Completa alla Pubblicazione Online
## Fatture Locali & HACCP • Krügel – Lavis & Cafè L’Incontro – Pergine

Questa guida spiega come pubblicare l'applicazione su Internet in modo sicuro, con certificato **HTTPS**, **accesso protetto da password**, **persistenza dei dati** e **supporto all'uso contemporaneo** da tablet e computer presenti nei due locali di Lavis e Pergine.

---

### 1. Architettura Tecnica del Progetto

* **Linguaggio**: Python 3 (3.10, 3.11, 3.12, 3.13 o 3.14).
* **Framework Web**: **FastAPI** con server ASGI **Uvicorn** (asincrono, scalabile e ad alte prestazioni).
* **Frontend**: Single Page Application (SPA) responsive in HTML5, Tailwind CSS e JavaScript nativo, ottimizzata per tablet da cucina/banco e per PC da ufficio. Non richiede Node.js né procedure di build: i file statici vengono serviti direttamente da FastAPI.
* **Database**: **SQLite 3** configurato in modalità ad alta concorrenza **WAL (Write-Ahead Logging)**.
* **Comando di avvio standard**:
  ```bash
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
  ```

---

### 2. Dove Vengono Salvati i Dati

Tutti i dati dell'applicazione risiedono in un unico file di database: **`fatture_locali.db`**.
Nello specifico:

1. **Fatture XML e Prezzi**:
   * I file XML e gli archivi ZIP caricati vengono elaborati e memorizzati nelle tabelle `documenti` (metadati fattura, data, fornitore, imponibile, hash univoco anti-duplicati) e `righe_documento` (prezzi unitari, quantità, codici articolo, descrizioni e attribuzione al locale di Lavis o Pergine).
2. **Utenti e Permessi**:
   * Salvati nelle tabelle `utenti` (username, salt univoco casuale, password hashata con standard crittografico PBKDF2-HMAC-SHA256), `permessi_utente` (permessi specifici per locale gestibili tramite caselle di spunta) e `sessioni` (token crittografici a 32 byte con scadenza).
3. **Registrazioni HACCP**:
   * Salvate nelle tabelle `haccp_frigoriferi`, `haccp_temperature`, `haccp_friggitrici`, `haccp_cambio_olio`, `haccp_pulizia_cappa`, `haccp_pulizie` (muri, vetri, magazzino) e `haccp_infestanti` (le 8 verifiche obbligatorie a cascata con eventuali dettagli di presenza e azioni).
4. **Etichette Alimenti & Lotti**:
   * Salvate nelle tabelle `haccp_lotti`, `haccp_lotti_contatore` (progressivo sequenziale atomico `LAV-000001` / `PER-000001`), `haccp_etichette` (storico dei singoli pezzi da 1 a $N$, lotto originale e scadenze) e `haccp_prodotti`.

> **Nota Fondamentale per il Cloud**: Tramite la variabile d'ambiente `DB_PATH`, il file di database può essere collocato in un **volume persistente** (ad esempio `/data/fatture_locali.db`), garantendo che nessun dato vada perso quando il server viene riavviato o aggiornato.

---

### 3. Servizi di Hosting Compatibili e Scelta Consigliata

Per un'applicazione basata su FastAPI e SQLite persistente, si distinguono due soluzioni ottimali:

#### Opzione A: Piattaforma Cloud Gestita (Consigliata: Railway.app o Render.com)
* **Perché è consigliata**: Non occorre configurare Linux, né gestire certificati SSL o firewall. È sufficiente collegare la cartella del progetto (o il repository GitHub) e aggiungere un disco persistente (*Persistent Volume*).
* **Funzionalità incluse**:
  * Certificato **HTTPS automatico** (Let's Encrypt).
  * Dominio pubblico gratuito (es. `gestionale-krugel.up.railway.app`) oppure collegamento del proprio dominio (es. `gestionale.krugel.it`).
  * Riavvio automatico in caso di errore o spegnimento.
* **Costo**: circa **5$ – 7$ al mese** (in base all'uso e allo spazio del volume).

#### Opzione B: Server VPS Linux Dedicato (es. Hetzner Cloud, Aruba Cloud, OVH)
* **Perché valutarla**: Offre controllo completo, massime prestazioni e costo fisso molto contenuto.
* **Configurazione**: VPS con 2 vCPU, 4 GB RAM e 40 GB SSD (es. Hetzner CX22 a circa **4€ al mese**), gestita tramite `docker compose` e il reverse proxy Caddy per HTTPS automatico.
* **Costo**: circa **4€ – 6€ al mese**.

#### Cosa NON Usare
* Evitare piattaforme *Serverless pure* (come Vercel base o Netlify standard), perché utilizzano filesystem effimeri: a ogni riavvio o rilascio di codice il file `fatture_locali.db` verrebbe cancellato.

---

### 4. Servizi a Pagamento da Attivare Prima della Pubblicazione

Prima di mettere online il sistema per i locali, prevedere:

1. **Piano Hosting Cloud** *(obbligatorio)*:
   * Abbonamento su **Railway.app** (piano *Hobby* o *Pro*, circa 5$/mese) oppure su **Render.com** (piano *Team/Starter* con disco persistente a circa 7$/mese), oppure un piccolo server VPS (**Hetzner / Aruba Cloud**, circa 4-5€/mese).
2. **Nome a Dominio Personalizzato** *(opzionale ma consigliato per facilità d'uso)*:
   * Se possiedi già il dominio del ristorante (es. `krugel.it`), creare un sottodominio come `gestionale.krugel.it` o `haccp.krugel.it` è **totalmente gratuito** e si configura in 2 minuti tramite il pannello DNS del proprio registrar.
   * Se si desidera acquistare un nuovo dominio dedicato (es. `krugelhaccp.it`), il costo medio è di circa **5€ – 10€ all'anno**.

---

### 5. Persistenza dei Dati e Strategia di Backup Automatico

#### A. Persistenza con Volumi Docker
Nel file `docker-compose.yml` è configurato il volume:
```yaml
volumes:
  - gestionale_data:/data
```
Il container del codice può essere spento, riavviato, ricostruito o aggiornato a una nuova versione del programma: il database `fatture_locali.db` rimarrà sempre intatto e protetto sul disco dell'host.

#### B. Backup Automatico a Caldo (`backup.py`)
Nel progetto è incluso lo script professionale `backup.py`:
* **Zero interruzioni**: Sfrutta l'API nativa *SQLite Online Backup*, eseguendo copie istantanee anche mentre i cuochi o il personale registrano temperature o stampano etichette, senza bloccare l'interfaccia.
* **Controllo integrità**: Verifica ogni file generato tramite `PRAGMA integrity_check`.
* **Compressione**: Comprime l'archivio in formato `.db.gz`, riducendo lo spazio occupato di oltre l'80% (da 2.3 MB a ~200-300 KB).
* **Rotazione automatica**: Conserva automaticamente gli ultimi 30 giorni di backup, eliminando quelli più vecchi.

**Come schedulare il backup automatico ogni notte alle 03:00 (su Linux / VPS):**
```bash
# Apri la tabella cron
crontab -e

# Aggiungi questa riga:
0 3 * * * docker exec fatture_locali_app python /app/backup.py >> /var/log/backup_krugel.log 2>&1
```

**Comandi utili di backup:**
* Creare un backup manuale immediato:
  ```bash
  python backup.py
  ```
* Visualizzare l'elenco dei backup presenti:
  ```bash
  python backup.py --list
  ```
* Ripristinare il database da un backup (con salvataggio automatico di sicurezza):
  ```bash
  python backup.py --restore backups/backup_20261120_155727.db.gz
  ```

---

### 6. Concorrenza Multi-Dispositivo, Password e HTTPS

1. **Uso Contemporaneo da più Dispositivi (Lavis e Pergine)**:
   * **WAL Mode**: Il database è impostato su `PRAGMA journal_mode = WAL` e `PRAGMA busy_timeout = 10000`. I lettori (chi consulta fatture o lotti) non bloccano gli scrittori (chi registra una temperatura o crea un'etichetta).
   * **Multi-Worker**: Il server Uvicorn è avviato con `--workers 2` (o più), processando in parallelo le richieste provenienti dai vari tablet e computer.
2. **Accesso e Sicurezza Password**:
   * Tutte le credenziali sono isolate nel file `.env`.
   * Le password memorizzate nel database utilizzano l'algoritmo PBKDF2-HMAC-SHA256 con 100.000 iterazioni e salt casuale.
   * Le sessioni sono basate su token crittografici sicuri a 32 byte (`secrets.token_urlsafe(32)`).
   * La disattivazione di un account dal pannello revoca istantaneamente la sessione attiva su qualsiasi dispositivo.
3. **HTTPS Obbligatorio**:
   * L'accesso dall'esterno richiede HTTPS: tutte le credenziali, i cookie e i dati delle fatture viaggiano su canale cifrato TLS 1.3.

---

### 7. Come Trasferire Online i Dati Già Inseriti

Per trasferire sul server online tutte le 13 fatture caricate, i 213 prodotti analizzati, le anagrafiche dei frigoriferi/friggitrici e lo storico HACCP già salvato sul computer locale:

1. **Localizza il database sul computer locale**:
   * Il file si trova in: `C:\Users\KRUGEL\Desktop\FATTURE LOCALI\fatture_locali.db`.
2. **Copia il file sul server online**:
   * **Se usi Railway**:
     Tramite la Railway CLI o l'interfaccia web, carica il file nel volume persistente associato a `/data/fatture_locali.db`.
     ```bash
     railway run scp ./fatture_locali.db /data/fatture_locali.db
     ```
   * **Se usi un VPS Linux**:
     Copia il file tramite `scp` o un client SFTP (come FileZilla o WinSCP):
     ```bash
     scp "C:\Users\KRUGEL\Desktop\FATTURE LOCALI\fatture_locali.db" root@IP_DEL_SERVER:/var/lib/docker/volumes/fatture_locali_data/_data/fatture_locali.db
     ```
3. **Avvia il container**:
   * Al primo avvio l'applicazione rileverà il database esistente e caricherà istantaneamente tutti i dati storici, senza sovrascriverli né azzerarli.

---

### 8. Procedura di Pubblicazione Passo-Passo

#### Metodo 1: Pubblicazione su Railway.app (Scelta Rapida - ~10 minuti)

1. Crea un account gratuito su [Railway.app](https://railway.app).
2. Crea un nuovo progetto (*New Project*) e seleziona *Deploy from GitHub repo* (oppure carica la cartella del progetto).
3. Nella scheda del servizio:
   * Vai su **Volumes** $\rightarrow$ Clicca su **Add Volume** $\rightarrow$ Imposta il punto di montaggio (*Mount Path*) su `/data`.
4. Vai su **Variables** $\rightarrow$ Inserisci le variabili d'ambiente prendendo come riferimento `.env.example`:
   * `DB_PATH` = `/data/fatture_locali.db`
   * `ADMIN_DEFAULT_PASSWORD` = *[la tua password complessa per admin]*
   * `CUCINA_DEFAULT_PASSWORD` = *[la password per l'account cucina]*
   * `ALLOWED_ORIGINS` = `*`
5. Vai su **Settings** $\rightarrow$ **Networking** $\rightarrow$ Clicca su **Generate Domain**.
   * Otterrai un link HTTPS sicuro pronto all'uso (es. `https://fatture-locali-production.up.railway.app`).
   * Puoi aggiungere il tuo dominio personalizzato cliccando su *Custom Domain*.
6. Copia il file `fatture_locali.db` nel volume `/data` (vedi sezione 7).
7. Apri il link dal browser del computer o dal tablet di Lavis e Pergine: l'app è subito operativa!

#### Metodo 2: Pubblicazione su Server VPS con Docker Compose

1. Connettiti al server VPS tramite SSH:
   ```bash
   ssh root@INDIRIZZO_IP_SERVER
   ```
2. Installa Docker e Docker Compose:
   ```bash
   curl -fsSL https://get.docker.com | sh
   ```
3. Crea la cartella del progetto e copia i file:
   ```bash
   mkdir -p /opt/fatture_locali
   cd /opt/fatture_locali
   ```
4. Configura il file `.env`:
   ```bash
   cp .env.example .env
   nano .env  # Imposta le tue password e percorsi
   ```
5. Copia il database esistente `fatture_locali.db`.
6. Avvia l'applicazione con Docker Compose:
   ```bash
   docker compose up -d --build
   ```
7. Verifica lo stato del container:
   ```bash
   docker compose ps
   docker compose logs -f
   ```
8. Configura il reverse proxy Caddy o Nginx con Certbot per il dominio HTTPS.
