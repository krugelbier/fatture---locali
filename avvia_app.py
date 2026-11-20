# Script di avvio per Fatture Locali (Krügel & Cafè L'Incontro)
import os
import sys
import webbrowser
import threading
import time
import socket
import urllib.request

# Assicura che la directory di lavoro sia la radice del progetto
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_DIR)
sys.path.insert(0, PROJECT_DIR)

PORT = 8000
URL = f"http://127.0.0.1:{PORT}"

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(('127.0.0.1', port)) == 0

def is_our_app_running() -> bool:
    try:
        req = urllib.request.Request(f"{URL}/", method="GET")
        with urllib.request.urlopen(req, timeout=1.2) as resp:
            return resp.status in (200, 401)
    except urllib.error.HTTPError as e:
        return e.code in (200, 401)
    except Exception:
        return False

def open_browser():
    time.sleep(1.2)
    print(f"\n[Fatture Locali] Apertura automatica del browser: {URL}\n")
    try:
        webbrowser.open(URL)
    except Exception as e:
        print(f"Impossibile aprire il browser automaticamente: {e}")
        print(f"Apri manualmente il browser all'indirizzo: {URL}")

if __name__ == "__main__":
    print("=" * 65)
    print("  FATTURE LOCALI - Krügel & Cafè L’Incontro")
    print("  Applicazione Web Privata per Analisi Fatture e Controllo Prezzi")
    print("=" * 65)

    # 1. Verifica se l'applicazione è già attiva in background
    if is_our_app_running():
        print(f"\nL'applicazione è GIÀ ATTIVA e in esecuzione su {URL}!")
        print("Apertura della finestra del browser in corso...")
        webbrowser.open(URL)
        print("\nPremi INVIO per chiudere questa finestra (il server rimarrà attivo).")
        try:
            input()
        except Exception:
            pass
        sys.exit(0)

    # 2. Se la porta è occupata da un altro processo, cerca una porta libera o avvisa
    target_port = PORT
    if is_port_in_use(PORT):
        print(f"\nNota: La porta {PORT} è occupata da un altro processo.")
        # Prova su porta 8001
        if not is_port_in_use(8001):
            target_port = 8001
            URL = f"http://127.0.0.1:{target_port}"
            print(f"Avvio del server sulla porta alternativa: {target_port}")

    print(f"\nAvvio del server locale in corso...")
    print(f"Interfaccia Web: {URL}")
    print("Premi Ctrl+C nel terminale per arrestare il server.")
    print("=" * 65)

    # Avvia thread per aprire automaticamente il browser
    threading.Thread(target=open_browser, daemon=True).start()

    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=target_port, reload=False)
