# Settings and Configuration Routes with Granular Permissions
import os
import shutil
import tempfile
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import FileResponse
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from app.database import get_db
from app.services.importer.teamsystem_digital import TeamSystemDigitalConnector
from app.routes.auth import get_current_user
from app.services.auth_service import user_has_permission
from backup import create_backup, restore_backup, verify_integrity, BACKUP_DIR, DB_PATH

router = APIRouter(prefix="/api/settings", tags=["Configurazione"])

def require_admin(user: dict = Depends(get_current_user)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Accesso riservato all'amministratore.")
    return user

class SedeCreateUpdate(BaseModel):
    nome: str
    codice: str
    indirizzo: str
    cap: Optional[str] = "38015"
    comune: Optional[str] = "Lavis"
    provincia: Optional[str] = "TN"
    parole_chiave: Optional[str] = ""
    colore_badge: Optional[str] = "#3b82f6"

class RuleCreate(BaseModel):
    sede_id: int
    tipo_campo: str
    operatore: str
    valore_match: str
    priorita: int = 10
    descrizione: Optional[str] = ""

class ProductCreateUpdate(BaseModel):
    nome_canonico: str
    categoria: str
    unita_base: str
    descrizione: Optional[str] = ""

class MappingCreateUpdate(BaseModel):
    prodotto_id: int
    fornitore_piva: Optional[str] = None
    fornitore_denominazione: Optional[str] = None
    pattern_testo: str
    tipo_match: str = "CONTIENE"
    fattore_conversione: float = 1.0
    unita_confezione: Optional[str] = None
    note: Optional[str] = ""

class TeamSystemConfigModel(BaseModel):
    is_enabled: bool
    environment: str
    client_id: str
    client_secret: str
    company_id: str

# --- Sedi ---
@router.get("/sedi")
def list_sedi(user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    # Se l'utente non è admin, mostra solo le sedi a cui ha accesso
    if user.get("is_admin"):
        cursor.execute("""
        SELECT 
            s.*,
            (SELECT COUNT(*) FROM documenti d WHERE d.sede_id = s.id) as tot_fatture_assegnate,
            (SELECT COUNT(*) FROM righe_fattura r WHERE r.sede_id = s.id) as tot_righe_assegnate
        FROM sedi s
        ORDER BY s.id ASC
        """)
    else:
        allowed = [s["id"] for s in user.get("authorized_sedi", [])]
        if not allowed:
            conn.close()
            return {"sedi": []}
        placeholders = ",".join(["?"] * len(allowed))
        cursor.execute(f"""
        SELECT 
            s.*,
            (SELECT COUNT(*) FROM documenti d WHERE d.sede_id = s.id) as tot_fatture_assegnate,
            (SELECT COUNT(*) FROM righe_fattura r WHERE r.sede_id = s.id) as tot_righe_assegnate
        FROM sedi s
        WHERE s.id IN ({placeholders})
        ORDER BY s.id ASC
        """, allowed)
    sedi = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"sedi": sedi}

@router.post("/sedi")
def create_sede(req: SedeCreateUpdate, _: dict = Depends(require_admin)):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO sedi (nome, codice, indirizzo, cap, comune, provincia, parole_chiave, colore_badge)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (req.nome, req.codice.upper(), req.indirizzo, req.cap, req.comune, req.provincia, req.parole_chiave, req.colore_badge))
        conn.commit()
        s_id = cursor.lastrowid
        conn.close()
        return {"success": True, "id": s_id, "message": f"Sede {req.nome} creata con successo."}
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Errore nella creazione della sede: {str(e)}")

@router.put("/sedi/{sede_id}")
def update_sede(sede_id: int, req: SedeCreateUpdate, _: dict = Depends(require_admin)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE sedi 
    SET nome = ?, codice = ?, indirizzo = ?, cap = ?, comune = ?, provincia = ?, parole_chiave = ?, colore_badge = ?
    WHERE id = ?
    """, (req.nome, req.codice.upper(), req.indirizzo, req.cap, req.comune, req.provincia, req.parole_chiave, req.colore_badge, sede_id))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Sede aggiornata con successo."}

# --- Regole Assegnazione ---
@router.get("/rules")
def list_rules(user: dict = Depends(get_current_user)):
    if not (user.get("is_admin") or user_has_permission(user, None, "fatture.assign")):
        raise HTTPException(status_code=403, detail="Permesso non accordato.")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT r.*, s.nome as sede_nome, s.colore_badge as sede_colore
    FROM regole_assegnazione r
    JOIN sedi s ON r.sede_id = s.id
    ORDER BY r.priorita ASC, r.id ASC
    """)
    rules = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"rules": rules}

