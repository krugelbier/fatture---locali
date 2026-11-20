"""
Script di Backup & Ripristino per Fatture Locali & HACCP
Krügel – Lavis & Cafè L’Incontro – Pergine

Funzionalità:
- Esegue una copia coerente e a caldo del database SQLite tramite l'API nativa Online Backup
  anche mentre gli operatori sono collegati da tablet/PC.
- Verifica l'integrità del database con PRAGMA integrity_check.
- Comprime il backup con gzip (.db.gz) riducendo le dimensioni dell'80-90%.
- Gestisce la rotazione automatica (default: conserva gli ultimi 30 giorni).
- Permette il ripristino sicuro verificando l'integrità del backup prima della sovrascrittura
  e creando una copia di sicurezza del database attuale.
"""

import os
import sys
import gzip
import shutil
import sqlite3
import argparse
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(BASE_DIR, "fatture_locali.db")
DEFAULT_BACKUP_DIR = os.path.join(BASE_DIR, "backups")

DB_PATH = os.environ.get("DB_PATH", DEFAULT_DB)
BACKUP_DIR = os.environ.get("BACKUP_DIR", DEFAULT_BACKUP_DIR)
RETENTION_DAYS = int(os.environ.get("BACKUP_RETENTION_DAYS", "30"))


def verify_integrity(db_file: str) -> bool:
    """Verifica l'integrità strutturale del database SQLite"""
    try:
        conn = sqlite3.connect(db_file)
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check")
        res = cur.fetchone()
        conn.close()
        return res is not None and res[0] == "ok"
    except Exception as e:
        print(f"Errore durante il controllo di integrità: {e}")
        return False


def create_backup(db_path: str = DB_PATH, backup_dir: str = BACKUP_DIR, retention_days: int = RETENTION_DAYS) -> str:
    """Crea un backup coerente a caldo, verifica l'integrità, lo comprime e rimuove i backup obsoleti"""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database sorgente non trovato nel percorso: {db_path}")

    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_backup_file = os.path.join(backup_dir, f"backup_{timestamp}.db")
    final_gz_file = f"{temp_backup_file}.gz"

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Avvio backup di: {db_path}")

    # 1. Copia a caldo tramite SQLite Online Backup API
    source_conn = sqlite3.connect(db_path, timeout=15.0)
    dest_conn = sqlite3.connect(temp_backup_file)
    with dest_conn:
        source_conn.backup(dest_conn)
    dest_conn.close()
    source_conn.close()

    # 2. Controllo integrità della copia effettuata
    if not verify_integrity(temp_backup_file):
        if os.path.exists(temp_backup_file):
            os.remove(temp_backup_file)
        raise RuntimeError("Il backup generato non ha superato il test di integrità SQLite.")

    # 3. Compressione Gzip
    with open(temp_backup_file, 'rb') as f_in:
        with gzip.open(final_gz_file, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)

    os.remove(temp_backup_file)
    file_size_kb = os.path.getsize(final_gz_file) / 1024

    print(f"[OK] Backup completato e verificato: {os.path.basename(final_gz_file)} ({file_size_kb:.1f} KB)")

    # 4. Rotazione: rimozione backup più vecchi di RETENTION_DAYS
    cleanup_old_backups(backup_dir, retention_days)

    return final_gz_file


def cleanup_old_backups(backup_dir: str, retention_days: int) -> int:
    """Rimuove i file di backup anteriori al periodo di ritenzione specificato"""
    cutoff_date = datetime.now() - timedelta(days=retention_days)
    deleted_count = 0

    if not os.path.exists(backup_dir):
        return 0

    for fname in os.listdir(backup_dir):
        if fname.startswith("backup_") and (fname.endswith(".db.gz") or fname.endswith(".db")):
            fpath = os.path.join(backup_dir, fname)
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
            if mtime < cutoff_date:
                try:
                    os.remove(fpath)
                    deleted_count += 1
                    print(f"  [Rotazione] Rimosso backup obsoleto: {fname}")
                except Exception as e:
                    print(f"  [Avviso] Impossibile rimuovere {fname}: {e}")

    return deleted_count


def list_backups(backup_dir: str = BACKUP_DIR):
    """Elenca tutti i backup disponibili nella cartella"""
    if not os.path.exists(backup_dir):
        print(f"Cartella backup vuota o non esistente: {backup_dir}")
        return

    files = sorted([f for f in os.listdir(backup_dir) if f.startswith("backup_") and (f.endswith(".db.gz") or f.endswith(".db"))])
    if not files:
        print(f"Nessun file di backup presente in: {backup_dir}")
        return

    print(f"\nElenco backup disponibili in {backup_dir}:")
    print(f"{'Nome File':<40} {'Data Creazione':<22} {'Dimensione':<12}")
    print("-" * 76)
    for f in files:
        fpath = os.path.join(backup_dir, f)
        mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d %H:%M:%S")
        size_kb = os.path.getsize(fpath) / 1024
        print(f"{f:<40} {mtime:<22} {size_kb:>8.1f} KB")
    print("-" * 76)


def restore_backup(backup_file: str, target_db_path: str = DB_PATH):
    """Ripristina in modo sicuro il database da un archivio di backup (.db o .db.gz)"""
    if not os.path.exists(backup_file):
        raise FileNotFoundError(f"File di backup non trovato: {backup_file}")

    temp_restored_file = f"{target_db_path}.restore_temp"
    try:
        # Se compresso con Gzip, decomprime in file temporaneo
        if backup_file.endswith(".gz"):
            print(f"Decompressione di {backup_file}...")
            with gzip.open(backup_file, 'rb') as f_in:
                with open(temp_restored_file, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
        else:
            shutil.copy2(backup_file, temp_restored_file)

        # Verifica integrità del file estratto prima di toccare il DB attivo
        print("Verifica integrità del backup da ripristinare...")
        if not verify_integrity(temp_restored_file):
            raise RuntimeError("Il file di backup risulta corrotto. Ripristino interrotto per sicurezza.")

        # Copia di sicurezza del database attuale prima della sostituzione
        if os.path.exists(target_db_path):
            safety_copy = f"{target_db_path}.safety_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
            print(f"Creazione copia di salvataggio del database attivo in: {safety_copy}")
            shutil.copy2(target_db_path, safety_copy)

        # Sostituzione atomica del database attivo
        shutil.move(temp_restored_file, target_db_path)
        print(f"[OK] Database ripristinato con successo in: {target_db_path}")

        # Verifica tabelle
        conn = sqlite3.connect(target_db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        conn.close()
        print(f"[OK] Verifica tabelle ripristinate ({len(tables)} tabelle trovate).")

    finally:
        if os.path.exists(temp_restored_file):
            try:
                os.remove(temp_restored_file)
            except Exception:
                pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backup e Ripristino Fatture Locali & HACCP")
    parser.add_argument("--backup", action="store_true", help="Esegue un nuovo backup completo")
    parser.add_argument("--list", action="store_true", help="Elenca i backup disponibili")
    parser.add_argument("--restore", type=str, metavar="FILE", help="Ripristina il database da un file specificato")

    args = parser.parse_args()

    if args.list:
        list_backups()
    elif args.restore:
        restore_backup(args.restore)
    else:
        create_backup()
