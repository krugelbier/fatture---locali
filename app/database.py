# Database and core models for Fatture Locali & HACCP (Krügel – Lavis & Cafè L’Incontro – Pergine)
import sqlite3
import os
import json
from datetime import datetime, timedelta
from app.services.auth_service import hash_password

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fatture_locali.db"))

ALL_PERMISSIONS = [
    # Fatture e prezzi
    ("fatture.view", "Fatture e prezzi", "Consultare fatture e analisi prezzi"),
    ("fatture.import", "Fatture e prezzi", "Importare fatture"),
    ("fatture.assign", "Fatture e prezzi", "Assegnarle o correggerne l'assegnazione"),
    ("fatture.products", "Fatture e prezzi", "Gestire le associazioni tra prodotti"),
    # HACCP - Etichette
    ("haccp.labels.view", "HACCP – Etichette", "Consultare lo storico"),
    ("haccp.labels.create", "HACCP – Etichette", "Creare etichette e lotti"),
    ("haccp.labels.print", "HACCP – Etichette", "Stampare e ristampare"),
    # HACCP - Temperature
    ("haccp.temp.view", "HACCP – Temperature", "Consultare lo storico"),
    ("haccp.temp.record", "HACCP – Temperature", "Registrare i controlli"),
    ("haccp.temp.manage", "HACCP – Temperature", "Gestire e rinominare i frigoriferi"),
    # HACCP - Cambio olio
    ("haccp.oil.view", "HACCP – Cambio olio", "Consultare lo storico"),
    ("haccp.oil.record", "HACCP – Cambio olio", "Registrare i cambi"),
    ("haccp.oil.manage", "HACCP – Cambio olio", "Configurare le friggitrici"),
    # HACCP - Pulizia cappa
    ("haccp.hood.view", "HACCP – Pulizia cappa", "Consultare lo storico"),
    ("haccp.hood.record", "HACCP – Pulizia cappa", "Registrare la pulizia"),
    # HACCP - Pulizia muri
    ("haccp.cleaning.walls.view", "HACCP – Pulizia muri", "Consultare lo storico"),
    ("haccp.cleaning.walls.record", "HACCP – Pulizia muri", "Registrare la pulizia"),
    # HACCP - Pulizia vetri
    ("haccp.cleaning.windows.view", "HACCP – Pulizia vetri", "Consultare lo storico"),
    ("haccp.cleaning.windows.record", "HACCP – Pulizia vetri", "Registrare la pulizia"),
    # HACCP - Pulizia magazzino
    ("haccp.cleaning.warehouse.view", "HACCP – Pulizia magazzino", "Consultare lo storico"),
    ("haccp.cleaning.warehouse.record", "HACCP – Pulizia magazzino", "Registrare la pulizia"),
    # HACCP - Monitoraggio infestanti
    ("haccp.pests.view", "HACCP – Monitoraggio infestanti", "Consultare lo storico"),
    ("haccp.pests.record", "HACCP – Monitoraggio infestanti", "Registrare la verifica"),
]

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 10000;")
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True) if os.path.dirname(DB_PATH) else None
    conn = get_db()
    conn.execute("PRAGMA journal_mode = WAL;")
    cursor = conn.cursor()

    # Sedi di consegna (Krügel – Lavis, Cafè L’Incontro – Pergine)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sedi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL UNIQUE,
        codice TEXT NOT NULL UNIQUE,
        indirizzo TEXT NOT NULL,
        cap TEXT,
        comune TEXT NOT NULL,
        provincia TEXT,
        parole_chiave TEXT,
        colore_badge TEXT DEFAULT '#3b82f6',
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Regole di assegnazione automatica personalizzabili
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS regole_assegnazione (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sede_id INTEGER NOT NULL,
        tipo_campo TEXT NOT NULL,
        operatore TEXT NOT NULL DEFAULT 'CONTIENE',
        valore_match TEXT NOT NULL,
        priorita INTEGER DEFAULT 10,
        descrizione TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sede_id) REFERENCES sedi (id) ON DELETE CASCADE
    );
    """)

    # Fatture importate
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS documenti (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        file_hash TEXT UNIQUE NOT NULL,
        sdi_identificativo TEXT,
        tipo_documento TEXT NOT NULL,
        numero_documento TEXT NOT NULL,
        data_documento DATE NOT NULL,
        cedente_denominazione TEXT NOT NULL,
        cedente_piva TEXT,
        cedente_codice_fiscale TEXT,
        cedente_indirizzo TEXT,
        cedente_comune TEXT,
        cessionario_piva TEXT,
        cessionario_denominazione TEXT,
        importo_totale REAL NOT NULL,
        imponibile_totale REAL,
        iva_totale REAL,
        divisa TEXT DEFAULT 'EUR',
        sede_id INTEGER,
        stato_assegnazione TEXT DEFAULT 'DA_ASSEGNARE',
        metodo_assegnazione TEXT,
        ddt_elenco_json TEXT,
        indirizzo_resa_estratto TEXT,
        raw_xml TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sede_id) REFERENCES sedi (id) ON DELETE SET NULL
    );
    """)

    # Righe di fattura
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS righe_fattura (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        documento_id INTEGER NOT NULL,
        numero_linea INTEGER NOT NULL,
        codice_articolo TEXT,
        descrizione TEXT NOT NULL,
        quantita REAL NOT NULL,
        unita_misura TEXT,
        prezzo_unitario_lordo REAL NOT NULL,
        sconto_percentuale REAL DEFAULT 0,
        sconto_importo REAL DEFAULT 0,
        prezzo_unitario_netto REAL NOT NULL,
        prezzo_totale_netto REAL NOT NULL,
        aliquota_iva REAL DEFAULT 0,
        riferimento_ddt_numero TEXT,
        riferimento_ddt_data DATE,
        sede_id INTEGER,
        metodo_assegnazione TEXT DEFAULT 'DA_ASSEGNARE',
        prodotto_id INTEGER,
        note TEXT,
        FOREIGN KEY (documento_id) REFERENCES documenti (id) ON DELETE CASCADE,
        FOREIGN KEY (sede_id) REFERENCES sedi (id) ON DELETE SET NULL,
        FOREIGN KEY (prodotto_id) REFERENCES prodotti (id) ON DELETE SET NULL
    );
    """)

    # Prodotti canonici
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS prodotti (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome_canonico TEXT NOT NULL UNIQUE,
        categoria TEXT NOT NULL,
        unita_base TEXT NOT NULL,
        descrizione TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Mappature descrizioni/codici fornitori
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS mappature_prodotto (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prodotto_id INTEGER NOT NULL,
        fornitore_piva TEXT,
        fornitore_denominazione TEXT,
        pattern_testo TEXT NOT NULL,
        tipo_match TEXT DEFAULT 'CONTIENE',
        fattore_conversione REAL NOT NULL DEFAULT 1.0,
        unita_confezione TEXT,
        note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (prodotto_id) REFERENCES prodotti (id) ON DELETE CASCADE
    );
    """)

    # Configurazione TeamSystem Digital
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS teamsystem_config (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        is_enabled INTEGER DEFAULT 0,
        environment TEXT DEFAULT 'sandbox',
        client_id TEXT DEFAULT '',
        client_secret TEXT DEFAULT '',
        company_id TEXT DEFAULT '',
        last_sync_at TIMESTAMP,
        last_sync_status TEXT,
        last_sync_message TEXT,
        auto_sync_interval_hours INTEGER DEFAULT 24,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # ========================================================
    # TABELLE ACCOUNT & PERMESSI
    # ========================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS utenti (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        nome_completo TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessioni (
        token TEXT PRIMARY KEY,
        utente_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL,
        FOREIGN KEY (utente_id) REFERENCES utenti (id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS permessi_utente (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        utente_id INTEGER NOT NULL,
        sede_id INTEGER NOT NULL,
        permesso TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(utente_id, sede_id, permesso),
        FOREIGN KEY (utente_id) REFERENCES utenti (id) ON DELETE CASCADE,
        FOREIGN KEY (sede_id) REFERENCES sedi (id) ON DELETE CASCADE
    );
    """)

    # ========================================================
    # TABELLE MODULO HACCP
    # ========================================================
    # 1. Configurazione Prodotti per Etichette Alimenti (durata personalizzata per sede)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS haccp_prodotti_etichette (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sede_id INTEGER NOT NULL,
        nome_prodotto TEXT NOT NULL,
        durata_ore INTEGER NOT NULL DEFAULT 48, -- default 48 ore secondo piano HACCP
        categoria TEXT DEFAULT 'Generale',
        note TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sede_id) REFERENCES sedi (id) ON DELETE CASCADE
    );
    """)

    # 2. Storico Etichette Alimenti Stampate
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS haccp_etichette (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sede_id INTEGER NOT NULL,
        prodotto TEXT NOT NULL,
        preparato_da TEXT NOT NULL,
        data_preparazione TEXT NOT NULL, -- YYYY-MM-DD HH:MM
        data_scadenza TEXT NOT NULL, -- YYYY-MM-DD HH:MM
        durata_ore INTEGER NOT NULL DEFAULT 48,
        larghezza_mm INTEGER DEFAULT 60,
        altezza_mm INTEGER DEFAULT 40,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sede_id) REFERENCES sedi (id) ON DELETE CASCADE
    );
    """)

    # 3. Anagrafica Frigoriferi / Celle
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS haccp_frigoriferi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sede_id INTEGER NOT NULL,
        nome TEXT NOT NULL,
        temperatura_min REAL DEFAULT 0.0,
        temperatura_max REAL DEFAULT 4.0,
        is_active INTEGER DEFAULT 1,
        ordine INTEGER DEFAULT 10,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sede_id) REFERENCES sedi (id) ON DELETE CASCADE
    );
    """)

    # 4. Registrazioni Temperature Frigoriferi
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS haccp_temperature (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sede_id INTEGER NOT NULL,
        frigorifero_id INTEGER NOT NULL,
        data_controllo DATE NOT NULL,
        ora_controllo TIME NOT NULL,
        temperatura REAL NOT NULL,
        operatore TEXT NOT NULL,
        esito TEXT NOT NULL, -- 'CONFORME' o 'NON_CONFORME'
        azione_correttiva TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sede_id) REFERENCES sedi (id) ON DELETE CASCADE,
        FOREIGN KEY (frigorifero_id) REFERENCES haccp_frigoriferi (id) ON DELETE CASCADE
    );
    """)

    # 5. Anagrafica Friggitrici
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS haccp_friggitrici (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sede_id INTEGER NOT NULL,
        nome TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sede_id) REFERENCES sedi (id) ON DELETE CASCADE
    );
    """)

    # 6. Registrazioni Cambio Olio Friggitrici
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS haccp_cambio_olio (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sede_id INTEGER NOT NULL,
        friggitrice_id INTEGER NOT NULL,
        data_cambio DATE NOT NULL,
        ora_cambio TIME NOT NULL,
        operatore TEXT NOT NULL,
        note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sede_id) REFERENCES sedi (id) ON DELETE CASCADE,
        FOREIGN KEY (friggitrice_id) REFERENCES haccp_friggitrici (id) ON DELETE CASCADE
    );
    """)

    # 7. Registrazioni Pulizia Settimanale Cappa
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS haccp_pulizia_cappa (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sede_id INTEGER NOT NULL,
        anno INTEGER NOT NULL,
        settimana_numero INTEGER NOT NULL, -- numero settimana ISO (1-53)
        data_inizio_settimana DATE NOT NULL,
        data_fine_settimana DATE NOT NULL,
        data_pulizia DATE NOT NULL,
        ora_pulizia TIME NOT NULL,
        operatore TEXT NOT NULL,
        note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sede_id) REFERENCES sedi (id) ON DELETE CASCADE
    );
    """)

    # 8. Lotti Alimenti Preparati (condivisi per preparazione e pezzi)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS haccp_lotti (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sede_id INTEGER NOT NULL,
        lotto_interno TEXT NOT NULL UNIQUE,
        lotto_originale TEXT NOT NULL,
        prodotto TEXT NOT NULL,
        prodotto_id INTEGER,
        preparato_da TEXT NOT NULL,
        data_preparazione TEXT NOT NULL,
        data_scadenza TEXT NOT NULL,
        durata_ore INTEGER NOT NULL DEFAULT 48,
        numero_pezzi INTEGER NOT NULL DEFAULT 1,
        larghezza_mm INTEGER DEFAULT 60,
        altezza_mm INTEGER DEFAULT 40,
        idempotency_key TEXT UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sede_id) REFERENCES sedi (id) ON DELETE CASCADE
    );
    """)

    # 9. Contatore Sequenziale Univoco Lotti per Sede (LAV-000001, PER-000001)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS haccp_lotti_contatore (
        sede_id INTEGER PRIMARY KEY,
        ultimo_progressivo INTEGER NOT NULL DEFAULT 0,
        prefisso TEXT NOT NULL,
        FOREIGN KEY (sede_id) REFERENCES sedi (id) ON DELETE CASCADE
    );
    """)

    # 10. Registri Pulizie Generali (Muri - mensile, Vetri - mensile, Magazzino - settimanale)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS haccp_pulizie (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sede_id INTEGER NOT NULL,
        tipo_pulizia TEXT NOT NULL, -- 'muri', 'vetri', 'magazzino'
        data_esecuzione DATE NOT NULL,
        ora_esecuzione TIME NOT NULL,
        operatore TEXT NOT NULL,
        note TEXT,
        prossima_scadenza DATE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sede_id) REFERENCES sedi (id) ON DELETE CASCADE
    );
    """)

    # 11. Monitoraggio Infestanti (Questionario guidato a cascata 8 voci)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS haccp_infestanti (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sede_id INTEGER NOT NULL,
        data_controllo DATE NOT NULL,
        ora_controllo TIME NOT NULL,
        operatore TEXT NOT NULL,
        has_presenze INTEGER NOT NULL DEFAULT 0,
        risposte_json TEXT NOT NULL, -- JSON con le 8 voci e dettagli
        note_generali TEXT,
        prossima_scadenza DATE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sede_id) REFERENCES sedi (id) ON DELETE CASCADE
    );
    """)

    # Migrazioni dinamiche colonne haccp_etichette
    cursor.execute("PRAGMA table_info(haccp_etichette)")
    cols_etichette = [r["name"] for r in cursor.fetchall()]
    if "lotto_originale" not in cols_etichette:
        cursor.execute("ALTER TABLE haccp_etichette ADD COLUMN lotto_originale TEXT")
    if "lotto_interno" not in cols_etichette:
        cursor.execute("ALTER TABLE haccp_etichette ADD COLUMN lotto_interno TEXT")
    if "numero_pezzi" not in cols_etichette:
        cursor.execute("ALTER TABLE haccp_etichette ADD COLUMN numero_pezzi INTEGER DEFAULT 1")
    if "numero_pezzo" not in cols_etichette:
        cursor.execute("ALTER TABLE haccp_etichette ADD COLUMN numero_pezzo INTEGER DEFAULT 1")
    if "lotto_id" not in cols_etichette:
        cursor.execute("ALTER TABLE haccp_etichette ADD COLUMN lotto_id INTEGER")

    conn.commit()

    # Inizializzazioni e seed
    seed_sedi(cursor)
    seed_default_products(cursor)
    seed_default_teamsystem(cursor)
    seed_default_users(cursor)
    seed_default_haccp(cursor)

    conn.commit()
    conn.close()

