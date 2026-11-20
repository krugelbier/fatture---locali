# Fatture Locali • Krügel & Cafè L’Incontro

Applicazione web privata in italiano per l’analisi delle fatture elettroniche di acquisto (FatturaPA XML/P7M), con gestione multi-sede a partita IVA condivisa, controllo prezzi storici, conversioni confezioni e tracciabilità riga per riga.

---

## 🌟 Caratteristiche Principali

- **Gestione Multi-Sede a Partita IVA Condivisa**:
  - **Krügel Pub / Birreria**: Via Roma 10, Treviso
  - **Cafè L’Incontro**: Piazza dei Signori 5, Treviso
  - Entrambi i locali condividono la medesima Partita IVA. Le sedi e gli indirizzi di consegna sono liberamente riconfigurabili o espandibili.
- **Assegnazione Automatica Intelligente**:
  - **Univoca per Indirizzo/Codice**: se la fattura presenta un indirizzo o codice sede corrispondente, viene assegnata integralmente.
  - **Consegne Miste per Riga (DDT)**: se una fattura include merci per entrambi i locali con DDT separati (es. DDT 1043 per Krügel e DDT 1044 per L'Incontro), le singole righe collegate vengono assegnate automaticamente con certezza a ciascuna sede.
  - **Gestione Ambivalenze**: le fatture o le righe prive di recapito certo confluiscono nella vista dedicata **"Da assegnare"** per una rapida attribuzione manuale con 1 clic.
- **Analisi Acquisti & Controllo Prezzi (Ultimi 6 Mesi)**:
  - Raggruppamento per **Prodotto Canonico** e **Fornitore**.
  - **Quantità Fatturata** normalizzata nell'unità di misura base compatibile (`LT`, `KG`, `BT`, `PZ`).
  - **Prezzo Medio Ponderato**: calcolato al netto di IVA e al netto di tutti gli sconti di riga (`ScontoMaggiorazione` a cascata o a importo).
  - **Prezzo Minimo** e **Prezzo Massimo** riscontrati nel periodo con percentuale di oscillazione.
  - Gestione corretta delle **Note di Credito (TD04)** per resi o conguagli (storno da quantità e imponibile).
  - **Conversioni Confezioni & Alias**: associa descrizioni fornitore diverse allo stesso prodotto (es. fusto 30L -> 30 LT, cartone 6 bottiglie -> 6 BT o 4.5 LT, cartone 25 hamburger -> 25 PZ).
  - **Tracciabilità Totale**: cliccando su qualsiasi riga dell'analisi si apre il dettaglio riga per riga di tutte le fatture e DDT da cui il prezzo deriva.
- **Importazione Multipla & Archivi ZIP (Anti-Duplicati)**:
  - Caricamento simultaneo drag-and-drop di singoli file XML FatturaPA 1.2, P7M firmati digitalmente o **archivi ZIP completi** contenenti decine o centinaia di fatture (anche organizzate in sottocartelle).
  - Decompressione automatica in memoria con gestione di tutti i file XML contenuti.
  - Blocco automatico dei duplicati tramite hash crittografico e chiave composita (Fornitore + Numero Documento + Data).
- **Predisposizione TeamSystem Digital (SDI B2B)**:
  - Architettura modulare con provider di importazione astratto (`InvoiceImportProvider`).
  - Connettore `TeamSystemDigitalConnector` pronto per l'autenticazione OAuth2 Client Credentials, interrogazione endpoint di ricezione SDI e ricezione webhook push.
- **Dati Demo Inclusi**:
  - Set completo di file XML realistici (`demo_fatture/`) con fusti birra, vini DOCG, distillati, caffè, hamburger, note di credito per resi e consegne miste.
  - Pulsante **"Dati Demo"** in testata per popolare l'applicazione con 1 clic.

---

## 🚀 Come Avviare l'Applicazione

### Metodo Rapido (Windows)
Fai doppio clic sul file:
```cmd
avvia.bat
```

### Metodo da Riga di Comando (Python)
Assicurati di trovarti nella cartella del progetto ed esegui:
```powershell
python avvia_app.py
```

L'applicazione avvierà il server locale e aprirà automaticamente il browser all'indirizzo:
👉 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## 🖥️ Le Tre Viste Principali

### 1. 📊 Analisi Acquisti
- Mostra la panoramica dei prezzi medi ponderati, minimi e massimi degli ultimi sei mesi.
- Filtra per sede globale (**Tutte**, **Krügel**, **Cafè L'Incontro**), per categoria o per fornitore.
- Visualizza le quantità espresse in unità base normalizzate (Litri, Bottiglie, Kg, Pezzi) applicando i fattori di conversione delle confezioni.
- **Drill-down immediato**: cliccando su un prodotto o fornitore si apre la finestra di tracciabilità con l'elenco delle singole righe di fattura originali, data, numero fattura, riferimento DDT, sconti applicati e prezzo unitario risultante.

### 2. 📑 Fatture
- Elenco cronologico di tutte le fatture e note di credito importate.
- Badge di stato: assegnata a Krügel, assegnata a Cafè L'Incontro, mista (DDT separati), o da assegnare.
- Badge per Tipo Documento (TD01 Ordinaria, TD04 Nota di Credito, TD24 Differita).
- Apertura del drawer di dettaglio fattura con visualizzazione completa di testata, indirizzo resa rilevato, elenco DDT e tutte le righe originali.

### 3. ⚠️ Da Assegnare
- Inbox dedicata con contatore notifiche per le fatture o le singole righe di consegne parziali/senza indirizzo univoco.
- Pulsanti di assegnazione rapida con un clic:
  - `🍺 Assegna a Krügel`
  - `☕ Assegna a Cafè L’Incontro`
- Assegnazione multipla di righe tramite caselle di spunta per smistare rapidamente carichi misti.

### ⚙️ Configurazione & Sedi
- **Sedi di Consegna**: anagrafica sedi con indirizzo, CAP, comune e parole chiave per il matching automatico dei DDT.
- **Regole di Assegnazione**: regole configurabili basate su testo dell'indirizzo di resa, riferimenti DDT o causali.
- **Catalogo Prodotti & Conversioni**: gestione delle unità base, associazione di codici/descrizioni dei fornitori e configurazione dei moltiplicatori di confezione (es. Fusto 30L = 30x).
- **Integrazione TeamSystem Digital**: pannello per inserire Client ID, Client Secret e Codice Ditta con test di connessione API SDI.

---

## 📁 Struttura del Progetto

```
FATTURE LOCALI/
├── app/
│   ├── database.py                 # Schema SQLite, inizializzazione sedi e prodotti
│   ├── main.py                     # Entrypoint FastAPI e configurazione routes
│   ├── routes/
│   │   ├── analytics.py            # API per analisi acquisti e drilldown tracciabilità
│   │   ├── invoices.py             # API per lista, dettaglio e upload fatture XML
│   │   ├── lines.py                # API per assegnazione e mappatura singole righe
│   │   ├── unassigned.py           # API per vista 'Da assegnare' e azioni rapide
│   │   ├── settings.py             # API configurazione sedi, regole e TeamSystem
│   │   └── demo.py                 # API per caricamento e reset dati di prova
│   ├── services/
│   │   ├── xml_parser.py           # Parser FatturaPA 1.2 XML/P7M con gestione sconti
│   │   ├── assignment_engine.py    # Logica di assegnazione univoca o per riga/DDT
│   │   ├── analytics_service.py    # Calcolo prezzi ponderati, min/max e conversioni
│   │   ├── demo_service.py         # Generatore di fatture XML realistiche
│   │   └── importer/
│   │       ├── base.py             # Interfaccia astratta provider importazione
│   │       ├── xml_importer.py     # Importatore XML/P7M con controllo duplicati
│   │       └── teamsystem_digital.py # Connettore API TeamSystem Digital SDI
│   └── static/
│       ├── index.html              # Interfaccia utente web responsive in italiano
│       └── js/
│           └── app.js              # Logica frontend interattiva (filtri, drilldown)
├── demo_fatture/                   # File XML di prova (Partesa, Hausbrandt, Metro, DAC, NC)
├── avvia_app.py                    # Script Python per avviare il server e aprire il browser
├── avvia.bat                       # Script batch Windows per avvio con doppio clic
├── test_app.py                     # Suite di test automatizzati
└── README.md                       # Questa documentazione
```

---

## 🧪 Dati Demo per Provare l'App

La cartella `demo_fatture/` contiene 7 documenti realistici pronti per essere importati o testati:
1. `Fattura_01_Partesa_Krugel_Birre.xml`: birre in fusto (Heineken, Ichnusa, Paulaner) con sconti di riga, consegnata a Krügel (Via Roma 10).
2. `Fattura_02_Hausbrandt_Incontro_Caffe.xml`: fornitura caffè in grani e tè bar, consegnata a Cafè L'Incontro (Piazza dei Signori 5).
3. `Fattura_03_Beverage_Mista_Entrambe_Sedi.xml`: fattura mista differita (TD24) con **DDT 1043 a Krügel** (Gin Mare e Rum Zacapa) e **DDT 1044 a Cafè L'Incontro** (Prosecco DOCG e Aperol) con assegnazione automatica per riga.
4. `Fattura_04_Dac_Food_Krugel.xml`: forniture cucina Krügel (Hamburger Black Angus, patate dipper, bun brioche).
5. `NotaCredito_05_Partesa_Reso_Fusti.xml`: nota di credito (TD04) con storno di fusti resi.
6. `Fattura_06_Metro_Da_Assegnare.xml`: fattura senza indirizzo di consegna univoco, ideale per testare la vista **"Da assegnare"**.
7. `Fattura_07_Partesa_Krugel_Prezzi_Precedenti.xml`: fattura di 4 mesi fa con prezzi leggermente differenti per mostrare il calcolo del minimo, massimo e medio ponderato negli ultimi sei mesi.
