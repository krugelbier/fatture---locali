# Invoices Routes with Granular Permission Enforcement
import json
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, Depends
from typing import List, Optional
from app.database import get_db
from app.services.importer.xml_importer import XmlFileImporter
from app.routes.auth import get_current_user
from app.services.auth_service import user_has_permission

router = APIRouter(prefix="/api/invoices", tags=["Fatture"])

@router.get("")
def list_invoices(
    sede_id: Optional[int] = None,
    stato: Optional[str] = None,
    tipo: Optional[str] = None,
    search: Optional[str] = None,
    fornitore: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    # Verifica permessi utente per consultare le fatture
    if sede_id:
        if not user_has_permission(user, sede_id, "fatture.view"):
            raise HTTPException(status_code=403, detail="Permesso non accordato per visualizzare le fatture di questa sede.")
    else:
        # Se non specifica la sede, verifica che abbia fatture.view in almeno una sede
        if not user_has_permission(user, None, "fatture.view"):
            raise HTTPException(status_code=403, detail="Non hai i permessi per accedere alla sezione Fatture e prezzi.")

    conn = get_db()
    cursor = conn.cursor()

    # Se l'utente non è admin, filtra per le sedi a cui ha effettivamente accesso
    allowed_sede_ids = []
    if not user.get("is_admin"):
        allowed_sede_ids = [s["id"] for s in user.get("authorized_sedi", []) if "fatture.view" in user.get("permissions", {}).get(s["id"], [])]
        if not allowed_sede_ids:
            conn.close()
            raise HTTPException(status_code=403, detail="Nessuna sede autorizzata per la consultazione fatture.")

    query = """
    SELECT 
        d.id, d.filename, d.tipo_documento, d.numero_documento, d.data_documento,
        d.cedente_denominazione, d.cedente_piva, d.importo_totale, d.imponibile_totale,
        d.iva_totale, d.divisa, d.sede_id, d.stato_assegnazione, d.metodo_assegnazione,
        d.indirizzo_resa_estratto, d.created_at,
        s.nome as sede_nome, s.colore_badge as sede_colore,
        (SELECT COUNT(*) FROM righe_fattura r WHERE r.documento_id = d.id) as tot_righe,
        (SELECT COUNT(*) FROM righe_fattura r WHERE r.documento_id = d.id AND r.sede_id IS NULL) as righe_da_assegnare,
        (SELECT COUNT(*) FROM righe_fattura r WHERE r.documento_id = d.id AND r.prodotto_id IS NULL) as righe_non_mappate
    FROM documenti d
    LEFT JOIN sedi s ON d.sede_id = s.id
    WHERE 1=1
    """
    params = []

    if sede_id:
        query += " AND (d.sede_id = ? OR EXISTS (SELECT 1 FROM righe_fattura r WHERE r.documento_id = d.id AND r.sede_id = ?))"
        params.extend([sede_id, sede_id])
    elif not user.get("is_admin") and allowed_sede_ids:
        placeholders = ",".join(["?"] * len(allowed_sede_ids))
        query += f" AND (d.sede_id IN ({placeholders}) OR d.sede_id IS NULL OR EXISTS (SELECT 1 FROM righe_fattura r WHERE r.documento_id = d.id AND r.sede_id IN ({placeholders})))"
        params.extend(allowed_sede_ids + allowed_sede_ids)

    if stato:
        query += " AND d.stato_assegnazione = ?"
        params.append(stato)

    if tipo:
        query += " AND d.tipo_documento = ?"
        params.append(tipo)

    if fornitore:
        query += " AND UPPER(d.cedente_denominazione) LIKE ?"
        params.append(f"%{fornitore.upper()}%")

    if search:
        query += """ AND (
            UPPER(d.numero_documento) LIKE ? 
            OR UPPER(d.cedente_denominazione) LIKE ? 
            OR UPPER(d.cedente_piva) LIKE ?
            OR UPPER(d.indirizzo_resa_estratto) LIKE ?
        )"""
        s_term = f"%{search.upper()}%"
        params.extend([s_term, s_term, s_term, s_term])

    if date_from:
        query += " AND d.data_documento >= ?"
        params.append(date_from)

    if date_to:
        query += " AND d.data_documento <= ?"
        params.append(date_to)

    query += " ORDER BY d.data_documento DESC, d.numero_documento DESC"

    cursor.execute(query, params)
    invoices = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"invoices": invoices, "total": len(invoices)}

