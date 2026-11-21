# HACCP API Routes (Etichette, Temperature Frigo, Cambio Olio, Pulizia Cappa, Pulizie Generali, Monitoraggio Infestanti, Avvisi)
import json
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
from app.database import get_db
from app.routes.auth import get_current_user
from app.services.auth_service import user_has_permission
from app.services.haccp_service import HaccpService

router = APIRouter(prefix="/api/haccp", tags=["HACCP"])

def verify_sede_permission(user: dict, sede_id: int, permission: str):
    if not user_has_permission(user, sede_id, permission):
        raise HTTPException(
            status_code=403,
            detail=f"Permesso non accordato ({permission}) per il locale specificato."
        )

# ========================================================
# 1. HACCP - ETICHETTE ALIMENTI & LOTTI
# ========================================================
class LabelProductCreate(BaseModel):
    sede_id: int
    nome_prodotto: str
    durata_ore: int = 48
    categoria: Optional[str] = "Generale"
    note: Optional[str] = ""

class LabelCreateRequest(BaseModel):
    sede_id: int
    prodotto: Optional[str] = None
    prodotto_nome: Optional[str] = None
    prodotto_id: Optional[int] = None
    preparato_da: str
    lotto_originale: Optional[str] = "ORIGINALE" # Lotto originale manuale (lettere, numeri, simboli)
    numero_pezzi: int = Field(default=1, ge=1) # Numero intero minimo 1
    data_preparazione: str # YYYY-MM-DD HH:MM oppure YYYY-MM-DDTHH:MM
    data_scadenza: str # YYYY-MM-DD HH:MM oppure YYYY-MM-DDTHH:MM
    durata_ore: int = 48
    larghezza_mm: Optional[int] = None
    altezza_mm: Optional[int] = None
    formato_larghezza_mm: Optional[int] = None
    formato_altezza_mm: Optional[int] = None
    idempotency_key: Optional[str] = None # Anti doppio-tocco / retry di rete

@router.get("/labels/products")
def list_label_products(sede_id: int = Query(...), user: dict = Depends(get_current_user)):
    if not (user_has_permission(user, sede_id, "haccp.labels.view") or user_has_permission(user, sede_id, "haccp.labels.create")):
        raise HTTPException(status_code=403, detail="Permesso non accordato per consultare i prodotti etichetta.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM haccp_prodotti_etichette
        WHERE sede_id = ? AND is_active = 1
        ORDER BY nome_prodotto ASC
    """, (sede_id,))
    products = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"products": products}

@router.post("/labels/products")
def create_label_product(req: LabelProductCreate, user: dict = Depends(get_current_user)):
    verify_sede_permission(user, req.sede_id, "haccp.labels.create")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO haccp_prodotti_etichette (sede_id, nome_prodotto, durata_ore, categoria, note)
        VALUES (?, ?, ?, ?, ?)
    """, (req.sede_id, req.nome_prodotto.strip(), req.durata_ore, req.categoria, req.note))
    p_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"success": True, "id": p_id, "message": "Prodotto e durata memorizzati."}

@router.post("/labels/create")
def create_and_save_label(req: LabelCreateRequest, user: dict = Depends(get_current_user)):
    verify_sede_permission(user, req.sede_id, "haccp.labels.create")
    if req.numero_pezzi < 1:
        raise HTTPException(status_code=400, detail="Il numero di pezzi deve essere almeno 1.")
    
    lotto_orig = (req.lotto_originale or "").strip()
    if not lotto_orig:
        lotto_orig = "ORIGINALE"

    prod_name = (req.prodotto_nome or req.prodotto or "Prodotto Alimentare").strip()
    w_mm = req.formato_larghezza_mm or req.larghezza_mm or 60
    h_mm = req.formato_altezza_mm or req.altezza_mm or 40

    conn = get_db()
    cursor = conn.cursor()

    # 1. Verifica Idempotenza per evitare doppi tocchi accidentali o errori di rete ripetuti
    if req.idempotency_key:
        cursor.execute("SELECT * FROM haccp_lotti WHERE idempotency_key = ?", (req.idempotency_key,))
        existing_lot = cursor.fetchone()
        if existing_lot:
            lot_dict = dict(existing_lot)
            cursor.execute("SELECT * FROM haccp_etichette WHERE lotto_id = ? ORDER BY numero_pezzo ASC", (lot_dict["id"],))
            labels = []
            for r in cursor.fetchall():
                d = dict(r)
                d["prodotto_nome"] = d["prodotto"]
                d["formato_larghezza_mm"] = d["larghezza_mm"]
                d["formato_altezza_mm"] = d["altezza_mm"]
                d["pezzo_label"] = f"Pezzo {d.get('numero_pezzo', 1)} di {d.get('numero_pezzi', 1)}"
                labels.append(d)
            conn.close()
            return {
                "success": True,
                "lot_id": lot_dict["id"],
                "lotto_interno": lot_dict["lotto_interno"],
                "numero_pezzi": lot_dict["numero_pezzi"],
                "labels": labels,
                "label": labels[0] if labels else None,
                "message": f"Lotto esistente recuperato (Idempotenza attiva): {lot_dict['lotto_interno']}."
            }

    # 2. Generazione progressivo interno univoco per sede (es. LAV-000001, PER-000001)
    lotto_interno = HaccpService.generate_next_lotto_interno(conn, req.sede_id)

    # 3. Inserimento testata lotto condiviso
    cursor.execute("""
        INSERT INTO haccp_lotti (
            sede_id, lotto_interno, lotto_originale, prodotto, prodotto_id,
            preparato_da, data_preparazione, data_scadenza, durata_ore,
            numero_pezzi, larghezza_mm, altezza_mm, idempotency_key
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        req.sede_id, lotto_interno, lotto_orig, prod_name, req.prodotto_id,
        req.preparato_da.strip(), req.data_preparazione, req.data_scadenza,
        req.durata_ore, req.numero_pezzi, w_mm, h_mm, req.idempotency_key
    ))
    lot_id = cursor.lastrowid

    # 4. Creazione singole etichette per ciascun pezzo (da 1 a N)
    labels = []
    for pezzo_num in range(1, req.numero_pezzi + 1):
        cursor.execute("""
            INSERT INTO haccp_etichette (
                sede_id, prodotto, preparato_da, data_preparazione,
                data_scadenza, durata_ore, larghezza_mm, altezza_mm,
                lotto_originale, lotto_interno, numero_pezzi, numero_pezzo, lotto_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            req.sede_id, prod_name, req.preparato_da.strip(),
            req.data_preparazione, req.data_scadenza, req.durata_ore,
            w_mm, h_mm, lotto_orig, lotto_interno, req.numero_pezzi, pezzo_num, lot_id
        ))
        lbl_id = cursor.lastrowid
        labels.append({
            "id": lbl_id,
            "lotto_id": lot_id,
            "sede_id": req.sede_id,
            "prodotto": prod_name,
            "prodotto_nome": prod_name,
            "preparato_da": req.preparato_da.strip(),
            "data_preparazione": req.data_preparazione,
            "data_scadenza": req.data_scadenza,
            "durata_ore": req.durata_ore,
            "larghezza_mm": w_mm,
            "altezza_mm": h_mm,
            "formato_larghezza_mm": w_mm,
            "formato_altezza_mm": h_mm,
            "lotto_originale": lotto_orig,
            "lotto_interno": lotto_interno,
            "numero_pezzo": pezzo_num,
            "numero_pezzi": req.numero_pezzi,
            "pezzo_label": f"Pezzo {pezzo_num} di {req.numero_pezzi}"
        })

    conn.commit()
    conn.close()

    return {
        "success": True,
        "lot_id": lot_id,
        "lotto_interno": lotto_interno,
        "lotto_originale": lotto_orig,
        "numero_pezzi": req.numero_pezzi,
        "labels": labels,
        "label": labels[0] if labels else None,
        "message": f"Lotto {lotto_interno} creato con successo ({req.numero_pezzi} etichette generate)."
    }

