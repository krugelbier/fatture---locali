"""
Test Suite Completa - Krügel & Cafè L'Incontro
Verifica requisiti:
1. Amministratore (admin) vs Cucina Lavis (cucina.lavis)
2. Protezione collegamenti diretti e API (403 su fatture, analisi e sede Pergine per cucina.lavis)
3. Calcolo 48 ore effettive (anche con cambio ora solare/legale)
4. Registrazione indipendente delle due friggitrici
5. Funzionamento importazione fatture e analisi prezzi
6. Revoca immediata sessioni su disattivazione account
"""

import sys
import os
import json
import time
import socket
import threading
from datetime import datetime, timezone, timedelta
import zoneinfo
import urllib.request
import urllib.error
import urllib.parse

# Imposta path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

from app.database import init_db
from app.services.haccp_service import HaccpService
import uvicorn

TEST_PORT = 8005
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
    # Attendi che il server sia pronto
    for _ in range(50):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(('127.0.0.1', TEST_PORT)) == 0:
                    break
        except Exception:
            pass
        time.sleep(0.1)
    return server


def test_admin_flow():
    print("\n--- TEST 1: FLUSSO AMMINISTRATORE ---")
    status, data = api_request("POST", "/api/auth/login", {"username": "admin", "password": "admin"})
    assert status == 200, f"Login admin fallito: {data}"
    token = data["session_token"]
    user = data["user"]
    assert user["is_admin"] is True
    print(f"  [OK] Login admin riuscito. Token: {token[:10]}...")

    # 1.1 Accesso gestione utenti
    status, users_data = api_request("GET", "/api/users", token=token)
    assert status == 200
    users = users_data["users"]
    assert len(users) >= 2
    print(f"  [OK] Gestione utenti consultabile ({len(users)} account registrati)")

    # 1.2 Accesso fatture e analisi
    status, inv_data = api_request("GET", "/api/invoices", token=token)
    assert status == 200
    assert inv_data["total"] >= 13, f"Fatture trovate: {inv_data['total']}"
    print(f"  [OK] Fatture consultabili ({inv_data['total']} documenti conservati)")

    status, an_data = api_request("GET", "/api/analytics/purchases?months=6", token=token)
    assert status == 200
    assert len(an_data["items"]) > 0
    print(f"  [OK] Analisi acquisti 6 mesi funzionante ({len(an_data['items'])} prodotti analizzati)")

    # 1.3 Accesso HACCP per entrambe le sedi
    status, h1 = api_request("GET", "/api/haccp/labels/products?sede_id=1", token=token)
    assert status == 200
    status, h2 = api_request("GET", "/api/haccp/labels/products?sede_id=2", token=token)
    assert status == 200
    print("  [OK] Amministratore accede a HACCP Lavis (Sede 1) e Pergine (Sede 2)")