def seed_sedi(cursor):
    cursor.execute("SELECT COUNT(*) as cnt FROM sedi")
    cnt = cursor.fetchone()["cnt"]
    if cnt == 0:
        cursor.execute("""
        INSERT INTO sedi (nome, codice, indirizzo, cap, comune, provincia, parole_chiave, colore_badge)
        VALUES 
        ('Krügel – Lavis', 'KRUGEL', 'Via Nazionale', '38015', 'Lavis', 'TN', 'krugel,krügel,lavis,via nazionale,ristorante krugel,pizzeria krugel,birreria krugel,38015', '#d97706'),
        ('Cafè L’Incontro – Pergine', 'INCONTRO', 'Via Tamarisi 2', '38057', 'Pergine Valsugana', 'TN', 'incontro,cafè incontro,cafe incontro,tamarisi,via tamarisi,pergine,pergine valsugana,38057', '#059669')
        """)

        cursor.execute("""
        INSERT INTO regole_assegnazione (sede_id, tipo_campo, operatore, valore_match, priorita, descrizione)
        VALUES 
        (1, 'INDIRIZZO_RESA', 'CONTIENE', 'Lavis', 1, 'Comune Lavis (Krügel)'),
        (1, 'INDIRIZZO_RESA', 'CONTIENE', 'Via Nazionale', 2, 'Via Nazionale Lavis (Krügel)'),
        (1, 'NOTE_DDT', 'CONTIENE', 'KRUGEL', 3, 'Riferimento Krügel nel DDT'),
        (2, 'INDIRIZZO_RESA', 'CONTIENE', 'Pergine', 1, 'Comune Pergine Valsugana (Cafè Incontro)'),
        (2, 'INDIRIZZO_RESA', 'CONTIENE', 'Tamarisi', 2, 'Via Tamarisi Pergine (Cafè Incontro)'),
        (2, 'NOTE_DDT', 'CONTIENE', 'INCONTRO', 3, 'Riferimento Incontro nel DDT')
        """)
    else:
        # Assicura che i nomi riflettano esattamente la dicitura richiesta
        cursor.execute("UPDATE sedi SET nome = 'Krügel – Lavis' WHERE id = 1 OR codice = 'KRUGEL'")
        cursor.execute("UPDATE sedi SET nome = 'Cafè L’Incontro – Pergine' WHERE id = 2 OR codice = 'INCONTRO'")