@router.get("/labels/history")
def get_labels_history(
    sede_id: int = Query(...),
    limit: int = 100,
    search: Optional[str] = None,
    lotto_interno: Optional[str] = None,
    lotto_originale: Optional[str] = None,
    prodotto: Optional[str] = None,
    data_from: Optional[str] = None,
    data_to: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    verify_sede_permission(user, sede_id, "haccp.labels.view")
    conn = get_db()
    cursor = conn.cursor()

    # Query su haccp_lotti con fallback su etichette legacy (lotto_id IS NULL)
    query = """
        SELECT l.id as lotto_id, l.sede_id, l.lotto_interno, l.lotto_originale,
               l.prodotto, l.preparato_da, l.data_preparazione, l.data_scadenza,
               l.durata_ore, l.numero_pezzi, l.larghezza_mm, l.altezza_mm, l.created_at
        FROM haccp_lotti l
        WHERE l.sede_id = ?
    """
    params: List[Any] = [sede_id]

    if search:
        s = f"%{search.strip().upper()}%"
        query += " AND (UPPER(l.lotto_interno) LIKE ? OR UPPER(l.lotto_originale) LIKE ? OR UPPER(l.prodotto) LIKE ? OR UPPER(l.preparato_da) LIKE ?)"
        params.extend([s, s, s, s])
    if lotto_interno:
        query += " AND UPPER(l.lotto_interno) LIKE ?"
        params.append(f"%{lotto_interno.strip().upper()}%")
    if lotto_originale:
        query += " AND UPPER(l.lotto_originale) LIKE ?"
        params.append(f"%{lotto_originale.strip().upper()}%")
    if prodotto:
        query += " AND UPPER(l.prodotto) LIKE ?"
        params.append(f"%{prodotto.strip().upper()}%")
    if data_from:
        query += " AND l.data_preparazione >= ?"
        params.append(data_from)
    if data_to:
        query += " AND l.data_preparazione <= ?"
        params.append(data_to + " 23:59:59")

    query += " ORDER BY l.id DESC LIMIT ?"
    params.append(limit)
    cursor.execute(query, params)
    lotti = [dict(r) for r in cursor.fetchall()]

    # Recupera i singoli pezzi per ciascun lotto
    for lot in lotti:
        lot["prodotto_nome"] = lot["prodotto"]
        lot["formato_larghezza_mm"] = lot["larghezza_mm"]
        lot["formato_altezza_mm"] = lot["altezza_mm"]
        cursor.execute("""
            SELECT id, numero_pezzo, numero_pezzi, lotto_interno, lotto_originale,
                   prodotto, preparato_da, data_preparazione, data_scadenza
            FROM haccp_etichette
            WHERE lotto_id = ?
            ORDER BY numero_pezzo ASC
        """, (lot["lotto_id"],))
        pieces = []
        for pr in cursor.fetchall():
            pd = dict(pr)
            pd["pezzo_label"] = f"Pezzo {pd['numero_pezzo']} di {pd['numero_pezzi']}"
            pieces.append(pd)
        lot["pezzi"] = pieces

    # Recupera eventuali etichette pre-aggiornamento (compatibilità garantita)
    cursor.execute("""
        SELECT id, sede_id, prodotto, preparato_da, data_preparazione, data_scadenza,
               durata_ore, larghezza_mm, altezza_mm, COALESCE(lotto_originale, 'LEGACY') as lotto_originale,
               COALESCE(lotto_interno, 'PREC-000000') as lotto_interno,
               COALESCE(numero_pezzi, 1) as numero_pezzi, COALESCE(numero_pezzo, 1) as numero_pezzo, created_at
        FROM haccp_etichette
        WHERE sede_id = ? AND (lotto_id IS NULL OR lotto_id = 0)
        ORDER BY id DESC LIMIT 50
    """, (sede_id,))
    legacy_rows = []
    for r in cursor.fetchall():
        d = dict(r)
        d["prodotto_nome"] = d["prodotto"]
        d["formato_larghezza_mm"] = d["larghezza_mm"]
        d["formato_altezza_mm"] = d["altezza_mm"]
        d["lotto_id"] = None
        d["pezzo_label"] = f"Pezzo 1 di 1"
        d["pezzi"] = [{
            "id": d["id"],
            "numero_pezzo": 1,
            "numero_pezzi": 1,
            "lotto_interno": d["lotto_interno"],
            "lotto_originale": d["lotto_originale"],
            "prodotto": d["prodotto"],
            "preparato_da": d["preparato_da"],
            "data_preparazione": d["data_preparazione"],
            "data_scadenza": d["data_scadenza"],
            "pezzo_label": "Pezzo 1 di 1"
        }]
        legacy_rows.append(d)

    conn.close()
    combined = lotti + legacy_rows
    return {"lotti": lotti, "labels": combined, "legacy": legacy_rows, "count": len(combined)}

@router.get("/labels/{label_id}/reprint")
def get_label_for_reprint(label_id: int, user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM haccp_etichette WHERE id = ?", (label_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Etichetta non trovata.")
    lbl = dict(row)
    verify_sede_permission(user, lbl["sede_id"], "haccp.labels.print")
    lbl["prodotto_nome"] = lbl.get("prodotto")
    lbl["formato_larghezza_mm"] = lbl.get("larghezza_mm", 60)
    lbl["formato_altezza_mm"] = lbl.get("altezza_mm", 40)
    lbl["numero_pezzo"] = lbl.get("numero_pezzo", 1)
    lbl["numero_pezzi"] = lbl.get("numero_pezzi", 1)
    lbl["lotto_interno"] = lbl.get("lotto_interno", "N.D.")
    lbl["lotto_originale"] = lbl.get("lotto_originale", "N.D.")
    lbl["pezzo_label"] = f"Pezzo {lbl['numero_pezzo']} di {lbl['numero_pezzi']}"
    return {"label": lbl}

@router.get("/labels/lots/{lot_id}/reprint")
def get_lot_for_reprint(lot_id: int, user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM haccp_lotti WHERE id = ?", (lot_id,))
    lot_row = cursor.fetchone()
    if not lot_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Lotto non trovato.")
    lot = dict(lot_row)
    verify_sede_permission(user, lot["sede_id"], "haccp.labels.print")

    cursor.execute("SELECT * FROM haccp_etichette WHERE lotto_id = ? ORDER BY numero_pezzo ASC", (lot_id,))
    labels = []
    for r in cursor.fetchall():
        d = dict(r)
        d["prodotto_nome"] = d["prodotto"]
        d["formato_larghezza_mm"] = d.get("larghezza_mm", 60)
        d["formato_altezza_mm"] = d.get("altezza_mm", 40)
        d["pezzo_label"] = f"Pezzo {d.get('numero_pezzo', 1)} di {d.get('numero_pezzi', 1)}"
        labels.append(d)

    conn.close()
    lot["prodotto_nome"] = lot["prodotto"]
    return {"lot": lot, "labels": labels, "count": len(labels)}

# ========================================================
# 2. HACCP - TEMPERATURE FRIGORIFERI (MODIFICA NOME MANTENENDO ID)
# ========================================================
class FridgeCreate(BaseModel):
    sede_id: int
    nome: Optional[str] = None
    nome_frigorifero: Optional[str] = None
    temperatura_min: Optional[float] = None
    temperatura_minima: Optional[float] = None
    temperatura_max: Optional[float] = None
    temperatura_massima: Optional[float] = None

class FridgeUpdate(BaseModel):
    nome: Optional[str] = None
    nome_frigorifero: Optional[str] = None
    temperatura_min: Optional[float] = None
    temperatura_max: Optional[float] = None
    is_active: Optional[bool] = None

class TempRecordCreate(BaseModel):
    sede_id: int
    frigorifero_id: int
    data_controllo: Optional[str] = None # YYYY-MM-DD
    ora_controllo: Optional[str] = None # HH:MM
    data_ora: Optional[str] = None
    temperatura: float
    operatore: str
    esito: str # 'CONFORME' o 'NON_CONFORME'
    azione_correttiva: Optional[str] = ""

@router.get("/temperature/fridges")
def list_fridges(
    sede_id: int = Query(...),
    include_inactive: bool = False,
    user: dict = Depends(get_current_user)
):
    if not (user_has_permission(user, sede_id, "haccp.temp.view") or user_has_permission(user, sede_id, "haccp.temp.record")):
        raise HTTPException(status_code=403, detail="Permesso non accordato per visualizzare i frigoriferi.")

    conn = get_db()
    cursor = conn.cursor()
    q = "SELECT * FROM haccp_frigoriferi WHERE sede_id = ?"
    if not include_inactive:
        q += " AND is_active = 1"
    q += " ORDER BY ordine ASC, nome ASC"
    cursor.execute(q, (sede_id,))
    fridges = []
    for r in cursor.fetchall():
        f = dict(r)
        f["nome_frigorifero"] = f["nome"]
        f["temperatura_minima"] = f.get("temperatura_min", 0.0)
        f["temperatura_massima"] = f.get("temperatura_max", 4.0)

        # Ultimo controllo registrato
        cursor.execute("""
            SELECT data_controllo, ora_controllo, temperatura, esito, operatore, azione_correttiva
            FROM haccp_temperature
            WHERE frigorifero_id = ?
            ORDER BY data_controllo DESC, ora_controllo DESC, id DESC
            LIMIT 1
        """, (f["id"],))
        last = cursor.fetchone()
        if last:
            last_dict = dict(last)
            f["ultimo_controllo"] = last_dict
            f["ultima_temperatura"] = last_dict["temperatura"]
            f["ultimo_esito"] = last_dict["esito"]
            f["ultimo_operatore"] = last_dict["operatore"]
            f["ultima_data"] = f"{last_dict['data_controllo']} {last_dict['ora_controllo']}"
        else:
            f["ultimo_controllo"] = None
            f["ultima_temperatura"] = None
            f["ultimo_esito"] = None
            f["ultimo_operatore"] = None
            f["ultima_data"] = None

        fridges.append(f)
    conn.close()
    return {"fridges": fridges, "count": len(fridges)}

@router.post("/temperature/fridges")
def add_fridge(req: FridgeCreate, user: dict = Depends(get_current_user)):
    verify_sede_permission(user, req.sede_id, "haccp.temp.manage")
    f_name = (req.nome_frigorifero or req.nome or "Frigo").strip()
    t_min = req.temperatura_minima if req.temperatura_minima is not None else (req.temperatura_min if req.temperatura_min is not None else 0.0)
    t_max = req.temperatura_massima if req.temperatura_massima is not None else (req.temperatura_max if req.temperatura_max is not None else 4.0)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO haccp_frigoriferi (sede_id, nome, temperatura_min, temperatura_max)
        VALUES (?, ?, ?, ?)
    """, (req.sede_id, f_name, t_min, t_max))
    f_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"success": True, "id": f_id, "message": "Frigorifero aggiunto all'elenco."}

@router.put("/temperature/fridges/{fridge_id}")
def update_fridge(fridge_id: int, req: FridgeUpdate, user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM haccp_frigoriferi WHERE id = ?", (fridge_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Frigorifero non trovato.")
    current = dict(row)
    verify_sede_permission(user, current["sede_id"], "haccp.temp.manage")

    new_name = (req.nome_frigorifero or req.nome or current["nome"]).strip()
    new_tmin = req.temperatura_min if req.temperatura_min is not None else current["temperatura_min"]
    new_tmax = req.temperatura_max if req.temperatura_max is not None else current["temperatura_max"]
    new_active = (1 if req.is_active else 0) if req.is_active is not None else current["is_active"]

    # Mantiene lo stesso identico ID, così tutti i controlli storici restano associati all'attrezzatura
    cursor.execute("""
        UPDATE haccp_frigoriferi
        SET nome = ?, temperatura_min = ?, temperatura_max = ?, is_active = ?
        WHERE id = ?
    """, (new_name, new_tmin, new_tmax, new_active, fridge_id))
    conn.commit()
    conn.close()
    return {"success": True, "id": fridge_id, "fridge_id": fridge_id, "nome": new_name, "message": f"Nome frigorifero aggiornato a '{new_name}' (ID {fridge_id} invariato)."}

@router.post("/temperature/record")
def record_temperature(req: TempRecordCreate, user: dict = Depends(get_current_user)):
    verify_sede_permission(user, req.sede_id, "haccp.temp.record")
    esito_clean = req.esito.upper().strip()
    if esito_clean not in ("CONFORME", "NON_CONFORME"):
        raise HTTPException(status_code=400, detail="Esito non valido. Utilizzare CONFORME o NON_CONFORME.")

    if esito_clean == "NON_CONFORME" and not req.azione_correttiva:
        raise HTTPException(
            status_code=400,
            detail="In caso di Non Conformità (NC) è obbligatorio specificare l'azione correttiva intrapresa."
        )

    now = datetime.now()
    d_ctrl = req.data_controllo or now.strftime("%Y-%m-%d")
    o_ctrl = req.ora_controllo or now.strftime("%H:%M")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO haccp_temperature (
            sede_id, frigorifero_id, data_controllo, ora_controllo,
            temperatura, operatore, esito, azione_correttiva
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        req.sede_id, req.frigorifero_id, d_ctrl, o_ctrl,
        req.temperatura, req.operatore.strip(), esito_clean,
        req.azione_correttiva.strip() if req.azione_correttiva else None
    ))
    r_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {
        "success": True,
        "id": r_id,
        "message": "Registrazione controllo temperatura memorizzata correttamente."
    }

@router.get("/temperature/history")
def get_temperature_history(
    sede_id: int = Query(...),
    frigorifero_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    verify_sede_permission(user, sede_id, "haccp.temp.view")
    conn = get_db()
    cursor = conn.cursor()
    query = """
        SELECT t.*, f.nome as frigorifero_nome, f.nome as nome_frigorifero,
               (t.data_controllo || ' ' || t.ora_controllo) as data_ora
        FROM haccp_temperature t
        JOIN haccp_frigoriferi f ON t.frigorifero_id = f.id
        WHERE t.sede_id = ?
    """
    params: List[Any] = [sede_id]
    if frigorifero_id:
        query += " AND t.frigorifero_id = ?"
        params.append(frigorifero_id)
    if date_from:
        query += " AND t.data_controllo >= ?"
        params.append(date_from)
    if date_to:
        query += " AND t.data_controllo <= ?"
        params.append(date_to)

    query += " ORDER BY t.data_controllo DESC, t.ora_controllo DESC, t.id DESC LIMIT 100"
    cursor.execute(query, params)
    history = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"records": history, "history": history, "count": len(history)}

# ========================================================
# 3. HACCP - CAMBIO OLIO FRIGGITRICI
# ========================================================
class FryerCreate(BaseModel):
    sede_id: int
    nome: Optional[str] = None
    nome_friggitrice: Optional[str] = None

class FryerUpdate(BaseModel):
    nome: Optional[str] = None
    nome_friggitrice: Optional[str] = None

class OilChangeCreate(BaseModel):
    sede_id: int
    friggitrice_id: int
    data_cambio: Optional[str] = None # YYYY-MM-DD
    ora_cambio: Optional[str] = None # HH:MM
    operatore: str
    note: Optional[str] = ""

@router.get("/oil/fryers")
def list_fryers(sede_id: int = Query(...), user: dict = Depends(get_current_user)):
    if not (user_has_permission(user, sede_id, "haccp.oil.view") or user_has_permission(user, sede_id, "haccp.oil.record")):
        raise HTTPException(status_code=403, detail="Permesso non accordato per visualizzare le friggitrici.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM haccp_friggitrici WHERE sede_id = ? AND is_active = 1 ORDER BY id ASC", (sede_id,))
    fryers = []
    now_date = datetime.now().date()
    for r in cursor.fetchall():
        fryer = dict(r)
        fryer["nome_friggitrice"] = fryer["nome"]
        fryer["codice_identificativo"] = fryer["nome"]
        fryer["capacita_litri"] = 20

        # Ultimo cambio olio
        cursor.execute("""
            SELECT id, data_cambio, ora_cambio, operatore, note
            FROM haccp_cambio_olio
            WHERE friggitrice_id = ?
            ORDER BY data_cambio DESC, ora_cambio DESC, id DESC
            LIMIT 1
        """, (fryer["id"],))
        last_change = cursor.fetchone()
        if last_change:
            l_dict = dict(last_change)
            d_obj = datetime.strptime(l_dict["data_cambio"], "%Y-%m-%d").date()
            giorni_fa = (now_date - d_obj).days
            l_dict["giorni_fa"] = giorni_fa
            fryer["ultimo_cambio"] = l_dict
            fryer["ultimo_cambio_data"] = l_dict["data_cambio"]
            fryer["ultimo_cambio_ora"] = l_dict["ora_cambio"]
            fryer["ultimo_operatore"] = l_dict["operatore"]
            fryer["ultime_note"] = l_dict["note"]
            fryer["giorni_da_ultimo_cambio"] = giorni_fa
        else:
            fryer["ultimo_cambio"] = None
            fryer["ultimo_cambio_data"] = None
            fryer["ultimo_cambio_ora"] = None
            fryer["ultimo_operatore"] = None
            fryer["ultime_note"] = None
            fryer["giorni_da_ultimo_cambio"] = None

        fryers.append(fryer)
    conn.close()
    return {"fryers": fryers, "count": len(fryers)}

@router.post("/oil/fryers")
def add_fryer(req: FryerCreate, user: dict = Depends(get_current_user)):
    verify_sede_permission(user, req.sede_id, "haccp.oil.manage")
    f_name = (req.nome_friggitrice or req.nome or "Friggitrice").strip()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO haccp_friggitrici (sede_id, nome, is_active)
        VALUES (?, ?, 1)
    """, (req.sede_id, f_name))
    f_id = cursor.lastrowid
    now = datetime.now()
    cursor.execute("""
        INSERT INTO haccp_cambio_olio (sede_id, friggitrice_id, data_cambio, ora_cambio, operatore, note)
        VALUES (?, ?, ?, ?, ?, 'Attivazione iniziale')
    """, (req.sede_id, f_id, now.strftime("%Y-%m-%d"), now.strftime("%H:%M"), user.get("nome_completo") or user.get("username") or "Admin"))
    conn.commit()
    conn.close()
    return {"success": True, "id": f_id, "message": f"'{f_name}' aggiunta con successo."}

@router.put("/oil/fryers/{fryer_id}")
def rename_fryer(fryer_id: int, req: FryerUpdate, user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT sede_id FROM haccp_friggitrici WHERE id = ?", (fryer_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Friggitrice non trovata.")
    verify_sede_permission(user, row["sede_id"], "haccp.oil.manage")

    new_name = (req.nome_friggitrice or req.nome or "Friggitrice").strip()
    cursor.execute("UPDATE haccp_friggitrici SET nome = ? WHERE id = ?", (new_name, fryer_id))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Nome friggitrice aggiornato."}

@router.delete("/oil/fryers/{fryer_id}")
def delete_fryer(fryer_id: int, user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT sede_id FROM haccp_friggitrici WHERE id = ?", (fryer_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Friggitrice non trovata.")
    verify_sede_permission(user, row["sede_id"], "haccp.oil.manage")
    cursor.execute("UPDATE haccp_friggitrici SET is_active = 0 WHERE id = ?", (fryer_id,))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Friggitrice rimossa con successo."}

@router.post("/oil/record")
def record_oil_change(req: OilChangeCreate, user: dict = Depends(get_current_user)):
    verify_sede_permission(user, req.sede_id, "haccp.oil.record")
    now = datetime.now()
    d_cambio = req.data_cambio or now.strftime("%Y-%m-%d")
    o_cambio = req.ora_cambio or now.strftime("%H:%M")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO haccp_cambio_olio (sede_id, friggitrice_id, data_cambio, ora_cambio, operatore, note)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (req.sede_id, req.friggitrice_id, d_cambio, o_cambio, req.operatore.strip(), req.note.strip() if req.note else None))
    c_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"success": True, "id": c_id, "message": "Cambio olio registrato con successo."}

