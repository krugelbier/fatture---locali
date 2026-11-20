# Unassigned View Routes with Permission Checks
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel
from app.database import get_db
from app.routes.lines import _update_document_status
from app.routes.auth import get_current_user
from app.services.auth_service import user_has_permission

router = APIRouter(prefix="/api/unassigned", tags=["Da Assegnare"])

class QuickAssignInvoiceRequest(BaseModel):
    documento_id: int
    sede_id: int

class QuickAssignLinesRequest(BaseModel):
    riga_ids: List[int]
    sede_id: int

@router.get("/summary")
def get_unassigned_summary(user: dict = Depends(get_current_user)):
    if not (user_has_permission(user, None, "fatture.view") or user_has_permission(user, None, "fatture.assign")):
        raise HTTPException(status_code=403, detail="Permesso non accordato.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT 
        COUNT(CASE WHEN stato_assegnazione = 'DA_ASSEGNARE' THEN 1 END) as fatture_da_assegnare,
        COUNT(CASE WHEN stato_assegnazione = 'PARZIALE' THEN 1 END) as fatture_parziali
    FROM documenti
    """)
    doc_stats = dict(cursor.fetchone())

    cursor.execute("""
    SELECT 
        COUNT(*) as righe_da_assegnare,
        COALESCE(SUM(r.prezzo_totale_netto), 0) as importo_netto_da_assegnare
    FROM righe_fattura r
    JOIN documenti d ON r.documento_id = d.id
    WHERE r.sede_id IS NULL
    """)
    line_stats = dict(cursor.fetchone())

    cursor.execute("SELECT COUNT(*) as non_mappate FROM righe_fattura WHERE prodotto_id IS NULL")
    prod_stats = dict(cursor.fetchone())

    conn.close()
    return {
        "fatture_da_assegnare": doc_stats["fatture_da_assegnare"] or 0,
        "fatture_parziali": doc_stats["fatture_parziali"] or 0,
        "righe_da_assegnare": line_stats["righe_da_assegnare"] or 0,
        "importo_da_assegnare": round(line_stats["importo_netto_da_assegnare"] or 0.0, 2),
        "righe_non_mappate": prod_stats["non_mappate"] or 0
    }

@router.get("/invoices")
def get_unassigned_invoices(user: dict = Depends(get_current_user)):
    if not user_has_permission(user, None, "fatture.view"):
        raise HTTPException(status_code=403, detail="Permesso non accordato.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT 
        d.id, d.numero_documento, d.data_documento, d.tipo_documento,
        d.cedente_denominazione, d.cedente_piva, d.importo_totale, d.imponibile_totale,
        d.stato_assegnazione, d.metodo_assegnazione, d.indirizzo_resa_estratto,
        d.ddt_elenco_json,
        (SELECT COUNT(*) FROM righe_fattura r WHERE r.documento_id = d.id) as tot_righe,
        (SELECT COUNT(*) FROM righe_fattura r WHERE r.documento_id = d.id AND r.sede_id IS NULL) as righe_sospese,
        (SELECT COUNT(*) FROM righe_fattura r WHERE r.documento_id = d.id AND r.sede_id IS NOT NULL) as righe_assegnate
    FROM documenti d
    WHERE d.stato_assegnazione IN ('DA_ASSEGNARE', 'PARZIALE')
    ORDER BY d.data_documento DESC, d.numero_documento DESC
    """)
    invoices = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"invoices": invoices, "count": len(invoices)}

@router.get("/lines")
def get_unassigned_lines(documento_id: Optional[int] = None, user: dict = Depends(get_current_user)):
    if not user_has_permission(user, None, "fatture.view"):
        raise HTTPException(status_code=403, detail="Permesso non accordato.")

    conn = get_db()
    cursor = conn.cursor()
    query = """
    SELECT 
        r.id as riga_id, r.documento_id, r.numero_linea, r.codice_articolo,
        r.descrizione, r.quantita, r.unita_misura, r.prezzo_unitario_netto,
        r.prezzo_totale_netto, r.riferimento_ddt_numero, r.riferimento_ddt_data,
        d.numero_documento, d.data_documento, d.cedente_denominazione,
        d.indirizzo_resa_estratto,
        p.id as prodotto_id, p.nome_canonico as prodotto_nome
    FROM righe_fattura r
    JOIN documenti d ON r.documento_id = d.id
    LEFT JOIN prodotti p ON r.prodotto_id = p.id
    WHERE r.sede_id IS NULL
    """
    params = []
    if documento_id:
        query += " AND r.documento_id = ?"
        params.append(documento_id)

    query += " ORDER BY d.data_documento DESC, r.documento_id ASC, r.numero_linea ASC"
    cursor.execute(query, params)
    lines = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"lines": lines, "count": len(lines)}

@router.post("/quick-assign-invoice")
def quick_assign_invoice(req: QuickAssignInvoiceRequest, user: dict = Depends(get_current_user)):
    if not user_has_permission(user, req.sede_id, "fatture.assign"):
        raise HTTPException(status_code=403, detail="Permesso non accordato per assegnare fatture a questa sede.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome FROM sedi WHERE id = ?", (req.sede_id,))
    sede = cursor.fetchone()
    if not sede:
        conn.close()
        raise HTTPException(status_code=404, detail="Sede non trovata")

    cursor.execute("""
    UPDATE documenti 
    SET sede_id = ?, stato_assegnazione = 'COMPLETA', metodo_assegnazione = 'MANUALE'
    WHERE id = ?
    """, (req.sede_id, req.documento_id))

    cursor.execute("""
    UPDATE righe_fattura 
    SET sede_id = ?, metodo_assegnazione = 'MANUALE'
    WHERE documento_id = ?
    """, (req.sede_id, req.documento_id))

    conn.commit()
    conn.close()
    return {"success": True, "message": f"Fattura assegnata integralmente a {sede['nome']}."}

@router.post("/quick-assign-lines")
def quick_assign_lines(req: QuickAssignLinesRequest, user: dict = Depends(get_current_user)):
    if not user_has_permission(user, req.sede_id, "fatture.assign"):
        raise HTTPException(status_code=403, detail="Permesso non accordato per assegnare righe a questa sede.")

    if not req.riga_ids:
        raise HTTPException(status_code=400, detail="Nessuna riga selezionata")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome FROM sedi WHERE id = ?", (req.sede_id,))
    sede = cursor.fetchone()
    if not sede:
        conn.close()
        raise HTTPException(status_code=404, detail="Sede non trovata")

    placeholders = ",".join(["?"] * len(req.riga_ids))
    cursor.execute(f"""
    UPDATE righe_fattura 
    SET sede_id = ?, metodo_assegnazione = 'MANUALE'
    WHERE id IN ({placeholders})
    """, [req.sede_id] + req.riga_ids)

    cursor.execute(f"SELECT DISTINCT documento_id FROM righe_fattura WHERE id IN ({placeholders})", req.riga_ids)
    doc_ids = [r["documento_id"] for r in cursor.fetchall()]
    for d_id in doc_ids:
        _update_document_status(cursor, d_id)

    conn.commit()
    conn.close()
    return {"success": True, "message": f"{len(req.riga_ids)} righe assegnate con successo a {sede['nome']}."}
