# Demo Data Management Routes
from fastapi import APIRouter, Depends
from app.database import get_db, init_db
from app.services.demo_service import load_demo_data_into_db
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/demo", tags=["Dati Demo"])

def require_admin(user: dict = Depends(get_current_user)):
    if not user.get("is_admin"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Azione riservata all'amministratore.")
    return user

@router.post("/load")
def load_sample_invoices(_: dict = Depends(require_admin)):
    """Carica le fatture di prova realistiche"""
    conn = get_db()
    results = load_demo_data_into_db(conn)
    conn.close()
    
    imported = sum(1 for r in results if r.get("success") and not r.get("is_duplicate"))
    duplicates = sum(1 for r in results if r.get("is_duplicate"))

    return {
        "success": True,
        "message": f"Dati demo caricati: {imported} nuove fatture importate ({duplicates} duplicati già presenti saltati).",
        "results": results
    }

@router.post("/reset")
def reset_database(_: dict = Depends(require_admin)):
    """Ripristina il database allo stato iniziale con sedi e prodotti di default"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM righe_fattura")
    cursor.execute("DELETE FROM documenti")
    cursor.execute("DELETE FROM mappature_prodotto")
    cursor.execute("DELETE FROM prodotti")
    cursor.execute("DELETE FROM regole_assegnazione")
    cursor.execute("DELETE FROM sedi")
    cursor.execute("DELETE FROM teamsystem_config")
    cursor.execute("DELETE FROM haccp_etichette")
    cursor.execute("DELETE FROM haccp_temperature")
    cursor.execute("DELETE FROM haccp_cambio_olio")
    cursor.execute("DELETE FROM haccp_pulizia_cappa")
    conn.commit()
    conn.close()

    init_db()

    return {"success": True, "message": "Database azzerato e reinizializzato con sedi e prodotti predefiniti."}