@router.get("/oil/history")
def get_oil_history(
    sede_id: int = Query(...),
    friggitrice_id: Optional[int] = None,
    user: dict = Depends(get_current_user)
):
    verify_sede_permission(user, sede_id, "haccp.oil.view")
    conn = get_db()
    cursor = conn.cursor()
    query = """
        SELECT o.*, f.nome as friggitrice_nome
        FROM haccp_cambio_olio o
        JOIN haccp_friggitrici f ON o.friggitrice_id = f.id
        WHERE o.sede_id = ?
    """
    params: List[Any] = [sede_id]
    if friggitrice_id:
        query += " AND o.friggitrice_id = ?"
        params.append(friggitrice_id)
    query += " ORDER BY o.data_cambio DESC, o.ora_cambio DESC, o.id DESC LIMIT 50"

    cursor.execute(query, params)
    history = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"records": history, "history": history, "count": len(history)}

# ========================================================
# 4. HACCP - PULIZIA SETTIMANALE CAPPA
# ========================================================
class HoodCleaningCreate(BaseModel):
    sede_id: int
    settimana_riferimento: Optional[str] = None
    data_pulizia: Optional[str] = None # YYYY-MM-DD
    ora_pulizia: Optional[str] = None # HH:MM
    operatore: str
    note: Optional[str] = ""

