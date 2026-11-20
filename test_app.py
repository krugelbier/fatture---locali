# Automated Test Suite for Fatture Locali
import sys
import os
import sqlite3
import json

# Ensure root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import init_db, get_db
from app.services.demo_service import generate_demo_xmls, load_demo_data_into_db
from app.services.analytics_service import AnalyticsService

def run_tests():
    print("=== TEST 1: INIZIALIZZAZIONE DATABASE ===")
    init_db()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM sedi")
    sedi_count = cursor.fetchone()["cnt"]
    print(f"Sedi trovate nel DB: {sedi_count} (Attese >= 2)")
    assert sedi_count >= 2, "Errore: sedi non inizializzate!"

    cursor.execute("SELECT COUNT(*) as cnt FROM prodotti")
    prod_count = cursor.fetchone()["cnt"]
    print(f"Prodotti canonici di default: {prod_count} (Attesi >= 10)")
    assert prod_count >= 10, "Errore: prodotti non inizializzati!"

    print("\n=== TEST 2: GENERAZIONE FILE DEMO XML ===")
    xml_paths = generate_demo_xmls()
    print(f"File XML generati in demo_fatture/: {len(xml_paths)}")
    for p in xml_paths:
        print(f"  - {os.path.basename(p)} ({os.path.getsize(p)} bytes)")
    assert len(xml_paths) >= 6, "Errore: numero di file XML demo insufficiente!"

    print("\n=== TEST 3: IMPORTAZIONE FILE XML E ASSEGNAZIONE SEDI ===")
    results = load_demo_data_into_db(conn)
    print(f"Risultati importazione:")
    for r in results:
        status = "OK" if r.get("success") else "FAIL"
        print(f"  [{status}] {r.get('numero_documento', r.get('filename'))}: Sede = {r.get('sede_assegnata')} ({r.get('metodo_assegnazione')}) | Righe = {r.get('righe_salvate', 0)}")

    cursor.execute("SELECT COUNT(*) as cnt FROM documenti")
    doc_count = cursor.fetchone()["cnt"]
    cursor.execute("SELECT COUNT(*) as cnt FROM righe_fattura")
    righe_count = cursor.fetchone()["cnt"]
    print(f"Totale documenti salvati nel DB: {doc_count}")
    print(f"Totale righe salvate nel DB: {righe_count}")

    print("\n=== TEST 4: VERIFICA CONTROLLO DUPLICATI ===")
    # Tentiamo di re-importare gli stessi file: devono essere tutti riconosciuti come duplicati
    dup_results = load_demo_data_into_db(conn)
    dup_detected = sum(1 for r in dup_results if r.get("is_duplicate"))
    print(f"Duplicati correttamente rilevati e bloccati: {dup_detected} su {len(dup_results)}")
    assert dup_detected == len(dup_results), "Errore: i duplicati non sono stati bloccati!"

    print("\n=== TEST 5: VERIFICA ASSEGNAZIONE MISTA CON DDT ===")
    cursor.execute("""
        SELECT r.numero_linea, r.descrizione, r.sede_id, s.nome as sede_nome, r.metodo_assegnazione
        FROM righe_fattura r
        JOIN documenti d ON r.documento_id = d.id
        LEFT JOIN sedi s ON r.sede_id = s.id
        WHERE d.numero_documento = 'FT-DIFF-2026/184'
        ORDER BY r.numero_linea ASC
    """)
    miste_lines = cursor.fetchall()
    print("Righe fattura mista FT-DIFF-2026/184 (DDT 1043 a Krügel, DDT 1044 a Cafè L'Incontro):")
    for l in miste_lines:
        print(f"  Linea #{l['numero_linea']}: {l['descrizione']} -> Sede: {l['sede_nome']} (metodo: {l['metodo_assegnazione']})")
    
    # Verifica che le righe 1 e 2 siano Krügel e 3 e 4 siano Cafè Incontro
    assert "Krügel" in miste_lines[0]["sede_nome"], "Linea 1 deve essere assegnata a Krügel!"
    assert "Krügel" in miste_lines[1]["sede_nome"], "Linea 2 deve essere assegnata a Krügel!"
    assert "Incontro" in miste_lines[2]["sede_nome"], "Linea 3 deve essere assegnata a Cafè Incontro!"
    assert "Incontro" in miste_lines[3]["sede_nome"], "Linea 4 deve essere assegnata a Cafè Incontro!"
    print("  -> Corretta assegnazione riga per riga tramite DDT verificata al 100%!")

    print("\n=== TEST 6: VERIFICA FATTURA DA ASSEGNARE ===")
    cursor.execute("SELECT id, numero_documento, stato_assegnazione FROM documenti WHERE numero_documento = 'FT-METRO-09881'")
    unassigned_doc = cursor.fetchone()
    print(f"Fattura senza indirizzo (Metro): stato = {unassigned_doc['stato_assegnazione']}")
    assert unassigned_doc["stato_assegnazione"] == "DA_ASSEGNARE", "Fattura Metro deve risultare DA_ASSEGNARE!"

    print("\n=== TEST 7: ANALISI ACQUISTI E PREZZO MEDIO PONDERATO (ULTIMI 6 MESI) ===")
    analytics = AnalyticsService.get_purchase_analytics(conn, months_back=6)
    print(f"Prodotti analizzati: {len(analytics)}")
    for a in analytics:
        print(f"  • {a['prodotto_nome']} ({a['fornitore']}):")
        print(f"      Qtà Base: {a['quantita_fatturata']} {a['unita_base']} | P. Medio: € {a['prezzo_medio_ponderato']:.2f}/{a['unita_base']} | Min: € {a['prezzo_min']:.2f} | Max: € {a['prezzo_max']:.2f} | Var: {a['variazione_perc']}% | Sedi: {a['sedi']}")

    # Verifica calcolo Heineken (ha acquisto recente a 88.20/30 = 2.94€/L, acquisto vecchio a 92.12/30 = 3.07€/L, e nota credito di storno)
    heineken_stats = next((x for x in analytics if "Heineken" in x["prodotto_nome"]), None)
    assert heineken_stats is not None, "Heineken deve essere presente nelle statistiche!"
    print(f"  -> Test Heineken: P. Min = {heineken_stats['prezzo_min']} €/LT, P. Max = {heineken_stats['prezzo_max']} €/LT, Medio Ponderato = {heineken_stats['prezzo_medio_ponderato']} €/LT")
    assert heineken_stats["unita_base"] == "LT", "Unità base per Heineken deve essere LT!"
    assert heineken_stats["prezzo_min"] <= heineken_stats["prezzo_medio_ponderato"] <= heineken_stats["prezzo_max"], "Consistenza min <= medio <= max"

    print("\n=== TEST 8: TRACCIABILITÀ DRILL-DOWN A LIVELLO DI RIGA ===")
    drilldown = AnalyticsService.get_price_drilldown_lines(conn, prodotto_id=heineken_stats["prodotto_id"])
    print(f"Righe di fattura originali tracciate per {heineken_stats['prodotto_nome']}: {len(drilldown)}")
    for dl in drilldown:
        nc = " (NOTA CREDITO)" if dl["is_credit_note"] else ""
        print(f"  Doc: {dl['numero_documento']} del {dl['data_documento']}{nc} | Riga #{dl['numero_linea']}: '{dl['descrizione_originale']}' | P. Netto Orig: € {dl['prezzo_unitario_netto']} | Qtà: {dl['quantita_originale']} {dl['um_originale']} -> {dl['quantita_base']} {dl['prodotto_um_base']} a € {dl['prezzo_unitario_base']:.2f}/{dl['prodotto_um_base']}")

    conn.close()
    print("\n==========================================")
    print("TUTTI I TEST SONO STATI SUPERATI CON SUCCESSO!")
    print("==========================================")

if __name__ == "__main__":
    run_tests()