def seed_default_products(cursor):
    cursor.execute("SELECT COUNT(*) as cnt FROM prodotti")
    if cursor.fetchone()["cnt"] == 0:
        prodotti = [
            ("Heineken Birra Fusto", "Birre & Fusti", "LT", "Birra chiara lager Heineken"),
            ("Ichnusa Non Filtrata Fusto", "Birre & Fusti", "LT", "Birra Ichnusa bionda non filtrata"),
            ("Paulaner Salvator Fusto", "Birre & Fusti", "LT", "Birra doppio malto Paulaner Salvator"),
            ("Corona Extra Bottiglia", "Birre & Fusti", "BT", "Birra Corona 33cl"),
            ("Prosecco Valdobbiadene Superiore DOCG", "Vini & Bollicine", "BT", "Spumante prosecco millesimato"),
            ("Franciacorta Brut DOCG", "Vini & Bollicine", "BT", "Metodo classico Franciacorta"),
            ("Ripasso della Valpolicella DOC", "Vini & Bollicine", "BT", "Vino rosso veneto"),
            ("Gin Mare 70cl", "Spirits & Liquori", "BT", "Gin mediterraneo"),
            ("Aperol 1L", "Spirits & Liquori", "BT", "Aperitivo Aperol"),
            ("Campari Bitter 1L", "Spirits & Liquori", "BT", "Bitter Campari"),
            ("Rum Zacapa 23 70cl", "Spirits & Liquori", "BT", "Rum invecchiato Zacapa Centenario"),
            ("Caffè in Grani Gourmet 100% Arabica", "Caffè & Bar", "KG", "Miscela caffè espresso premium"),
            ("Latte Intero Fresco Alta Qualità", "Caffè & Bar", "LT", "Latte fresco bar"),
            ("Brioche / Croissant Surgelati", "Caffè & Bar", "PZ", "Croissant burro surgelati"),
            ("Hamburger Black Angus 200g", "Food & Cucina", "PZ", "Polpetta hamburger gourmet"),
            ("Patate Fritte Da Frittura", "Food & Cucina", "KG", "Patate prefritte surgelate"),
            ("Pane Hamburger Brioche Bun", "Food & Cucina", "PZ", "Panini per hamburger")
        ]
        for nome, cat, um, desc in prodotti:
            cursor.execute("INSERT INTO prodotti (nome_canonico, categoria, unita_base, descrizione) VALUES (?, ?, ?, ?)",
                           (nome, cat, um, desc))