@router.get("/hood/status")
def get_hood_status(sede_id: int = Query(...), user: dict = Depends(get_current_user)):
    if not (user_has_permission(user, sede_id, "haccp.hood.view") or user_has_permission(user, sede_id, "haccp.hood.record")):
        raise HTTPException(status_code=403, detail="Permesso non accordato per visualizzare la pulizia cappa.")

    year, week, mon_str, sun_str = HaccpService.get_current_iso_week()
    label = HaccpService.format_iso_week_label(year, week, mon_str, sun_str)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM haccp_pulizia_cappa
        WHERE sede_id = ? AND anno = ? AND settimana_numero = ?
        ORDER BY id DESC LIMIT 1
    """, (sede_id, year, week))
    record = cursor.fetchone()
    conn.close()

    is_done = record is not None
    rec_dict = dict(record) if record else None

    return {
        "anno": year,
        "year": year,
        "settimana_numero": week,
        "week_number": week,
        "week_iso": f"{year}-W{week:02d}",
        "data_inizio": mon_str,
        "data_fine": sun_str,
        "etichetta_settimana": label,
        "stato": "ESEGUITA" if is_done else "DA_FARE",
        "status": "ESEGUITA" if is_done else "DA_FARE",
        "dettaglio_registrazione": rec_dict,
        "current_record": rec_dict
    }

@router.post("/hood/record")
def record_hood_cleaning(req: HoodCleaningCreate, user: dict = Depends(get_current_user)):
    verify_sede_permission(user, req.sede_id, "haccp.hood.record")
    now = datetime.now()
    d_pulizia = req.data_pulizia or now.strftime("%Y-%m-%d")
    o_pulizia = req.ora_pulizia or now.strftime("%H:%M")

    p_date = datetime.strptime(d_pulizia, "%Y-%m-%d").date()
    year, week, mon_str, sun_str = HaccpService.get_current_iso_week(p_date)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO haccp_pulizia_cappa (
            sede_id, anno, settimana_numero, data_inizio_settimana,
            data_fine_settimana, data_pulizia, ora_pulizia, operatore, note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        req.sede_id, year, week, mon_str, sun_str,
        d_pulizia, o_pulizia, req.operatore.strip(),
        req.note.strip() if req.note else None
    ))
    c_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"success": True, "id": c_id, "message": f"Pulizia cappa registrata per la Settimana {week}."}

@router.get("/hood/history")
def get_hood_history(sede_id: int = Query(...), user: dict = Depends(get_current_user)):
    verify_sede_permission(user, sede_id, "haccp.hood.view")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT *, (anno || '-W' || CASE WHEN settimana_numero < 10 THEN '0' || settimana_numero ELSE '' || settimana_numero END) as settimana_riferimento
        FROM haccp_pulizia_cappa
        WHERE sede_id = ?
        ORDER BY data_pulizia DESC, id DESC LIMIT 52
    """, (sede_id,))
    rows = []
    for r in cursor.fetchall():
        d = dict(r)
        d["etichetta_settimana"] = HaccpService.format_iso_week_label(
            d["anno"], d["settimana_numero"], d["data_inizio_settimana"], d["data_fine_settimana"]
        )
        rows.append(d)
    conn.close()
    return {"records": rows, "history": rows, "count": len(rows)}