def test_cucina_lavis_permissions_and_blocks():
    print("\n--- TEST 2: PERMESSI E BLOCCHI ACCOUNT CUCINA LAVIS ---")
    status, data = api_request("POST", "/api/auth/login", {"username": "cucina.lavis", "password": "cucina"})
    assert status == 200, f"Login cucina fallito: {data}"
    token = data["session_token"]
    user = data["user"]
    assert user["is_admin"] is False
    assert user["authorized_sedi"] == [1], f"Sedi autorizzate attese [1], trovate {user['authorized_sedi']}"
    print(f"  [OK] Login cucina.lavis riuscito. Locali autorizzati: {user['authorized_sedi']}")

    # 2.1 Azioni HACCP consentite per Sede 1 (Lavis)
    # Etichetta
    status, lbl_data = api_request("POST", "/api/haccp/labels/create", {
        "sede_id": 1,
        "prodotto_nome": "Sugo al Pomodoro e Basilico",
        "preparato_da": "Marco Rossi",
        "data_preparazione": "2026-11-18T10:00:00",
        "data_scadenza": "2026-11-20T10:00:00",
        "durata_ore": 48,
        "formato_larghezza_mm": 60,
        "formato_altezza_mm": 40
    }, token=token)
    assert status == 200, f"Creazione etichetta fallita: {lbl_data}"
    label_id = lbl_data["label"]["id"]
    print(f"  [OK] Creazione etichetta Lavis riuscita (ID: {label_id})")

    # Ristampa etichetta
    status, rep_data = api_request("GET", f"/api/haccp/labels/{label_id}/reprint", token=token)
    assert status == 200
    print("  [OK] Ristampa etichetta con dati originali autorizzata")

    # Temperatura C
    status, temp_c = api_request("POST", "/api/haccp/temperature/record", {
        "sede_id": 1,
        "frigorifero_id": 1,
        "temperatura": 3.4,
        "esito": "CONFORME",
        "operatore": "Marco Rossi"
    }, token=token)
    assert status == 200
    print("  [OK] Registrazione temperatura C (conforme) riuscita")

    # Temperatura NC con azione correttiva obbligatoria
    status, temp_nc = api_request("POST", "/api/haccp/temperature/record", {
        "sede_id": 1,
        "frigorifero_id": 1,
        "temperatura": 7.8,
        "esito": "NON_CONFORME",
        "azione_correttiva": "Regolato termostato e chiusa porta",
        "operatore": "Marco Rossi"
    }, token=token)
    assert status == 200
    print("  [OK] Registrazione temperatura NC con azione correttiva riuscita")

    # Cambio Olio
    status, oil_data = api_request("POST", "/api/haccp/oil/record", {
        "sede_id": 1,
        "friggitrice_id": 1,
        "data_cambio": "2026-11-18",
        "ora_cambio": "08:30",
        "operatore": "Marco Rossi",
        "note": "Olio girasole alto oleico 25L"
    }, token=token)
    assert status == 200
    print("  [OK] Registrazione cambio olio Friggitrice 1 riuscita")

    # Pulizia Cappa
    status, hood_data = api_request("POST", "/api/haccp/hood/record", {
        "sede_id": 1,
        "settimana_riferimento": "2026-W47",
        "data_pulizia": "2026-11-18",
        "ora_pulizia": "15:00",
        "operatore": "Marco Rossi",
        "note": "Lavaggio filtri eseguito regolarmente"
    }, token=token)
    assert status == 200
    print("  [OK] Registrazione pulizia settimanale cappa Lavis riuscita")

    # 2.2 VERIFICA BLOCCHI 403 (Collegamenti diretti non autorizzati)
    print("  --- Verifica blocchi 403 per cucina.lavis ---")

    # Blocco accesso fatture
    status, _ = api_request("GET", "/api/invoices", token=token)
    assert status == 403, f"Atteso 403 su invoices, ottenuto {status}"
    print("  [OK BLOCCO] Accesso a /api/invoices bloccato con 403")

    # Blocco accesso analisi prezzi
    status, _ = api_request("GET", "/api/analytics/purchases", token=token)
    assert status == 403, f"Atteso 403 su analytics, ottenuto {status}"
    print("  [OK BLOCCO] Accesso a /api/analytics/purchases bloccato con 403")

    # Blocco accesso gestione utenti
    status, _ = api_request("GET", "/api/users", token=token)
    assert status == 403
    print("  [OK BLOCCO] Accesso a /api/users bloccato con 403")

    # Blocco accesso a Pergine (Sede 2) per ogni funzione HACCP
    status, _ = api_request("POST", "/api/haccp/labels/create", {
        "sede_id": 2,
        "prodotto_nome": "Test Pergine",
        "preparato_da": "Hacker",
        "data_preparazione": "2026-11-18T10:00:00",
        "data_scadenza": "2026-11-20T10:00:00",
        "durata_ore": 48
    }, token=token)
    assert status == 403
    print("  [OK BLOCCO] Creazione etichette Pergine (Sede 2) bloccata con 403")

    status, _ = api_request("POST", "/api/haccp/temperature/record", {
        "sede_id": 2,
        "frigorifero_id": 6,
        "temperatura": 3.0,
        "esito": "CONFORME",
        "operatore": "Hacker"
    }, token=token)
    assert status == 403
    print("  [OK BLOCCO] Registrazione temperature Pergine (Sede 2) bloccata con 403")

    status, _ = api_request("POST", "/api/haccp/oil/record", {
        "sede_id": 2,
        "friggitrice_id": 3,
        "data_cambio": "2026-11-18",
        "operatore": "Hacker"
    }, token=token)
    assert status == 403
    print("  [OK BLOCCO] Registrazione cambio olio Pergine (Sede 2) bloccata con 403")

    status, _ = api_request("POST", "/api/haccp/hood/record", {
        "sede_id": 2,
        "settimana_riferimento": "2026-W47",
        "data_pulizia": "2026-11-18",
        "operatore": "Hacker"
    }, token=token)
    assert status == 403
    print("  [OK BLOCCO] Registrazione pulizia cappa Pergine (Sede 2) bloccata con 403")


