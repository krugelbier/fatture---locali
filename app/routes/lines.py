# Lines Routes with Granular Permission Checks
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel
from app.database import get_db
from app.routes.auth import get_current_user
from app.services.auth_service import user_has_permission

router = APIRouter(prefix="/api/lines", tags=["Righe Fattura"])

class LineAssignRequest(BaseModel):
    sede_id: int

class BatchLineAssignRequest(BaseModel):
    line_ids: List[int]
    sede_id: int

class MapProductRequest(BaseModel):
    prodotto_id: Optional[int] = None
    nuovo_prodotto_nome: Optional[str] = None
    categoria: Optional[str] = None
    unita_base: Optional[str] = None
    crea_regola_alias: bool = True
    fattore_conversione: float = 1.0
    unita_confezione: Optional[str] = None
    pattern_ricerca: Optional[str] = None
    specifico_fornitore: bool = True

@router.post("/{line_id}/assign-venue")
def assign_single_line_venue(line_id: int, req: LineAssignRequest, user: dict = Depends(get_current_user)):
    if not user_has_permission(user, req.sede_id, "fatture.assign"):
        raise HTTPException(status_code=403, detail="Permesso non accordato per assegnare righe a questa sede.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome FROM sedi WHERE id = ?", (req.sede_id,))
    sede = cursor.fetchone()
    if not sede:
        conn.close()
        raise HTTPException(status_code=404, detail="Sede non trovata")

    cursor.execute("""
    UPDATE righe_fattura 
    SET sede_id = ?, metodo_assegnazione = 'MANUALE'
    WHERE id = ?
    """, (req.sede_id, line_id))

    cursor.execute("SELECT documento_id FROM righe_fattura WHERE id = ?", (line_id,))
    row = cursor.fetchone()
    if row:
        doc_id = row["documento_id"]
        _update_document_status(cursor, doc_id)

    conn.commit()
    conn.close()
    return {"success": True, "message": f"Riga assegnata a {sede['nome']}."}

@router.post("/batch-assign-venue")
def batch_assign_lines(req: BatchLineAssignRequest, user: dict = Depends(get_current_user)):
    if not user_has_permission(user, req.sede_id, "fatture.assign"):
        raise HTTPException(status_code=403, detail="Permesso non accordato per assegnare righe a questa sede.")

    if not req.line_ids:
        raise HTTPException(status_code=400, detail="Nessuna riga fornita")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome FROM sedi WHERE id = ?", (req.sede_id,))
    sede = cursor.fetchone()
    if not sede:
        conn.close()
        raise HTTPException(status_code=404, detail="Sede non trovata")

    placeholders = ",".join(["?"] * len(req.line_ids))
    cursor.execute(f"""
    UPDATE righe_fattura 
    SET sede_id = ?, metodo_assegnazione = 'MANUALE'
    WHERE id IN ({placeholders})
    """, [req.sede_id] + req.line_ids)

    cursor.execute(f"SELECT DISTINCT documento_id FROM righe_fattura WHERE id IN ({placeholders})", req.line_ids)
    doc_ids = [r["documento_id"] for r in cursor.fetchall()]
    for d_id in doc_ids:
        _update_document_status(cursor, d_id)

    conn.commit()
    conn.close()
    return {"success": True, "message": f"{len(req.line_ids)} righe assegnate con successo a {sede['nome']}."}

@router.post("/{line_id}/map-product")
def map_line_product(line_id: int, req: MapProductRequest, user: dict = Depends(get_current_user)):
    if not user_has_permission(user, None, "fatture.products"):
        raise HTTPException(status_code=403, detail="Permesso non accordato per gestire le associazioni tra prodotti.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT r.*, d.cedente_piva, d.cedente_denominazione 
    FROM righe_fattura r
    JOIN documenti d ON r.documento_id = d.id
    WHERE r.id = ?
    """, (line_id,))
    riga = cursor.fetchone()
    if not riga:
        conn.close()
        raise HTTPException(status_code=404, detail="Riga non trovata")

    prodotto_id = req.prodotto_id
    if not prodotto_id and req.nuovo_prodotto_nome:
        cursor.execute("""
        INSERT INTO prodotti (nome_canonico, categoria, unita_base, descrizione)
        VALUES (?, ?, ?, ?)
        """, (req.nuovo_prodotto_nome.strip(), req.categoria or "Altro", req.unita_base or "PZ", "Creato da mappatura fattura"))
        prodotto_id = cursor.lastrowid

    if not prodotto_id:
        conn.close()
        raise HTTPException(status_code=400, detail="Specificare un prodotto esistente o il nome per uno nuovo")

    cursor.execute("UPDATE righe_fattura SET prodotto_id = ? WHERE id = ?", (prodotto_id, line_id))

    if req.crea_regola_alias:
        pattern = req.pattern_ricerca or riga["descrizione"]
        piva_forn = riga["cedente_piva"] if req.specifico_fornitore else None
        den_forn = riga["cedente_denominazione"] if req.specifico_fornitore else None

        cursor.execute("""
        INSERT INTO mappature_prodotto (
            prodotto_id, fornitore_piva, fornitore_denominazione,
            pattern_testo, tipo_match, fattore_conversione, unita_confezione, note
        ) VALUES (?, ?, ?, ?, 'CONTIENE', ?, ?, ?)
        """, (
            prodotto_id, piva_forn, den_forn,
            pattern, req.fattore_conversione, req.unita_confezione, "Regola creata da interfaccia utente"
        ))

        cursor.execute("""
        UPDATE righe_fattura
        SET prodotto_id = ?
        WHERE (prodotto_id IS NULL OR prodotto_id = 0)
        AND UPPER(descrizione) LIKE ?
        """, (prodotto_id, f"%{pattern.upper()}%"))

    conn.commit()
    conn.close()
    return {"success": True, "message": "Prodotto associato e regola di conversione memorizzata con successo."}

def _update_document_status(cursor, doc_id: int):
    cursor.execute("""
    SELECT 
        COUNT(*) as total_lines,
        COUNT(CASE WHEN sede_id IS NOT NULL THEN 1 END) as assigned_lines,
        COUNT(DISTINCT sede_id) as distinct_sedi
    FROM righe_fattura
    WHERE documento_id = ?
    """, (doc_id,))
    stats = cursor.fetchone()

    total = stats["total_lines"]
    assigned = stats["assigned_lines"]
    distinct_sedi = stats["distinct_sedi"]

    if assigned == 0:
        new_stato = "DA_ASSEGNARE"
        doc_sede = None
    elif assigned == total:
        new_stato = "COMPLETA"
        if distinct_sedi == 1:
            cursor.execute("SELECT sede_id FROM righe_fattura WHERE documento_id = ? LIMIT 1", (doc_id,))
            doc_sede = cursor.fetchone()["sede_id"]
        else:
            doc_sede = None
    else:
        new_stato = "PARZIALE"
        doc_sede = None

    cursor.execute("""
    UPDATE documenti 
    SET stato_assegnazione = ?, sede_id = ?
    WHERE id = ?
    """, (new_stato, doc_sede, doc_id))