# ========================================================
# 5. HACCP - REGISTRI PULIZIE (MURI, VETRI, MAGAZZINO)
# ========================================================
class CleaningRecordCreate(BaseModel):
    sede_id: int
    tipo_pulizia: str # 'muri' | 'vetri' | 'magazzino'
    data_esecuzione: Optional[str] = None # YYYY-MM-DD
    ora_esecuzione: Optional[str] = None # HH:MM
    operatore: str
    note: Optional[str] = ""

@router.get("/cleaning/status")
def get_cleaning_status(
    sede_id: int = Query(...),
    tipo_pulizia: str = Query(...),
    user: dict = Depends(get_current_user)
):
    perm_code = f"haccp.cleaning.{tipo_pulizia}.view"
    perm_code_alt = f"haccp.cleaning.{tipo_pulizia}.record"
    if not (user_has_permission(user, sede_id, perm_code) or user_has_permission(user, sede_id, perm_code_alt)):
        raise HTTPException(status_code=403, detail=f"Permesso non accordato per visualizzare la pulizia {tipo_pulizia}.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM haccp_pulizie
        WHERE sede_id = ? AND tipo_pulizia = ?
        ORDER BY data_esecuzione DESC, ora_esecuzione DESC, id DESC
        LIMIT 1
    """, (sede_id, tipo_pulizia))
    last_row = cursor.fetchone()
    conn.close()

    today = datetime.now().date()
    if last_row:
        rec = dict(last_row)
        scadenza_date = datetime.strptime(rec["prossima_scadenza"], "%Y-%m-%d").date()
        is_overdue = today > scadenza_date
        days_diff = (today - scadenza_date).days if is_overdue else 0
        return {
            "tipo_pulizia": tipo_pulizia,
            "has_record": True,
            "last_record": rec,
            "prossima_scadenza": rec["prossima_scadenza"],
            "is_overdue": is_overdue,
            "days_overdue": days_diff,
            "status": "SCADUTA" if is_overdue else "IN_REGOLA"
        }
    else:
        return {
            "tipo_pulizia": tipo_pulizia,
            "has_record": False,
            "last_record": None,
            "prossima_scadenza": None,
            "is_overdue": True,
            "days_overdue": 0,
            "status": "MAI_ESEGUITA"
        }

@router.post("/cleaning/record")
def record_cleaning(req: CleaningRecordCreate, user: dict = Depends(get_current_user)):
    tipo = req.tipo_pulizia.lower().strip()
    if tipo not in ("muri", "vetri", "magazzino"):
        raise HTTPException(status_code=400, detail="Tipologia pulizia non valida. Valori ammessi: muri, vetri, magazzino.")

    perm_code = f"haccp.cleaning.{tipo}.record"
    verify_sede_permission(user, req.sede_id, perm_code)

    now = datetime.now()
    d_exec = req.data_esecuzione or now.strftime("%Y-%m-%d")
    o_exec = req.ora_esecuzione or now.strftime("%H:%M")

    exec_date = datetime.strptime(d_exec, "%Y-%m-%d").date()
    prossima_scadenza = HaccpService.get_cleaning_deadline(tipo, exec_date)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO haccp_pulizie (
            sede_id, tipo_pulizia, data_esecuzione, ora_esecuzione,
            operatore, note, prossima_scadenza
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        req.sede_id, tipo, d_exec, o_exec,
        req.operatore.strip(), req.note.strip() if req.note else None,
        prossima_scadenza.strftime("%Y-%m-%d")
    ))
    c_id = cursor.lastrowid
    conn.commit()
    conn.close()

    nomi_it = {"muri": "muri", "vetri": "vetri", "magazzino": "magazzino"}
    return {
        "success": True,
        "id": c_id,
        "prossima_scadenza": prossima_scadenza.strftime("%Y-%m-%d"),
        "message": f"Pulizia {nomi_it.get(tipo, tipo)} registrata con successo (Prossima scadenza: {prossima_scadenza.strftime('%d/%m/%Y')})."
    }

@router.get("/cleaning/history")
def get_cleaning_history(
    sede_id: int = Query(...),
    tipo_pulizia: str = Query(...),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    perm_code = f"haccp.cleaning.{tipo_pulizia}.view"
    verify_sede_permission(user, sede_id, perm_code)

    conn = get_db()
    cursor = conn.cursor()
    query = """
        SELECT * FROM haccp_pulizie
        WHERE sede_id = ? AND tipo_pulizia = ?
    """
    params: List[Any] = [sede_id, tipo_pulizia]
    if date_from:
        query += " AND data_esecuzione >= ?"
        params.append(date_from)
    if date_to:
        query += " AND data_esecuzione <= ?"
        params.append(date_to)

    query += " ORDER BY data_esecuzione DESC, ora_esecuzione DESC, id DESC LIMIT 100"
    cursor.execute(query, params)
    history = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"records": history, "history": history, "count": len(history)}

# ========================================================
# 6. HACCP - MONITORAGGIO INFESTANTI (QUESTIONARIO 8 VOCI A CASCATA)
# ========================================================
VOCI_INFESTANTI_ORDINE = [
    "Peli o piume",
    "Segni di roditori",
    "Insetti vivi",
    "Insetti morti",
    "Roditori",
    "Contenitori danneggiati da animali o insetti",
    "Feci o escrementi",
    "Animali infestanti nelle esche"
]

class PestQuestionAnswer(BaseModel):
    voce: str
    esito: str # 'ASSENZA' o 'PRESENZA'
    zona: Optional[str] = ""
    note: Optional[str] = ""
    azione: Optional[str] = ""

class PestInspectionCreate(BaseModel):
    sede_id: int
    data_controllo: Optional[str] = None # YYYY-MM-DD
    ora_controllo: Optional[str] = None # HH:MM
    operatore: str
    note_generali: Optional[str] = ""
    risposte: List[PestQuestionAnswer]

@router.get("/pests/status")
def get_pests_status(sede_id: int = Query(...), user: dict = Depends(get_current_user)):
    if not (user_has_permission(user, sede_id, "haccp.pests.view") or user_has_permission(user, sede_id, "haccp.pests.record")):
        raise HTTPException(status_code=403, detail="Permesso non accordato per visualizzare il monitoraggio infestanti.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM haccp_infestanti
        WHERE sede_id = ?
        ORDER BY data_controllo DESC, ora_controllo DESC, id DESC
        LIMIT 1
    """, (sede_id,))
    last_row = cursor.fetchone()
    conn.close()

    today = datetime.now().date()
    if last_row:
        rec = dict(last_row)
        rec["risposte"] = json.loads(rec["risposte_json"]) if rec.get("risposte_json") else []
        scadenza_date = datetime.strptime(rec["prossima_scadenza"], "%Y-%m-%d").date()
        is_overdue = today > scadenza_date
        days_diff = (today - scadenza_date).days if is_overdue else 0
        return {
            "has_record": True,
            "last_record": rec,
            "prossima_scadenza": rec["prossima_scadenza"],
            "is_overdue": is_overdue,
            "days_overdue": days_diff,
            "has_presenze": bool(rec["has_presenze"]),
            "status": "SCADUTO" if is_overdue else "IN_REGOLA"
        }
    else:
        return {
            "has_record": False,
            "last_record": None,
            "prossima_scadenza": None,
            "is_overdue": True,
            "days_overdue": 0,
            "has_presenze": False,
            "status": "MAI_ESEGUITO"
        }