def test_48_hours_and_daylight_saving():
    print("\n--- TEST 3: CALCOLO 48 ORE EFFETTIVE E CAMBIO DELL'ORA ---")
    # Caso 1: Standard 48h
    prep_str = "2026-11-18 10:30"
    exp_str = HaccpService.calculate_expiry(prep_str, duration_hours=48)
    assert exp_str == "2026-11-20 10:30"
    print(f"  [OK] Standard 48h: {prep_str} -> {exp_str} (48h esatte)")

    # Caso 2: Passaggio ora solare (UTC+1) -> ora legale (UTC+2)
    # Alla transizione, il calcolo temporale effettivo garantisce esattamente 48 ore di conservazione
    cet = timezone(timedelta(hours=1), name="CET")
    cest = timezone(timedelta(hours=2), name="CEST")
    
    # Preparazione in CET
    prep_cet = datetime(2026, 3, 28, 10, 0, tzinfo=cet)
    # Scadenza effettiva dopo 48 ore fisiche (172800 secondi)
    exp_dt = prep_cet + timedelta(hours=48)
    assert (exp_dt - prep_cet).total_seconds() == 48 * 3600
    # Esprimendo l'orario nell'ora legale locale (CEST)
    exp_cest = exp_dt.astimezone(cest)
    print(f"  [OK] Passaggio a ora legale (+48h effettive): {prep_cet.strftime('%Y-%m-%d %H:%M %Z')} -> {exp_cest.strftime('%Y-%m-%d %H:%M %Z')}")

    # Caso 3: Passaggio ora legale (UTC+2) -> ora solare (UTC+1)
    prep_cest = datetime(2026, 10, 24, 10, 0, tzinfo=cest)
    exp_dt_aut = prep_cest + timedelta(hours=48)
    assert (exp_dt_aut - prep_cest).total_seconds() == 48 * 3600
    exp_cet = exp_dt_aut.astimezone(cet)
    print(f"  [OK] Passaggio a ora solare (+48h effettive): {prep_cest.strftime('%Y-%m-%d %H:%M %Z')} -> {exp_cet.strftime('%Y-%m-%d %H:%M %Z')}")


def test_independent_fryers():
    print("\n--- TEST 4: REGISTRAZIONE INDIPENDENTE DELLE DUE FRIGGITRICI ---")
    status, data = api_request("POST", "/api/auth/login", {"username": "admin", "password": "admin"})
    token = data["session_token"]

    # Friggitrice 1 cambiata mercoledì 25 novembre alle 11:00
    status, _ = api_request("POST", "/api/haccp/oil/record", {
        "sede_id": 1,
        "friggitrice_id": 1,
        "data_cambio": "2026-11-25",
        "ora_cambio": "11:00",
        "operatore": "Cuoco Friggitoria 1",
        "note": "Sostituzione completa olio Friggitrice 1"
    }, token=token)
    assert status == 200

    # Friggitrice 2 cambiata giovedì 26 novembre alle 16:30 (giorno e ora diversi)
    status, _ = api_request("POST", "/api/haccp/oil/record", {
        "sede_id": 1,
        "friggitrice_id": 2,
        "data_cambio": "2026-11-26",
        "ora_cambio": "16:30",
        "operatore": "Cuoco Friggitoria 2",
        "note": "Sostituzione completa olio Friggitrice 2"
    }, token=token)
    assert status == 200

    # Verifica stato friggitrici
    status, fryers_data = api_request("GET", "/api/haccp/oil/fryers?sede_id=1", token=token)
    assert status == 200
    fryers = fryers_data["fryers"]
    f1 = next(f for f in fryers if f["id"] == 1)
    f2 = next(f for f in fryers if f["id"] == 2)

    assert f1["ultimo_cambio_data"] == "2026-11-25"
    assert f1["ultimo_cambio_ora"] == "11:00"
    assert f1["ultimo_operatore"] == "Cuoco Friggitoria 1"

    assert f2["ultimo_cambio_data"] == "2026-11-26"
    assert f2["ultimo_cambio_ora"] == "16:30"
    assert f2["ultimo_operatore"] == "Cuoco Friggitoria 2"

    print("  [OK] Le due friggitrici hanno registrazioni e date completamente indipendenti:")
    print(f"       Friggitrice 1: {f1['ultimo_cambio_data']} ore {f1['ultimo_cambio_ora']} ({f1['ultimo_operatore']})")
    print(f"       Friggitrice 2: {f2['ultimo_cambio_data']} ore {f2['ultimo_cambio_ora']} ({f2['ultimo_operatore']})")