def seed_default_teamsystem(cursor):
    cursor.execute("SELECT COUNT(*) as cnt FROM teamsystem_config WHERE id = 1")
    if cursor.fetchone()["cnt"] == 0:
        env = os.environ.get("TEAMSYSTEM_ENVIRONMENT", "sandbox")
        cid = os.environ.get("TEAMSYSTEM_CLIENT_ID", "")
        csec = os.environ.get("TEAMSYSTEM_CLIENT_SECRET", "")
        comp_id = os.environ.get("TEAMSYSTEM_COMPANY_ID", "")
        is_en = 1 if (cid and csec) else 0
        cursor.execute("""
        INSERT INTO teamsystem_config (id, is_enabled, environment, client_id, client_secret, company_id, last_sync_status, last_sync_message)
        VALUES (1, ?, ?, ?, ?, ?, 'READY', 'Configurazione API TeamSystem Digital')
        """, (is_en, env, cid, csec, comp_id))

def seed_default_users(cursor):
    # Utente Amministratore (admin / admin o da env ADMIN_DEFAULT_PASSWORD)
    cursor.execute("SELECT id FROM utenti WHERE username = 'admin'")
    admin_row = cursor.fetchone()
    if not admin_row:
        admin_pwd = os.environ.get("ADMIN_DEFAULT_PASSWORD", "admin")
        pw_hash, salt = hash_password(admin_pwd)
        cursor.execute("""
        INSERT INTO utenti (username, password_hash, salt, nome_completo, is_admin, is_active)
        VALUES ('admin', ?, ?, 'Amministratore di Sistema', 1, 1)
        """, (pw_hash, salt))
        admin_id = cursor.lastrowid
    else:
        admin_id = admin_row["id"]

    # Assegna tutti i permessi ad admin per entrambe le sedi
    for sede_id in [1, 2]:
        for perm_code, _, _ in ALL_PERMISSIONS:
            cursor.execute("""
            INSERT OR IGNORE INTO permessi_utente (utente_id, sede_id, permesso)
            VALUES (?, ?, ?)
            """, (admin_id, sede_id, perm_code))

    # Utente Cucina Lavis (cucina.lavis / cucina o da env CUCINA_DEFAULT_PASSWORD)
    # Abilitato ESCLUSIVAMENTE all'HACCP di Krügel - Lavis (Sede 1)
    cursor.execute("SELECT id FROM utenti WHERE username = 'cucina.lavis'")
    cucina_row = cursor.fetchone()
    if not cucina_row:
        cucina_pwd = os.environ.get("CUCINA_DEFAULT_PASSWORD", "cucina")
        pw_hash, salt = hash_password(cucina_pwd)
        cursor.execute("""
        INSERT INTO utenti (username, password_hash, salt, nome_completo, is_admin, is_active)
        VALUES ('cucina.lavis', ?, ?, 'Cucina Krügel – Lavis', 0, 1)
        """, (pw_hash, salt))
        cucina_id = cursor.lastrowid
    else:
        cucina_id = cucina_row["id"]

    # Permessi HACCP SOLO per Sede 1 (Krügel - Lavis)
    haccp_perms = [
        "haccp.labels.view", "haccp.labels.create", "haccp.labels.print",
        "haccp.temp.view", "haccp.temp.record", "haccp.temp.manage",
        "haccp.oil.view", "haccp.oil.record", "haccp.oil.manage",
        "haccp.hood.view", "haccp.hood.record",
        "haccp.cleaning.walls.view", "haccp.cleaning.walls.record",
        "haccp.cleaning.windows.view", "haccp.cleaning.windows.record",
        "haccp.cleaning.warehouse.view", "haccp.cleaning.warehouse.record",
        "haccp.pests.view", "haccp.pests.record"
    ]
    for p in haccp_perms:
        cursor.execute("""
        INSERT OR IGNORE INTO permessi_utente (utente_id, sede_id, permesso)
        VALUES (?, 1, ?)
        """, (cucina_id, p))