@router.get("/{invoice_id}")
def get_invoice_detail(invoice_id: int, user: dict = Depends(get_current_user)):
    if not user_has_permission(user, None, "fatture.view"):
        raise HTTPException(status_code=403, detail="Permesso di consultazione fatture non accordato.")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT 
        d.*, 
        s.nome as sede_nome, s.colore_badge as sede_colore
    FROM documenti d
    LEFT JOIN sedi s ON d.sede_id = s.id
    WHERE d.id = ?
    """, (invoice_id,))
    doc = cursor.fetchone()
    if not doc:
        conn.close()
        raise HTTPException(status_code=404, detail="Documento non trovato")

    doc_dict = dict(doc)
    doc_sede_id = doc_dict.get("sede_id")

    # Verifica se l'utente ha accesso a questa sede
    if doc_sede_id and not user_has_permission(user, doc_sede_id, "fatture.view"):
        conn.close()
        raise HTTPException(status_code=403, detail="Non sei autorizzato a consultare i documenti di questo locale.")

    doc_dict["ddt_list"] = json.loads(doc_dict["ddt_elenco_json"] or "[]")

    cursor.execute("""
    SELECT 
        r.*,
        s.nome as sede_nome, s.colore_badge as sede_colore,
        p.nome_canonico as prodotto_nome, p.categoria as prodotto_categoria, p.unita_base as prodotto_um_base,
        m.fattore_conversione, m.unita_confezione
    FROM righe_fattura r
    LEFT JOIN sedi s ON r.sede_id = s.id
    LEFT JOIN prodotti p ON r.prodotto_id = p.id
    LEFT JOIN mappature_prodotto m ON (
        m.prodotto_id = p.id 
        AND (m.fornitore_piva IS NULL OR m.fornitore_piva = '' OR m.fornitore_piva = ?)
        AND (UPPER(r.descrizione) LIKE '%' || UPPER(m.pattern_testo) || '%')
    )
    WHERE r.documento_id = ?
    ORDER BY r.numero_linea ASC
    """, (doc_dict["cedente_piva"], invoice_id))

    rows = []
    for r in cursor.fetchall():
        row_dict = dict(r)
        factor = row_dict["fattore_conversione"] or 1.0
        row_dict["quantita_base"] = round(row_dict["quantita"] * factor, 2)
        if row_dict["quantita"] * factor != 0:
            row_dict["prezzo_unitario_base"] = round(row_dict["prezzo_totale_netto"] / (row_dict["quantita"] * factor), 4)
        else:
            row_dict["prezzo_unitario_base"] = row_dict["prezzo_unitario_netto"]
        rows.append(row_dict)

    doc_dict["righe"] = rows
    conn.close()
    return doc_dict

@router.post("/upload")
async def upload_invoices(
    files: List[UploadFile] = File(...),
    user: dict = Depends(get_current_user)
):
    # Verifica permesso di importazione
    if not user_has_permission(user, None, "fatture.import"):
        raise HTTPException(status_code=403, detail="Permesso non accordato per importare fatture.")

    conn = get_db()
    results = []
    duplicates = 0
    imported = 0
    errors = 0

    for file in files:
        fname = file.filename or "file_senza_nome"
        fname_lower = fname.lower()
        try:
            content = await file.read()
            if fname_lower.endswith(".zip") or file.content_type in ["application/zip", "application/x-zip-compressed"]:
                zip_res = XmlFileImporter.process_zip_bytes(conn, content, fname)
                results.append(zip_res)
                imported += zip_res.get("imported", 0)
                duplicates += zip_res.get("duplicates", 0)
                errors += zip_res.get("errors", 0)
            else:
                res = XmlFileImporter.process_file_bytes(conn, content, fname)
                results.append(res)
                if res.get("is_duplicate"):
                    duplicates += 1
                elif res.get("success"):
                    imported += 1
                else:
                    errors += 1
        except Exception as e:
            errors += 1
            results.append({
                "filename": fname,
                "success": False,
                "is_duplicate": False,
                "message": f"Errore durante l'elaborazione di {fname}: {str(e)}"
            })

    conn.close()
    return {
        "total_files": len(files),
        "imported": imported,
        "duplicates": duplicates,
        "errors": errors,
        "details": results
    }

@router.post("/{invoice_id}/assign")
def assign_invoice_to_venue(
    invoice_id: int,
    sede_id: int = Form(...),
    apply_to_all_lines: bool = Form(True),
    user: dict = Depends(get_current_user)
):
    if not user_has_permission(user, sede_id, "fatture.assign"):
        raise HTTPException(status_code=403, detail="Permesso non accordato per assegnare fatture a questa sede.")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, nome FROM sedi WHERE id = ?", (sede_id,))
    sede = cursor.fetchone()
    if not sede:
        conn.close()
        raise HTTPException(status_code=404, detail="Sede specificata non valida")

    cursor.execute("""
    UPDATE documenti 
    SET sede_id = ?, stato_assegnazione = 'COMPLETA', metodo_assegnazione = 'MANUALE'
    WHERE id = ?
    """, (sede_id, invoice_id))

    if apply_to_all_lines:
        cursor.execute("""
        UPDATE righe_fattura
        SET sede_id = ?, metodo_assegnazione = 'MANUALE'
        WHERE documento_id = ?
        """, (sede_id, invoice_id))

    conn.commit()
    conn.close()
    return {"success": True, "message": f"Fattura assegnata con successo a {sede['nome']}."}

@router.delete("/{invoice_id}")
def delete_invoice(invoice_id: int, user: dict = Depends(get_current_user)):
    if not (user.get("is_admin") or user_has_permission(user, None, "fatture.assign")):
        raise HTTPException(status_code=403, detail="Permesso non accordato per eliminare fatture.")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM documenti WHERE id = ?", (invoice_id,))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Fattura eliminata con successo."}
