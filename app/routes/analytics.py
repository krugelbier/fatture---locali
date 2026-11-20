# Purchase Analytics Routes with Granular Permission Enforcement
from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Optional
from app.database import get_db
from app.services.analytics_service import AnalyticsService
from app.routes.auth import get_current_user
from app.services.auth_service import user_has_permission

router = APIRouter(prefix="/api/analytics", tags=["Analisi Acquisti"])

def check_analytics_permission(user: dict, sede_id: Optional[int]) -> Optional[int]:
    """Valida i permessi e calcola l'eventuale sede forzata per utenti con accesso a un solo locale"""
    if sede_id:
        if not user_has_permission(user, sede_id, "fatture.view"):
            raise HTTPException(status_code=403, detail="Permesso non accordato per visualizzare l'analisi prezzi di questo locale.")
        return sede_id
    else:
        if not user_has_permission(user, None, "fatture.view"):
            raise HTTPException(status_code=403, detail="Non possiedi i permessi per accedere all'analisi acquisti.")
        # Se utente non admin autorizzato per una sola sede, forza quella sede
        if not user.get("is_admin"):
            allowed_sedi = [s["id"] for s in user.get("authorized_sedi", []) if "fatture.view" in user.get("permissions", {}).get(s["id"], [])]
            if len(allowed_sedi) == 1:
                return allowed_sedi[0]
            elif len(allowed_sedi) == 0:
                raise HTTPException(status_code=403, detail="Nessun locale autorizzato per l'analisi prezzi.")
    return sede_id

@router.get("/purchases")
def get_purchases_analytics(
    months: int = Query(6, ge=1, le=36),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    sede_id: Optional[int] = None,
    prodotto_id: Optional[int] = None,
    categoria: Optional[str] = None,
    fornitore: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    effective_sede_id = check_analytics_permission(user, sede_id)
    conn = get_db()
    data = AnalyticsService.get_purchase_analytics(
        conn=conn,
        months_back=months,
        date_from=date_from,
        date_to=date_to,
        sede_id=effective_sede_id,
        prodotto_id=prodotto_id,
        categoria=categoria,
        fornitore=fornitore
    )
    conn.close()
    return {"items": data, "count": len(data)}

@router.get("/drilldown")
def get_price_drilldown(
    prodotto_id: Optional[int] = None,
    raw_description: Optional[str] = None,
    fornitore: Optional[str] = None,
    sede_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    effective_sede_id = check_analytics_permission(user, sede_id)
    conn = get_db()
    lines = AnalyticsService.get_price_drilldown_lines(
        conn=conn,
        prodotto_id=prodotto_id,
        raw_description=raw_description,
        fornitore=fornitore,
        sede_id=effective_sede_id,
        date_from=date_from,
        date_to=date_to
    )
    conn.close()
    return {"lines": lines, "count": len(lines)}

@router.get("/summary")
def get_analytics_summary(
    months: int = Query(6, ge=1, le=36),
    sede_id: Optional[int] = None,
    user: dict = Depends(get_current_user)
):
    effective_sede_id = check_analytics_permission(user, sede_id)
    conn = get_db()
    cursor = conn.cursor()

    query_kpi = """
    SELECT 
        COUNT(DISTINCT d.id) as tot_fatture,
        SUM(CASE WHEN d.tipo_documento IN ('TD04', 'TD08') THEN -d.imponibile_totale ELSE d.imponibile_totale END) as spesa_netta_totale,
        COUNT(DISTINCT r.prodotto_id) as prodotti_mappati,
        COUNT(DISTINCT d.cedente_denominazione) as fornitori_attivi
    FROM documenti d
    LEFT JOIN righe_fattura r ON r.documento_id = d.id
    WHERE d.data_documento >= date('now', '-' || ? || ' month')
    """
    params_kpi = [months]
    if effective_sede_id:
        query_kpi += " AND (d.sede_id = ? OR r.sede_id = ?)"
        params_kpi.extend([effective_sede_id, effective_sede_id])

    cursor.execute(query_kpi, params_kpi)
    kpi = dict(cursor.fetchone())

    query_sedi = """
    SELECT 
        s.id, s.nome, s.colore_badge,
        SUM(CASE WHEN d.tipo_documento IN ('TD04', 'TD08') THEN -r.prezzo_totale_netto ELSE r.prezzo_totale_netto END) as spesa_sede
    FROM righe_fattura r
    JOIN documenti d ON r.documento_id = d.id
    JOIN sedi s ON COALESCE(r.sede_id, d.sede_id) = s.id
    WHERE d.data_documento >= date('now', '-' || ? || ' month')
    """
    params_sedi = [months]
    if effective_sede_id:
        query_sedi += " AND s.id = ?"
        params_sedi.append(effective_sede_id)
    query_sedi += " GROUP BY s.id, s.nome, s.colore_badge"

    cursor.execute(query_sedi, params_sedi)
    spesa_sedi = [dict(r) for r in cursor.fetchall()]

    conn.close()
    return {
        "kpi": {
            "tot_fatture": kpi["tot_fatture"] or 0,
            "spesa_netta_totale": round(kpi["spesa_netta_totale"] or 0.0, 2),
            "prodotti_mappati": kpi["prodotti_mappati"] or 0,
            "fornitori_attivi": kpi["fornitori_attivi"] or 0
        },
        "spesa_sedi": spesa_sedi
    }

@router.get("/categories")
def get_categories(user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT categoria FROM prodotti WHERE categoria IS NOT NULL ORDER BY categoria")
    cats = [row["categoria"] for row in cursor.fetchall()]
    conn.close()
    return {"categories": cats}
