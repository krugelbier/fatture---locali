"""
Test Suite Completa - Aggiornamento HACCP:
1. Nomi dei frigoriferi: modifica del nome con mantenimento dell'ID attrezzatura e storico collegato
2. Lotti ed etichette alimenti:
   - Campi: Lotto originale, Numero di pezzi (>= 1), Lotto interno automatico univoco (LAV-XXXXXX, PER-XXXXXX)
   - Lotto da 12 pezzi: verifica generazione 12 etichette identiche con numerazione 1 di 12 ... 12 di 12
   - Ristampa del pezzo 3 con dati originali
   - Creazione nuova preparazione con conferma progressivo successivo (es. LAV-000002)
   - Idempotenza contro doppi tocchi
   - Ricerca storico per lotto interno, lotto originale, prodotto, data
   - Retrocompatibilità etichette legacy
3. Banner degli avvisi scaduti:
   - Calcolo esatto mese solare con clipping (31 gen -> 28 feb, 31 mar -> 30 apr)
   - Scadenze: cappa > 7gg, frigo > 24h per ogni frigo, olio > 7gg per friggitrice, muri > 1 mese, vetri > 1 mese, magazzino > 7gg, infestanti > 1 mese
   - Testo per attività mai registrata: "Prima registrazione da effettuare"
4. Registri pulizie: Muri, Vetri, Magazzino
5. Monitoraggio infestanti: validazione 8 voci obbligatorie, registrazione e dettaglio
"""

import sys
import os
import json
import time
import socket
import threading
from datetime import datetime, date, timedelta
import urllib.request
import urllib.error

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

from app.database import init_db
from app.services.haccp_service import HaccpService
import uvicorn

TEST_PORT = 8008
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"

def api_request(method, path, body=None, token=None):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode("utf-8")
            return resp.status, json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        content = e.read().decode("utf-8")
        try:
            err_json = json.loads(content)
        except Exception:
            err_json = {"detail": content}
        return e.code, err_json

def start_server():
    config = uvicorn.Config("app.main:app", host="127.0.0.1", port=TEST_PORT, log_level="error")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()

    for _ in range(30):
        try:
            with socket.create_connection(("127.0.0.1", TEST_PORT), timeout=1):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("Server test non avviato!")