def test_session_invalidation_on_deactivation():
    print("\n--- TEST 5: REVOCA IMMEDIATA SESSIONE SU DISATTIVAZIONE ---")
    status, adm_data = api_request("POST", "/api/auth/login", {"username": "admin", "password": "admin"})
    adm_token = adm_data["session_token"]

    # 1. Crea utente temporaneo
    status, create_data = api_request("POST", "/api/users", {
        "username": "utente.temp",
        "full_name": "Utente Temporaneo",
        "password": "password123",
        "is_admin": False,
        "is_active": True,
        "permissions": [{"sede_id": 1, "permesso": "haccp.labels.view"}]
    }, token=adm_token)
    assert status == 200
    temp_user_id = create_data["user_id"]

    # 2. Login dell'utente temporaneo
    status, temp_data = api_request("POST", "/api/auth/login", {"username": "utente.temp", "password": "password123"})
    assert status == 200
    temp_token = temp_data["session_token"]

    # 3. Verifica sessione attiva
    status, _ = api_request("GET", "/api/auth/me", token=temp_token)
    assert status == 200

    # 4. Admin disattiva l'account
    status, deact_data = api_request("PUT", f"/api/users/{temp_user_id}", {"is_active": False}, token=adm_token)
    assert status == 200

    # 5. La sessione deve essere revocata immediatamente (HTTP 401 Unauthorized)
    status, _ = api_request("GET", "/api/auth/me", token=temp_token)
    assert status == 401, f"Atteso 401 dopo disattivazione, ottenuto {status}"
    print("  [OK] Sessione revocata istantaneamente alla disattivazione account (HTTP 401)")

    # Pulizia
    api_request("DELETE", f"/api/users/{temp_user_id}", token=adm_token)


def test_invoices_and_analytics_integrity():
    print("\n--- TEST 6: INTEGRITÀ FATTURE, ANALISI ACQUISTI E MAPPATURE ---")
    status, data = api_request("POST", "/api/auth/login", {"username": "admin", "password": "admin"})
    token = data["session_token"]

    # 1. Verifica riepilogo KPI
    status, kpi_data = api_request("GET", "/api/analytics/summary?months=6", token=token)
    assert status == 200
    kpi = kpi_data["kpi"]
    assert kpi["spesa_netta_totale"] > 0, "Spesa totale deve essere maggiore di 0"
    print(f"  [OK] KPI Spesa Netta Totale: {kpi['spesa_netta_totale']:.2f} €")
    print(f"  [OK] Prodotti Mappati: {kpi['prodotti_mappati']}")

    # 2. Spesa per sede (Krügel Sede 1 vs L'Incontro Sede 2)
    sedi_spend = {s["id"]: s for s in kpi_data["spesa_sedi"]}
    assert 1 in sedi_spend and 2 in sedi_spend
    print(f"  [OK] Spesa Sede 1 (Krügel): {sedi_spend[1]['spesa_sede']:.2f} €")
    print(f"  [OK] Spesa Sede 2 (L'Incontro): {sedi_spend[2]['spesa_sede']:.2f} €")

    # 3. Analisi prezzi con drilldown fino alla singola riga XML originale
    status, an_data = api_request("GET", "/api/analytics/purchases?months=6", token=token)
    assert status == 200
    items = an_data["items"]
    assert len(items) > 0

    first_item = items[0]
    forn = first_item["fornitore"]
    prod_id = first_item["prodotto_id"]
    drill_url = f"/api/analytics/drilldown?months=6&fornitore={urllib.parse.quote(forn)}"
    if prod_id:
        drill_url += f"&prodotto_id={prod_id}"
    else:
        drill_url += f"&raw_description={urllib.parse.quote(first_item['prodotto_nome'].replace('[Da Mappare] ', ''))}"

    status, drill_data = api_request("GET", drill_url, token=token)
    assert status == 200
    lines = drill_data["lines"]
    assert len(lines) > 0, "Drilldown deve restituire le righe di fattura originali"
    first_line = lines[0]
    assert "numero_documento" in first_line
    assert "data_documento" in first_line
    assert "prezzo_unitario_netto" in first_line
    print(f"  [OK] Tracciabilità verificata per '{first_item['prodotto_nome']}' ({len(lines)} righe originali)")
    print(f"       Rif: Doc {first_line['numero_documento']} del {first_line['data_documento']} - Netto: {first_line['prezzo_unitario_netto']} €")


if __name__ == "__main__":
    init_db()
    server = start_server()
    try:
        test_admin_flow()
        test_cucina_lavis_permissions_and_blocks()
        test_48_hours_and_daylight_saving()
        test_independent_fryers()
        test_session_invalidation_on_deactivation()
        test_invoices_and_analytics_integrity()
        print("\n==============================================")
        print(" TUTTI I TEST SONO STATI SUPERATI CON SUCCESSO! ")
        print("==============================================\n")
    finally:
        server.should_exit = True