@router.post("/pests/record")
def record_pest_inspection(req: PestInspectionCreate, user: dict = Depends(get_current_user)):
    verify_sede_permission(user, req.sede_id, "haccp.pests.record")

    # Verifica che siano state fornite risposte a TUTTE le 8 voci richieste
    if len(req.risposte) != 8:
        raise HTTPException(status_code=400, detail="È obbligatorio rispondere a tutte le 8 voci del controllo infestanti.")

    risposte_pulite = []
    has_presenze = False

    for idx, attesa in enumerate(VOCI_INFESTANTI_ORDINE):
        risp = req.risposte[idx]
        if risp.voce.strip().lower() != attesa.strip().lower():
            # Cerca per nome se ordine scambiato
            trovato = next((r for r in req.risposte if r.voce.strip().lower() == attesa.strip().lower()), None)
            if not trovato:
                raise HTTPException(status_code=400, detail=f"Risposta mancante per la voce '{attesa}'.")
            risp = trovato

        esito = risp.esito.upper().strip()
        if esito not in ("ASSENZA", "PRESENZA"):
            raise HTTPException(status_code=400, detail=f"Esito non valido per '{attesa}': selezionare Assenza o Presenza.")

        if esito == "PRESENZA":
            has_presenze = True

        risposte_pulite.append({
            "numero": idx + 1,
            "voce": attesa,
            "esito": esito,
            "zona": risp.zona.strip() if risp.zona else "",
            "note": risp.note.strip() if risp.note else "",
            "azione": risp.azione.strip() if risp.azione else ""
        })

    now = datetime.now()
    d_ctrl = req.data_controllo or now.strftime("%Y-%m-%d")
    o_ctrl = req.ora_controllo or now.strftime("%H:%M")

    ctrl_date = datetime.strptime(d_ctrl, "%Y-%m-%d").date()
    # Il completamento della verifica aggiorna sempre il promemoria mensile, anche con presenze
    prossima_scadenza = HaccpService.get_pest_deadline(ctrl_date)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO haccp_infestanti (
            sede_id, data_controllo, ora_controllo, operatore,
            has_presenze, risposte_json, note_generali, prossima_scadenza
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        req.sede_id, d_ctrl, o_ctrl, req.operatore.strip(),
        1 if has_presenze else 0, json.dumps(risposte_pulite, ensure_ascii=False),
        req.note_generali.strip() if req.note_generali else None,
        prossima_scadenza.strftime("%Y-%m-%d")
    ))
    i_id = cursor.lastrowid
    conn.commit()
    conn.close()

    stato_msg = "Attenzione: presenze di infestanti rilevate con relative azioni correttive" if has_presenze else "Controllo regolare (nessuna presenza riscontrata)"
    return {
        "success": True,
        "id": i_id,
        "has_presenze": has_presenze,
        "prossima_scadenza": prossima_scadenza.strftime("%Y-%m-%d"),
        "message": f"Verifica infestanti registrata con successo. {stato_msg}."
    }