def seed_default_haccp(cursor):
    # Inizializza contatori lotti per Sede 1 e Sede 2 se assenti
    cursor.execute("INSERT OR IGNORE INTO haccp_lotti_contatore (sede_id, ultimo_progressivo, prefisso) VALUES (1, 0, 'LAV')")
    cursor.execute("INSERT OR IGNORE INTO haccp_lotti_contatore (sede_id, ultimo_progressivo, prefisso) VALUES (2, 0, 'PER')")

    # Inizializza Frigoriferi di default per entrambe le sedi se assenti
    for sede_id in [1, 2]:
        cursor.execute("SELECT COUNT(*) as cnt FROM haccp_frigoriferi WHERE sede_id = ?", (sede_id,))
        if cursor.fetchone()["cnt"] == 0:
            frigos = [
                ("Frigo 1 - Carni e Cucina", 0.0, 4.0, 1),
                ("Frigo 2 - Latticini e Formaggi", 0.0, 4.0, 2),
                ("Frigo 3 - Verdure e Gastronomia", 2.0, 6.0, 3),
                ("Frigo 4 - Bar e Bevande", 2.0, 8.0, 4),
                ("Cella Surgelati / Freezer", -24.0, -18.0, 5)
            ]
            for nome, tmin, tmax, ordn in frigos:
                cursor.execute("""
                INSERT INTO haccp_frigoriferi (sede_id, nome, temperatura_min, temperatura_max, ordine)
                VALUES (?, ?, ?, ?, ?)
                """, (sede_id, nome, tmin, tmax, ordn))

    # Inizializza Friggitrice 1 e Friggitrice 2 per ciascun locale se assenti
    for sede_id in [1, 2]:
        cursor.execute("SELECT COUNT(*) as cnt FROM haccp_friggitrici WHERE sede_id = ?", (sede_id,))
        if cursor.fetchone()["cnt"] == 0:
            cursor.execute("INSERT INTO haccp_friggitrici (sede_id, nome) VALUES (?, 'Friggitrice 1')", (sede_id,))
            cursor.execute("INSERT INTO haccp_friggitrici (sede_id, nome) VALUES (?, 'Friggitrice 2')", (sede_id,))

    # Inizializza Prodotti di preparazione etichette (con 48 ore preconfigurate)
    for sede_id in [1, 2]:
        cursor.execute("SELECT COUNT(*) as cnt FROM haccp_prodotti_etichette WHERE sede_id = ?", (sede_id,))
        if cursor.fetchone()["cnt"] == 0:
            prod_etichette = [
                ("Sugo al Pomodoro Fresco", 48, "Primi piatti"),
                ("Ragù di Carne Cotto", 48, "Carni e condimenti"),
                ("Impasto Pizza / Palle Lievitate", 48, "Pizzeria"),
                ("Verdure Cotte Grigliate", 48, "Contorni"),
                ("Carne Cotta Porzionata", 48, "Secondi piatti"),
                ("Dolci Fatti in Casa (Tiramisù)", 48, "Pasticceria"),
                ("Salumi Affettati Sottovuoto", 72, "Salumi e formaggi"),
                ("Brodo di Carne Fresco", 24, "Cucina base")
            ]
            for nome, durata, cat in prod_etichette:
                cursor.execute("""
                INSERT INTO haccp_prodotti_etichette (sede_id, nome_prodotto, durata_ore, categoria)
                VALUES (?, ?, ?, ?)
                """, (sede_id, nome, durata, cat))