@router.post("/rules")
def create_rule(req: RuleCreate, user: dict = Depends(get_current_user)):
    if not (user.get("is_admin") or user_has_permission(user, req.sede_id, "fatture.assign")):
        raise HTTPException(status_code=403, detail="Permesso non accordato.")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO regole_assegnazione (sede_id, tipo_campo, operatore, valore_match, priorita, descrizione)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (req.sede_id, req.tipo_campo, req.operatore, req.valore_match, req.priorita, req.descrizione))
    conn.commit()
    r_id = cursor.lastrowid
    conn.close()
    return {"success": True, "id": r_id, "message": "Regola creata con successo."}

@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, user: dict = Depends(get_current_user)):
    if not (user.get("is_admin") or user_has_permission(user, None, "fatture.assign")):
        raise HTTPException(status_code=403, detail="Permesso non accordato.")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM regole_assegnazione WHERE id = ?", (rule_id,))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Regola rimossa con successo."}

# --- Prodotti Canonici ---
@router.get("/products")
def list_products(user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT 
        p.*,
        (SELECT COUNT(*) FROM mappature_prodotto m WHERE m.prodotto_id = p.id) as tot_mappature,
        (SELECT COUNT(*) FROM righe_fattura r WHERE r.prodotto_id = p.id) as tot_righe_collegate
    FROM prodotti p
    ORDER BY p.categoria ASC, p.nome_canonico ASC
    """)
    products = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"products": products}

@router.post("/products")
def create_product(req: ProductCreateUpdate, user: dict = Depends(get_current_user)):
    if not (user.get("is_admin") or user_has_permission(user, None, "fatture.products")):
        raise HTTPException(status_code=403, detail="Permesso non accordato.")
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO prodotti (nome_canonico, categoria, unita_base, descrizione)
        VALUES (?, ?, ?, ?)
        """, (req.nome_canonico.strip(), req.categoria, req.unita_base.upper(), req.descrizione))
        conn.commit()
        p_id = cursor.lastrowid
        conn.close()
        return {"success": True, "id": p_id, "message": f"Prodotto '{req.nome_canonico}' registrato."}
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Errore creazione prodotto: {str(e)}")