@router.get("/pests/history")
def get_pests_history(
    sede_id: int = Query(...),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    verify_sede_permission(user, sede_id, "haccp.pests.view")
    conn = get_db()
    cursor = conn.cursor()
    query = """
        SELECT * FROM haccp_infestanti
        WHERE sede_id = ?
    """
    params: List[Any] = [sede_id]
    if date_from:
        query += " AND data_controllo >= ?"
        params.append(date_from)
    if date_to:
        query += " AND data_controllo <= ?"
        params.append(date_to)

    query += " ORDER BY data_controllo DESC, ora_controllo DESC, id DESC LIMIT 50"
    cursor.execute(query, params)
    rows = []
    for r in cursor.fetchall():
        d = dict(r)
        d["has_presenze"] = bool(d["has_presenze"])
        d["risposte"] = json.loads(d["risposte_json"]) if d.get("risposte_json") else []
        rows.append(d)
    conn.close()
    return {"records": rows, "history": rows, "count": len(rows)}

@router.get("/pests/{inspection_id}")
def get_pest_inspection_detail(inspection_id: int, user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM haccp_infestanti WHERE id = ?", (inspection_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Scheda monitoraggio non trovata.")
    d = dict(row)
    verify_sede_permission(user, d["sede_id"], "haccp.pests.view")
    d["has_presenze"] = bool(d["has_presenze"])
    d["risposte"] = json.loads(d["risposte_json"]) if d.get("risposte_json") else []
    return {"inspection": d}

# ========================================================
# 7. BANNER DEGLI AVVISI CONTROLLI SCADUTI
# ========================================================
@router.get("/alerts")
def get_haccp_alerts(
    sede_id: int = Query(...),
    user: dict = Depends(get_current_user)
):
    """
    Restituisce tutti gli avvisi di controlli o pulizie scadute per il locale specificato,
    filtrando esclusivamente le attività per cui l'account possiede il permesso di visualizzazione.
    """
    if not user.get("is_admin") and sede_id not in user.get("authorized_sedi", []):
        raise HTTPException(status_code=403, detail="Non sei autorizzato per questo locale.")

    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now()
    today = now.date()
    alerts = []

    # 1. Pulizia Cappa (scaduta dopo più di 7 giorni)
    if user_has_permission(user, sede_id, "haccp.hood.view") or user_has_permission(user, sede_id, "haccp.hood.record"):
        cursor.execute("""
            SELECT data_pulizia, ora_pulizia, operatore
            FROM haccp_pulizia_cappa
            WHERE sede_id = ?
            ORDER BY data_pulizia DESC, ora_pulizia DESC, id DESC
            LIMIT 1
        """, (sede_id,))
        hood_row = cursor.fetchone()
        if not hood_row:
            alerts.append({
                "id": "alert-hood-never",
                "tipo": "hood",
                "tab": "hood",
                "titolo": "Pulizia cappa di aspirazione",
                "nome_attrezzatura": "Cappa aspirazione fumi",
                "is_first_time": True,
                "ultima_registrazione": None,
                "scadenza": None,
                "overdue_text": "Prima registrazione da effettuare",
                "messaggio": "Pulizia cappa: Prima registrazione da effettuare"
            })
        else:
            last_dt_str = f"{hood_row['data_pulizia']} {hood_row['ora_pulizia'] or '00:00'}"
            try:
                last_dt = datetime.strptime(last_dt_str, "%Y-%m-%d %H:%M")
            except ValueError:
                last_dt = datetime.strptime(last_dt_str[:16], "%Y-%m-%d %H:%M")
            
            deadline = last_dt + timedelta(days=7)
            if now > deadline:
                delta_scad = now - deadline
                txt_scad = HaccpService.format_time_elapsed(delta_scad)
                alerts.append({
                    "id": "alert-hood-overdue",
                    "tipo": "hood",
                    "tab": "hood",
                    "titolo": "Pulizia cappa di aspirazione",
                    "nome_attrezzatura": "Cappa aspirazione fumi",
                    "is_first_time": False,
                    "ultima_registrazione": last_dt_str,
                    "scadenza": deadline.strftime("%Y-%m-%d %H:%M"),
                    "overdue_text": f"Scaduta da {txt_scad}",
                    "messaggio": f"Pulizia cappa: scaduta da {txt_scad} (Ultima: {last_dt.strftime('%d/%m/%Y %H:%M')})"
                })

    # 2. Controllo Frigoriferi (scaduto dopo più di 24 ore, per ogni frigorifero attivo)
    if user_has_permission(user, sede_id, "haccp.temp.view") or user_has_permission(user, sede_id, "haccp.temp.record"):
        cursor.execute("SELECT id, nome FROM haccp_frigoriferi WHERE sede_id = ? AND is_active = 1", (sede_id,))
        for fr in cursor.fetchall():
            cursor.execute("""
                SELECT data_controllo, ora_controllo, temperatura, esito
                FROM haccp_temperature
                WHERE frigorifero_id = ?
                ORDER BY data_controllo DESC, ora_controllo DESC, id DESC
                LIMIT 1
            """, (fr["id"],))
            t_row = cursor.fetchone()
            if not t_row:
                alerts.append({
                    "id": f"alert-fridge-{fr['id']}-never",
                    "tipo": "temp",
                    "tab": "temp",
                    "titolo": "Controllo temperatura frigorifero",
                    "target_id": fr["id"],
                    "nome_attrezzatura": fr["nome"],
                    "is_first_time": True,
                    "ultima_registrazione": None,
                    "scadenza": None,
                    "overdue_text": "Prima registrazione da effettuare",
                    "messaggio": f"Frigorifero '{fr['nome']}': Prima registrazione da effettuare"
                })
            else:
                last_dt_str = f"{t_row['data_controllo']} {t_row['ora_controllo']}"
                try:
                    last_dt = datetime.strptime(last_dt_str, "%Y-%m-%d %H:%M")
                except ValueError:
                    last_dt = datetime.strptime(last_dt_str[:16], "%Y-%m-%d %H:%M")
                
                deadline = last_dt + timedelta(hours=24)
                if now > deadline:
                    delta_scad = now - deadline
                    txt_scad = HaccpService.format_time_elapsed(delta_scad)
                    alerts.append({
                        "id": f"alert-fridge-{fr['id']}-overdue",
                        "tipo": "temp",
                        "tab": "temp",
                        "titolo": "Controllo temperatura frigorifero",
                        "target_id": fr["id"],
                        "nome_attrezzatura": fr["nome"],
                        "is_first_time": False,
                        "ultima_registrazione": last_dt_str,
                        "scadenza": deadline.strftime("%Y-%m-%d %H:%M"),
                        "overdue_text": f"Scaduto da {txt_scad}",
                        "messaggio": f"Frigorifero '{fr['nome']}': controllo temperatura scaduto da {txt_scad} (Ultimo: {last_dt.strftime('%d/%m %H:%M')})"
                    })

    # 3. Cambio Olio Friggitrici (scaduto dopo più di 7 giorni, per ogni friggitrice)
    if user_has_permission(user, sede_id, "haccp.oil.view") or user_has_permission(user, sede_id, "haccp.oil.record"):
        cursor.execute("SELECT id, nome FROM haccp_friggitrici WHERE sede_id = ? AND is_active = 1", (sede_id,))
        for fg in cursor.fetchall():
            cursor.execute("""
                SELECT data_cambio, ora_cambio
                FROM haccp_cambio_olio
                WHERE friggitrice_id = ?
                ORDER BY data_cambio DESC, ora_cambio DESC, id DESC
                LIMIT 1
            """, (fg["id"],))
            o_row = cursor.fetchone()
            if not o_row:
                alerts.append({
                    "id": f"alert-fryer-{fg['id']}-never",
                    "tipo": "oil",
                    "tab": "oil",
                    "titolo": "Cambio olio friggitrice",
                    "target_id": fg["id"],
                    "nome_attrezzatura": fg["nome"],
                    "is_first_time": True,
                    "ultima_registrazione": None,
                    "scadenza": None,
                    "overdue_text": "Prima registrazione da effettuare",
                    "messaggio": f"Friggitrice '{fg['nome']}': Prima registrazione da effettuare"
                })
            else:
                last_dt_str = f"{o_row['data_cambio']} {o_row['ora_cambio'] or '00:00'}"
                try:
                    last_dt = datetime.strptime(last_dt_str, "%Y-%m-%d %H:%M")
                except ValueError:
                    last_dt = datetime.strptime(last_dt_str[:16], "%Y-%m-%d %H:%M")
                
                deadline = last_dt + timedelta(days=7)
                if now > deadline:
                    delta_scad = now - deadline
                    txt_scad = HaccpService.format_time_elapsed(delta_scad)
                    alerts.append({
                        "id": f"alert-fryer-{fg['id']}-overdue",
                        "tipo": "oil",
                        "tab": "oil",
                        "titolo": "Cambio olio friggitrice",
                        "target_id": fg["id"],
                        "nome_attrezzatura": fg["nome"],
                        "is_first_time": False,
                        "ultima_registrazione": last_dt_str,
                        "scadenza": deadline.strftime("%Y-%m-%d %H:%M"),
                        "overdue_text": f"Scaduto da {txt_scad}",
                        "messaggio": f"Friggitrice '{fg['nome']}': cambio olio scaduto da {txt_scad} (Ultimo: {last_dt.strftime('%d/%m/%Y')})"
                    })

    # 4. Pulizie Generali (Muri: 1 mese, Vetri: 1 mese, Magazzino: 7 giorni)
    cleanings_cfg = [
        ("muri", "Pulizia muri", "cleaning_walls", "haccp.cleaning.walls"),
        ("vetri", "Pulizia vetri", "cleaning_windows", "haccp.cleaning.windows"),
        ("magazzino", "Pulizia magazzino", "cleaning_warehouse", "haccp.cleaning.warehouse"),
    ]
    for tipo_p, label_p, tab_target, perm_base in cleanings_cfg:
        if user_has_permission(user, sede_id, f"{perm_base}.view") or user_has_permission(user, sede_id, f"{perm_base}.record"):
            cursor.execute("""
                SELECT data_esecuzione, ora_esecuzione, prossima_scadenza
                FROM haccp_pulizie
                WHERE sede_id = ? AND tipo_pulizia = ?
                ORDER BY data_esecuzione DESC, ora_esecuzione DESC, id DESC
                LIMIT 1
            """, (sede_id, tipo_p))
            p_row = cursor.fetchone()
            if not p_row:
                alerts.append({
                    "id": f"alert-cleaning-{tipo_p}-never",
                    "tipo": tab_target,
                    "tab": tab_target,
                    "titolo": label_p,
                    "nome_attrezzatura": label_p,
                    "is_first_time": True,
                    "ultima_registrazione": None,
                    "scadenza": None,
                    "overdue_text": "Prima registrazione da effettuare",
                    "messaggio": f"{label_p}: Prima registrazione da effettuare"
                })
            else:
                last_dt_str = f"{p_row['data_esecuzione']} {p_row['ora_esecuzione'] or '00:00'}"
                try:
                    last_dt = datetime.strptime(last_dt_str, "%Y-%m-%d %H:%M")
                except ValueError:
                    last_dt = datetime.strptime(last_dt_str[:16], "%Y-%m-%d %H:%M")

                if tipo_p in ("muri", "vetri"):
                    deadline_dt = HaccpService.add_calendar_month(last_dt)
                else:
                    deadline_dt = last_dt + timedelta(days=7)

                if now > deadline_dt:
                    delta_scad = now - deadline_dt
                    txt_scad = HaccpService.format_time_elapsed(delta_scad)
                    alerts.append({
                        "id": f"alert-cleaning-{tipo_p}-overdue",
                        "tipo": tab_target,
                        "tab": tab_target,
                        "titolo": label_p,
                        "nome_attrezzatura": label_p,
                        "is_first_time": False,
                        "ultima_registrazione": last_dt_str,
                        "scadenza": deadline_dt.strftime("%Y-%m-%d %H:%M"),
                        "overdue_text": f"Scaduta da {txt_scad}",
                        "messaggio": f"{label_p}: scaduta da {txt_scad} (Ultima: {last_dt.strftime('%d/%m/%Y %H:%M')})"
                    })

    # 5. Monitoraggio Infestanti (scaduto dopo 1 mese di calendario)
    if user_has_permission(user, sede_id, "haccp.pests.view") or user_has_permission(user, sede_id, "haccp.pests.record"):
        cursor.execute("""
            SELECT data_controllo, ora_controllo, prossima_scadenza, has_presenze
            FROM haccp_infestanti
            WHERE sede_id = ?
            ORDER BY data_controllo DESC, ora_controllo DESC, id DESC
            LIMIT 1
        """, (sede_id,))
        pest_row = cursor.fetchone()
        if not pest_row:
            alerts.append({
                "id": "alert-pests-never",
                "tipo": "pests",
                "tab": "pests",
                "titolo": "Monitoraggio infestanti",
                "nome_attrezzatura": "Monitoraggio infestanti",
                "is_first_time": True,
                "ultima_registrazione": None,
                "scadenza": None,
                "overdue_text": "Prima registrazione da effettuare",
                "messaggio": "Monitoraggio infestanti: Prima registrazione da effettuare"
            })
        else:
            last_dt_str = f"{pest_row['data_controllo']} {pest_row['ora_controllo'] or '00:00'}"
            try:
                last_dt = datetime.strptime(last_dt_str, "%Y-%m-%d %H:%M")
            except ValueError:
                last_dt = datetime.strptime(last_dt_str[:16], "%Y-%m-%d %H:%M")

            deadline_dt = HaccpService.add_calendar_month(last_dt)
            if now > deadline_dt:
                delta_scad = now - deadline_dt
                txt_scad = HaccpService.format_time_elapsed(delta_scad)
                alerts.append({
                    "id": "alert-pests-overdue",
                    "tipo": "pests",
                    "tab": "pests",
                    "titolo": "Monitoraggio infestanti",
                    "nome_attrezzatura": "Monitoraggio infestanti",
                    "is_first_time": False,
                    "ultima_registrazione": last_dt_str,
                    "scadenza": deadline_dt.strftime("%Y-%m-%d %H:%M"),
                    "overdue_text": f"Scaduto da {txt_scad}",
                    "messaggio": f"Monitoraggio infestanti: scaduto da {txt_scad} (Ultimo: {last_dt.strftime('%d/%m/%Y %H:%M')})"
                })

    conn.close()
    return {"alerts": alerts, "count": len(alerts), "sede_id": sede_id}


# ========================================================
# 8. RESET RAPIDO CONTROLLI SCADUTI HACCP (SOLO ADMIN)
# ========================================================
class AdminResetAlertsRequest(BaseModel):
    sede_id: int
    both_sedi: Optional[bool] = False

@router.post("/admin-reset-alerts")
def admin_reset_alerts(
    req: AdminResetAlertsRequest,
    user: dict = Depends(get_current_user)
):
    """
    Funzionalità riservata esclusivamente all'amministratore (is_admin == 1).
    Inserisce registrazioni valide, conformi e aggiornate alla data/ora corrente
    per tutte le attività HACCP soggette ad avviso di scadenza per il locale indicato
    (o per entrambi i locali se richiesto):
    - Pulizia cappa
    - Controllo temperatura per tutti i frigoriferi attivi (valore target conforme)
    - Cambio olio per tutte le friggitrici attive
    - Pulizie generali (muri, vetri, magazzino) con relative scadenze corrette
    - Scheda monitoraggio infestanti (tutte le 8 voci conformi/assenti)
    In questo modo tutti i banner di avviso di scadenza vengono azzerati e tutte
    le sezioni risultano 'IN REGOLA' ed 'ESEGUITE'.
    """
    if not user.get("is_admin"):
        raise HTTPException(
            status_code=403,
            detail="Operazione riservata esclusivamente all'amministratore."
        )

    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    now_time_str = now.strftime("%H:%M")
    operatore_nome = user.get("nome_completo") or user.get("username") or "Amministratore"
    operatore_str = f"Admin ({operatore_nome})"

    sedi_ids = [req.sede_id]
    if req.both_sedi:
        cursor.execute("SELECT id FROM sedi")
        sedi_ids = [r["id"] for r in cursor.fetchall()]

    for s_id in sedi_ids:
        # 1. Pulizia Cappa
        year, week, mon_str, sun_str = HaccpService.get_current_iso_week(now.date())
        cursor.execute("""
            INSERT INTO haccp_pulizia_cappa (
                sede_id, anno, settimana_numero, data_inizio_settimana,
                data_fine_settimana, data_pulizia, ora_pulizia, operatore, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Reset rapido controlli eseguito da Amministratore')
        """, (s_id, year, week, mon_str, sun_str, today_str, now_time_str, operatore_str))

        # 2. Controllo Frigoriferi (tutti i frigoriferi attivi per questa sede)
        cursor.execute("""
            SELECT id, nome, temperatura_min, temperatura_max
            FROM haccp_frigoriferi
            WHERE sede_id = ? AND is_active = 1
        """, (s_id,))
        frigos = cursor.fetchall()
        for fr in frigos:
            t_min = fr["temperatura_min"] if fr["temperatura_min"] is not None else 0.0
            t_max = fr["temperatura_max"] if fr["temperatura_max"] is not None else 4.0
            t_val = round((t_min + t_max) / 2.0, 1)
            cursor.execute("""
                INSERT INTO haccp_temperature (sede_id, frigorifero_id, data_controllo, ora_controllo, temperatura, operatore, esito, azione_correttiva)
                VALUES (?, ?, ?, ?, ?, ?, 'CONFORME', NULL)
            """, (s_id, fr["id"], today_str, now_time_str, t_val, operatore_str))

        # 3. Cambio Olio Friggitrici (tutte le friggitrici attive per questa sede)
        cursor.execute("""
            SELECT id, nome
            FROM haccp_friggitrici
            WHERE sede_id = ? AND is_active = 1
        """, (s_id,))
        fryers = cursor.fetchall()
        for fg in fryers:
            cursor.execute("""
                INSERT INTO haccp_cambio_olio (sede_id, friggitrice_id, data_cambio, ora_cambio, operatore, note)
                VALUES (?, ?, ?, ?, ?, 'Reset rapido controlli eseguito da Amministratore')
            """, (s_id, fg["id"], today_str, now_time_str, operatore_str))

        # 4. Pulizie Generali (muri, vetri, magazzino)
        for tipo_p in ["muri", "vetri", "magazzino"]:
            if tipo_p in ("muri", "vetri"):
                next_scad = HaccpService.add_calendar_month(now).date().isoformat()
            else:
                next_scad = (now + timedelta(days=7)).date().isoformat()
            cursor.execute("""
                INSERT INTO haccp_pulizie (sede_id, tipo_pulizia, data_esecuzione, ora_esecuzione, operatore, note, prossima_scadenza)
                VALUES (?, ?, ?, ?, ?, 'Reset rapido controlli eseguito da Amministratore', ?)
            """, (s_id, tipo_p, today_str, now_time_str, operatore_str, next_scad))

        # 5. Monitoraggio Infestanti
        voci_standard = [
            {"id": 1, "nome": "Stato visivo locali e pertinenze", "esito": "CONFORME"},
            {"id": 2, "nome": "Presenza roditori (escrementi, tracce)", "esito": "ASSENTE"},
            {"id": 3, "nome": "Presenza insetti striscianti (blatte, formiche)", "esito": "ASSENTE"},
            {"id": 4, "nome": "Presenza insetti volanti (mosche, moscerini)", "esito": "ASSENTE"},
            {"id": 5, "nome": "Integrità zanzariere e barriere antintrusione", "esito": "CONFORME"},
            {"id": 6, "nome": "Controllo trappole a luce UV / piastre collanti", "esito": "CONFORME"},
            {"id": 7, "nome": "Controllo erogatori esche esterne (se presenti)", "esito": "CONFORME"},
            {"id": 8, "nome": "Chiusura ermetica contenitori rifiuti e farine", "esito": "CONFORME"}
        ]
        prossima_scad_pests = HaccpService.add_calendar_month(now).date().isoformat()
        cursor.execute("""
            INSERT INTO haccp_infestanti (sede_id, data_controllo, ora_controllo, operatore, has_presenze, risposte_json, note_generali, prossima_scadenza)
            VALUES (?, ?, ?, ?, 0, ?, 'Reset rapido controlli eseguito da Amministratore - Regolare', ?)
        """, (s_id, today_str, now_time_str, operatore_str, json.dumps(voci_standard), prossima_scad_pests))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Tutti i controlli e le pulizie sono stati registrati come eseguiti e conformi.",
        "sedi_aggiornate": sedi_ids
    }