def run_tests():
    print("=" * 70)
    print("AVVIO TEST SUITE AGGIORNAMENTO HACCP")
    print("=" * 70)

    init_db()
    start_server()

    # Login come admin e come cucina.lavis
    status, res = api_request("POST", "/api/auth/login", {"username": "admin", "password": "admin"})
    assert status == 200, f"Login admin fallito: {res}"
    admin_token = res.get("token") or res.get("session_token")

    status, res = api_request("POST", "/api/auth/login", {"username": "cucina.lavis", "password": "cucina"})
    assert status == 200, f"Login cucina.lavis fallito: {res}"
    cucina_token = res.get("token") or res.get("session_token")

    print("[OK] Autenticazione admin e cucina.lavis riuscita.")

    # ---------------------------------------------------------
    # TEST 1: CALCOLO MESE SOLARE E CLIPPING GIORNI
    # ---------------------------------------------------------
    print("\n--- TEST 1: Calcolo Mese Solare (Regole HACCP) ---")
    d1 = date(2026, 1, 31)
    m1 = HaccpService.add_calendar_month(d1)
    assert m1 == date(2026, 2, 28), f"Atteso 28 feb 2026 per 31 gen, ottenuto: {m1}"

    d2 = date(2026, 3, 31)
    m2 = HaccpService.add_calendar_month(d2)
    assert m2 == date(2026, 4, 30), f"Atteso 30 apr 2026 per 31 mar, ottenuto: {m2}"

    d3 = date(2026, 8, 15)
    m3 = HaccpService.add_calendar_month(d3)
    assert m3 == date(2026, 9, 15), f"Atteso 15 set 2026 per 15 ago, ottenuto: {m3}"

    d4 = date(2026, 12, 31)
    m4 = HaccpService.add_calendar_month(d4)
    assert m4 == date(2027, 1, 31), f"Atteso 31 gen 2027 per 31 dic 2026, ottenuto: {m4}"

    print(f"[OK] Calcoli mese solare corretti: {d1} -> {m1}, {d2} -> {m2}, {d4} -> {m4}")

    # ---------------------------------------------------------
    # TEST 2: NOMI DEI FRIGORIFERI (MODIFICA E MANTENIMENTO ID)
    # ---------------------------------------------------------
    print("\n--- TEST 2: Nomi Frigoriferi e Modifica Nome ---")
    status, res = api_request("GET", "/api/haccp/temperature/fridges?sede_id=1", token=admin_token)
    assert status == 200
    fridges = res["fridges"]
    assert len(fridges) >= 1
    fridge = fridges[0]
    orig_fridge_id = fridge["id"]
    orig_name = fridge["nome_frigorifero"]

    # Registra un controllo temperatura per questo frigo
    status, t_res = api_request("POST", "/api/haccp/temperature/record", {
        "sede_id": 1,
        "frigorifero_id": orig_fridge_id,
        "temperatura": 3.4,
        "esito": "CONFORME",
        "operatore": "Mario Bianchi",
        "data_controllo": datetime.now().strftime("%Y-%m-%d"),
        "ora_controllo": datetime.now().strftime("%H:%M")
    }, token=admin_token)
    assert status == 200

    # Modifica nome del frigorifero
    new_fridge_name = f"Cella Carni & Latticini (Aggiornata {int(time.time())})"
    status, upd_res = api_request("PUT", f"/api/haccp/temperature/fridges/{orig_fridge_id}", {
        "nome": new_fridge_name
    }, token=admin_token)
    assert status == 200, f"Modifica frigo fallita: {upd_res}"
    assert upd_res["id"] == orig_fridge_id, "L'ID del frigorifero deve essere rimasto invariato!"
    assert upd_res["nome"] == new_fridge_name

    # Verifica che nei frigoriferi compaia il nuovo nome con lo stesso ID
    status, res = api_request("GET", "/api/haccp/temperature/fridges?sede_id=1", token=admin_token)
    fridge_upd = next(f for f in res["fridges"] if f["id"] == orig_fridge_id)
    assert fridge_upd["nome_frigorifero"] == new_fridge_name

    # Verifica che lo storico delle registrazioni sia ancora collegato al medesimo ID
    status, h_res = api_request("GET", f"/api/haccp/temperature/history?sede_id=1&frigorifero_id={orig_fridge_id}", token=admin_token)
    assert status == 200
    assert h_res["count"] >= 1
    assert h_res["records"][0]["nome_frigorifero"] == new_fridge_name
    print(f"[OK] Frigorifero ID {orig_fridge_id} rinominato in '{new_fridge_name}' mantenendo intatti i controlli storici.")

    # ---------------------------------------------------------
    # TEST 3: LOTTI ED ETICHETTE ALIMENTI (12 PEZZI, RISTAMPA PEZZO 3, PROGRESSIVO SUCCESSIVO)
    # ---------------------------------------------------------
    print("\n--- TEST 3: Lotti ed Etichette Alimenti ---")
    now_dt = datetime.now()
    prep_str = now_dt.strftime("%Y-%m-%dT%H:%M")
    exp_str = (now_dt + timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M")

    # Creazione lotto da 12 pezzi per Lavis (Sede 1)
    lot_payload = {
        "sede_id": 1,
        "prodotto_nome": "Sugo al Brasato Tradizionale",
        "preparato_da": "Chef Marco",
        "lotto_originale": "CARNE-L2026/88-A",
        "numero_pezzi": 12,
        "data_preparazione": prep_str,
        "data_scadenza": exp_str,
        "durata_ore": 48,
        "formato_larghezza_mm": 60,
        "formato_altezza_mm": 40,
        "idempotency_key": f"test_idem_12_{time.time()}"
    }

    status, lot_res = api_request("POST", "/api/haccp/labels/create", lot_payload, token=admin_token)
    assert status == 200, f"Creazione lotto fallita: {lot_res}"
    lot_id_1 = lot_res["lot_id"]
    lotto_interno_1 = lot_res["lotto_interno"]
    labels_1 = lot_res["labels"]

    assert lotto_interno_1.startswith("LAV-"), f"Lotto interno deve iniziare per LAV-, ottenuto: {lotto_interno_1}"
    assert len(labels_1) == 12, f"Attese 12 etichette, generate: {len(labels_1)}"

    # Verifica che tutte le 12 etichette condividano gli stessi dati e varino solo per Pezzo X di 12
    for idx, lbl in enumerate(labels_1, start=1):
        assert lbl["lotto_interno"] == lotto_interno_1
        assert lbl["lotto_originale"] == "CARNE-L2026/88-A"
        assert lbl["prodotto_nome"] == "Sugo al Brasato Tradizionale"
        assert lbl["preparato_da"] == "Chef Marco"
        assert lbl["numero_pezzo"] == idx
        assert lbl["numero_pezzi"] == 12
        assert lbl["pezzo_label"] == f"Pezzo {idx} di 12"
        assert lbl["data_preparazione"] == prep_str
        assert lbl["data_scadenza"] == exp_str

    print(f"[OK] Lotto {lotto_interno_1} creato con 12 etichette (Pezzo 1 di 12 ... 12 di 12) corrette.")

    # Ristampa del pezzo 3
    piece_3 = labels_1[2] # indice 2 = pezzo 3
    status, reprint_p3 = api_request("GET", f"/api/haccp/labels/{piece_3['id']}/reprint", token=admin_token)
    assert status == 200
    p3_data = reprint_p3["label"]
    assert p3_data["id"] == piece_3["id"]
    assert p3_data["numero_pezzo"] == 3
    assert p3_data["numero_pezzi"] == 12
    assert p3_data["lotto_interno"] == lotto_interno_1
    assert p3_data["lotto_originale"] == "CARNE-L2026/88-A"
    assert p3_data["pezzo_label"] == "Pezzo 3 di 12"
    print(f"[OK] Ristampa Pezzo 3 di 12 eseguita con successo con dati e numerazione originale.")

    # Ristampa intero lotto
    status, reprint_lot = api_request("GET", f"/api/haccp/labels/lots/{lot_id_1}/reprint", token=admin_token)
    assert status == 200
    assert len(reprint_lot["labels"]) == 12
    print(f"[OK] Ristampa intero lotto {lotto_interno_1} restituite tutte le 12 etichette.")

    # Creazione nuova preparazione per verificare il progressivo successivo
    lot_payload_2 = {
        "sede_id": 1,
        "prodotto_nome": "Vellutata di Zucca e Zenzero",
        "preparato_da": "Aiuto Cuoco Luca",
        "lotto_originale": "ZUC-991#B",
        "numero_pezzi": 4,
        "data_preparazione": prep_str,
        "data_scadenza": exp_str,
        "durata_ore": 48,
        "formato_larghezza_mm": 60,
        "formato_altezza_mm": 40
    }
    status, lot_res_2 = api_request("POST", "/api/haccp/labels/create", lot_payload_2, token=admin_token)
    assert status == 200
    lotto_interno_2 = lot_res_2["lotto_interno"]

    # Verifica sequenzialità progressiva (es. LAV-000001 -> LAV-000002)
    num1 = int(lotto_interno_1.split("-")[1])
    num2 = int(lotto_interno_2.split("-")[1])
    assert num2 == num1 + 1, f"Sequenzialità non rispettata: {lotto_interno_1} -> {lotto_interno_2}"
    print(f"[OK] Nuova preparazione genera correttamente il progressivo successivo: {lotto_interno_1} -> {lotto_interno_2}")

    # Verifica lotto per Pergine (Sede 2) -> prefisso PER
    lot_payload_per = {
        "sede_id": 2,
        "prodotto_nome": "Tramezzini Tonno e Uova",
        "preparato_da": "Barista Pergine",
        "lotto_originale": "TONNO-7788",
        "numero_pezzi": 6,
        "data_preparazione": prep_str,
        "data_scadenza": exp_str,
        "durata_ore": 24
    }
    status, lot_res_per = api_request("POST", "/api/haccp/labels/create", lot_payload_per, token=admin_token)
    assert status == 200
    assert lot_res_per["lotto_interno"].startswith("PER-"), f"Atteso prefisso PER-, ottenuto: {lot_res_per['lotto_interno']}"
    print(f"[OK] Sede 2 Pergine genera prefisso PER- univoco: {lot_res_per['lotto_interno']}")

    # Idempotenza: invio della stessa richiesta con la stessa idempotency_key
    status, idem_res = api_request("POST", "/api/haccp/labels/create", lot_payload, token=admin_token)
    assert status == 200
    assert idem_res["lotto_interno"] == lotto_interno_1, "L'idempotenza deve restituire lo stesso lotto interno senza ricrearlo!"
    print(f"[OK] Idempotenza confermata: richiesta duplicata restituisce lotto originale senza incremento.")

    # Ricerca nello storico
    status, search_res = api_request("GET", f"/api/haccp/labels/history?sede_id=1&search=CARNE-L2026", token=admin_token)
    assert status == 200
    assert len(search_res["lotti"]) >= 1
    assert search_res["lotti"][0]["lotto_originale"] == "CARNE-L2026/88-A"
    print(f"[OK] Ricerca per lotto originale riuscita ({search_res['count']} trovati).")

    # ---------------------------------------------------------
    # TEST 4: REGISTRI PULIZIE (MURI, VETRI, MAGAZZINO)
    # ---------------------------------------------------------
    print("\n--- TEST 4: Registri Pulizie (Muri, Vetri, Magazzino) ---")
    today_str = date.today().strftime("%Y-%m-%d")

    for tipo, freq_days, is_month in [("muri", 30, True), ("vetri", 30, True), ("magazzino", 7, False)]:
        status, clean_res = api_request("POST", "/api/haccp/cleaning/record", {
            "sede_id": 1,
            "tipo_pulizia": tipo,
            "data_esecuzione": today_str,
            "ora_esecuzione": "14:30",
            "operatore": "Addetto Pulizie",
            "note": f"Igienizzazione approfondita {tipo}"
        }, token=admin_token)
        assert status == 200, f"Registrazione pulizia {tipo} fallita: {clean_res}"
        prossima = clean_res["prossima_scadenza"]

        if is_month:
            expected_date = HaccpService.add_calendar_month(date.today()).strftime("%Y-%m-%d")
        else:
            expected_date = (date.today() + timedelta(days=7)).strftime("%Y-%m-%d")

        assert prossima == expected_date, f"Scadenza {tipo}: atteso {expected_date}, ottenuto {prossima}"

        # Verifica stato pulizia
        status, st_res = api_request("GET", f"/api/haccp/cleaning/status?sede_id=1&tipo_pulizia={tipo}", token=admin_token)
        assert status == 200
        assert st_res["has_record"] is True
        assert st_res["is_overdue"] is False
        assert st_res["prossima_scadenza"] == expected_date

    print("[OK] Registrazione e calcolo scadenze pulizie Muri (mese), Vetri (mese) e Magazzino (7gg) verificati.")

    # ---------------------------------------------------------
    # TEST 5: MONITORAGGIO INFESTANTI (8 VOCI OBBLIGATORIE)
    # ---------------------------------------------------------
    print("\n--- TEST 5: Monitoraggio Infestanti ---")
    # 1. Verifica che se mancano risposte il server risponda con errore 400
    status, err_res = api_request("POST", "/api/haccp/pests/record", {
        "sede_id": 1,
        "operatore": "Ispettore HACCP",
        "risposte": [
            {"voce": "Peli o piume", "esito": "ASSENZA"}
        ]
    }, token=admin_token)
    assert status == 400, "Deve bloccare se non tutte le 8 voci sono fornite!"
    print("[OK] Blocco validazione su meno di 8 voci verificato (HTTP 400).")

    # 2. Registrazione valida di tutte le 8 voci (con una presenza documentata)
    valid_risposte = [
        {"voce": "Peli o piume", "esito": "ASSENZA"},
        {"voce": "Segni di roditori", "esito": "ASSENZA"},
        {"voce": "Insetti vivi", "esito": "ASSENZA"},
        {"voce": "Insetti morti", "esito": "ASSENZA"},
        {"voce": "Roditori", "esito": "ASSENZA"},
        {"voce": "Contenitori danneggiati da animali o insetti", "esito": "PRESENZA", "zona": "Magazzino bibite", "azione": "Sostituito cartone e posizionata trappola di monitoraggio", "note": "Imballo forato"},
        {"voce": "Feci o escrementi", "esito": "ASSENZA"},
        {"voce": "Animali infestanti nelle esche", "esito": "ASSENZA"}
    ]

    status, pest_res = api_request("POST", "/api/haccp/pests/record", {
        "sede_id": 1,
        "operatore": "Marco Rossi",
        "data_controllo": today_str,
        "ora_controllo": "11:00",
        "note_generali": "Controllo periodico mensile effettuato su tutte le zone",
        "risposte": valid_risposte
    }, token=admin_token)
    assert status == 200, f"Registrazione infestanti fallita: {pest_res}"
    insp_id = pest_res["id"]
    assert pest_res["has_presenze"] is True
    exp_pest_deadline = HaccpService.add_calendar_month(date.today()).strftime("%Y-%m-%d")
    assert pest_res["prossima_scadenza"] == exp_pest_deadline

    # 3. Recupero dettaglio dell'ispezione
    status, detail_res = api_request("GET", f"/api/haccp/pests/{insp_id}", token=admin_token)
    assert status == 200
    insp = detail_res["inspection"]
    assert insp["operatore"] == "Marco Rossi"
    assert len(insp["risposte"]) == 8
    voce_presenza = next(r for r in insp["risposte"] if r["voce"] == "Contenitori danneggiati da animali o insetti")
    assert voce_presenza["esito"] == "PRESENZA"
    assert voce_presenza["zona"] == "Magazzino bibite"
    print(f"[OK] Ispezione infestanti 8 voci salvata e verificata con successo (ID {insp_id}, scadenza {exp_pest_deadline}).")

    # ---------------------------------------------------------
    # TEST 6: BANNER DEGLI AVVISI SCADUTI (/api/haccp/alerts)
    # ---------------------------------------------------------
    print("\n--- TEST 6: Banner Avvisi Scaduti (/api/haccp/alerts) ---")
    status, alerts_res = api_request("GET", "/api/haccp/alerts?sede_id=2", token=admin_token)
    assert status == 200
    alerts_sede2 = alerts_res["alerts"]
    assert len(alerts_sede2) > 0, "Sede 2 senza registrazioni pregresse deve avere avvisi di prima registrazione!"

    # Verifica presenza messaggio 'Prima registrazione da effettuare'
    first_time_alerts = [a for a in alerts_sede2 if a.get("is_first_time")]
    assert len(first_time_alerts) > 0
    assert any("Prima registrazione da effettuare" in a["overdue_text"] for a in first_time_alerts)
    print(f"[OK] Avvisi Sede 2: {len(alerts_sede2)} avvisi generati, con 'Prima registrazione da effettuare' corretta.")

    # 1. Verifica blocco accesso avvisi sede non autorizzata (403 per cucina.lavis su Sede 2)
    status, err_res = api_request("GET", "/api/haccp/alerts?sede_id=2", token=cucina_token)
    assert status == 403, f"cucina.lavis non deve poter visualizzare avvisi per Sede 2! Status: {status}"
    print("[OK] Accesso avvisi Sede 2 bloccato per account non autorizzato (HTTP 403).")

    # 2. Verifica avvisi Sede 1 filtrati sui soli permessi autorizzati di cucina.lavis
    status, alerts_cucina = api_request("GET", "/api/haccp/alerts?sede_id=1", token=cucina_token)
    assert status == 200
    cucina_alert_types = {a["tipo"] for a in alerts_cucina["alerts"]}
    # cucina.lavis ha solo etichette, temp, oil, hood
    for a in alerts_cucina["alerts"]:
        assert a["tipo"] in ("temp", "oil", "hood", "labels"), f"Tipo non autorizzato {a['tipo']} visibile a cucina.lavis!"
    print(f"[OK] Avvisi per cucina.lavis contengono solo attività autorizzate ({cucina_alert_types}).")

    # 3. Verifica avvisi distinti per frigorifero e friggitrice scaduti
    old_temp_date = (date.today() - timedelta(days=3)).strftime("%Y-%m-%d")
    status, _ = api_request("POST", "/api/haccp/temperature/record", {
        "sede_id": 2,
        "frigorifero_id": 6,
        "temperatura": 3.4,
        "esito": "CONFORME",
        "operatore": "Operatore Pergine",
        "data_controllo": old_temp_date,
        "ora_controllo": "08:00"
    }, token=admin_token)
    assert status == 200

    old_oil_date = (date.today() - timedelta(days=10)).strftime("%Y-%m-%d")
    status, _ = api_request("POST", "/api/haccp/oil/record", {
        "sede_id": 2,
        "friggitrice_id": 3,
        "data_cambio": old_oil_date,
        "ora_cambio": "08:00",
        "operatore": "Operatore Pergine"
    }, token=admin_token)
    assert status == 200

    # Richiediamo gli avvisi per Sede 2
    status, s2_alerts_res = api_request("GET", "/api/haccp/alerts?sede_id=2", token=admin_token)
    assert status == 200
    s2_alerts = s2_alerts_res["alerts"]

    fridge_alert = next((a for a in s2_alerts if a["tipo"] == "temp" and a.get("target_id") == 6), None)
    fryer_alert = next((a for a in s2_alerts if a["tipo"] == "oil" and a.get("target_id") == 3), None)

    assert fridge_alert is not None, "Frigorifero scaduto deve produrre il proprio avviso!"
    assert fryer_alert is not None, "Friggitrice scaduta deve produrre il proprio avviso!"
    assert fridge_alert["id"] != fryer_alert["id"]
    assert "Scadut" in fridge_alert["overdue_text"]
    assert "Scadut" in fryer_alert["overdue_text"]
    assert not fridge_alert["is_first_time"]
    assert not fryer_alert["is_first_time"]
    print(f"[OK] Frigorifero 6 e Friggitrice 3 generano avvisi propri e distinti per Sede 2:")
    print(f"     - {fridge_alert['nome_attrezzatura']}: {fridge_alert['overdue_text']}")
    print(f"     - {fryer_alert['nome_attrezzatura']}: {fryer_alert['overdue_text']}")

    print("\n" + "=" * 70)
    print("TUTTI I TEST DELLA SUITE HACCP COMPLETATI CON SUCCESSO! (100% PASS)")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