# --- Mappature e Conversioni Confezioni ---
@router.get("/mappings")
def list_mappings(user: dict = Depends(get_current_user)):
    if not (user.get("is_admin") or user_has_permission(user, None, "fatture.products")):
        raise HTTPException(status_code=403, detail="Permesso non accordato.")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT 
        m.*,
        p.nome_canonico as prodotto_nome,
        p.categoria as prodotto_categoria,
        p.unita_base as prodotto_um_base
    FROM mappature_prodotto m
    JOIN prodotti p ON m.prodotto_id = p.id
    ORDER BY p.nome_canonico ASC, m.id ASC
    """)
    mappings = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"mappings": mappings}

@router.post("/mappings")
def create_mapping(req: MappingCreateUpdate, user: dict = Depends(get_current_user)):
    if not (user.get("is_admin") or user_has_permission(user, None, "fatture.products")):
        raise HTTPException(status_code=403, detail="Permesso non accordato.")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO mappature_prodotto (
        prodotto_id, fornitore_piva, fornitore_denominazione,
        pattern_testo, tipo_match, fattore_conversione, unita_confezione, note
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        req.prodotto_id, req.fornitore_piva, req.fornitore_denominazione,
        req.pattern_testo.strip(), req.tipo_match, req.fattore_conversione,
        req.unita_confezione, req.note
    ))
    conn.commit()
    m_id = cursor.lastrowid

    cursor.execute("""
    UPDATE righe_fattura 
    SET prodotto_id = ?
    WHERE (prodotto_id IS NULL OR prodotto_id = 0)
    AND UPPER(descrizione) LIKE ?
    """, (req.prodotto_id, f"%{req.pattern_testo.upper()}%"))

    conn.commit()
    conn.close()
    return {"success": True, "id": m_id, "message": "Regola di associazione e conversione registrata con successo."}

@router.delete("/mappings/{mapping_id}")
def delete_mapping(mapping_id: int, user: dict = Depends(get_current_user)):
    if not (user.get("is_admin") or user_has_permission(user, None, "fatture.products")):
        raise HTTPException(status_code=403, detail="Permesso non accordato.")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM mappature_prodotto WHERE id = ?", (mapping_id,))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Mappatura eliminata."}

# --- TeamSystem Digital ---
@router.get("/teamsystem")
def get_teamsystem_config(_: dict = Depends(require_admin)):
    conn = get_db()
    connector = TeamSystemDigitalConnector(conn)
    cfg = connector.get_config()
    if cfg.get("client_secret"):
        cfg["client_secret_masked"] = cfg["client_secret"][:4] + "••••••••" if len(cfg["client_secret"]) > 4 else "••••"
    else:
        cfg["client_secret_masked"] = ""
    conn.close()
    return {"config": cfg}

@router.post("/teamsystem")
def save_teamsystem_config(req: TeamSystemConfigModel, _: dict = Depends(require_admin)):
    conn = get_db()
    connector = TeamSystemDigitalConnector(conn)
    connector.save_config(
        is_enabled=req.is_enabled,
        environment=req.environment,
        client_id=req.client_id,
        client_secret=req.client_secret,
        company_id=req.company_id
    )
    conn.close()
    return {"success": True, "message": "Impostazioni TeamSystem Digital salvate con successo."}

@router.post("/teamsystem/test")
def test_teamsystem_connection(_: dict = Depends(require_admin)):
    conn = get_db()
    connector = TeamSystemDigitalConnector(conn)
    res = connector.test_connection()
    conn.close()
    return res

@router.post("/teamsystem/sync")
def trigger_teamsystem_sync(_: dict = Depends(require_admin)):
    conn = get_db()
    connector = TeamSystemDigitalConnector(conn)
    res = connector.sync_invoices()
    conn.close()
    return res

# --- Gestione Backup & Database (Riservato Amministratore) ---
@router.post("/backup/run")
def run_backup_now(_: dict = Depends(require_admin)):
    """Esegue un backup a caldo istantaneo del database"""
    try:
        fpath = create_backup()
        fname = os.path.basename(fpath)
        size_kb = os.path.getsize(fpath) / 1024
        return {
            "success": True,
            "filename": fname,
            "size_kb": round(size_kb, 1),
            "message": f"Backup creato con successo: {fname} ({size_kb:.1f} KB)"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore durante la creazione del backup: {str(e)}")

@router.get("/backup/download")
def download_current_backup(_: dict = Depends(require_admin)):
    """Genera ed effettua il download immediato di un backup compresso (.db.gz)"""
    try:
        fpath = create_backup()
        fname = os.path.basename(fpath)
        return FileResponse(
            fpath,
            media_type="application/gzip",
            filename=fname
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Impossibile scaricare il backup: {str(e)}")

@router.get("/backup/list")
def get_backups_list(_: dict = Depends(require_admin)):
    """Restituisce l'elenco dei backup presenti nella cartella"""
    if not os.path.exists(BACKUP_DIR):
        return {"backups": [], "count": 0}

    files = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith("backup_") and (f.endswith(".db.gz") or f.endswith(".db"))], reverse=True)
    items = []
    for f in files:
        fpath = os.path.join(BACKUP_DIR, f)
        mtime = os.path.getmtime(fpath)
        items.append({
            "filename": f,
            "size_kb": round(os.path.getsize(fpath) / 1024, 1),
            "timestamp": mtime,
            "created_at": os.path.getctime(fpath)
        })
    return {"backups": items, "count": len(items)}

@router.post("/backup/upload")
async def upload_and_restore_database(file: UploadFile = File(...), _: dict = Depends(require_admin)):
    """Carica e ripristina un database SQLite (.db o .db.gz) con controllo preventivo di integrità"""
    if not file.filename.endswith((".db", ".db.gz", ".sqlite")):
        raise HTTPException(status_code=400, detail="Formato file non supportato. Caricare un file .db o .db.gz")

    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
        tmp_path = tmp.name
        content = await file.read()
        tmp.write(content)

    try:
        restore_backup(tmp_path, target_db_path=DB_PATH)
        return {
            "success": True,
            "message": f"Database ripristinato con successo dal file '{file.filename}'. Tutti i dati storici sono stati caricati."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore durante il ripristino del database: {str(e)}")
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
