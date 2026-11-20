# Admin User Management API Routes
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Optional, Any, Union
from app.database import get_db, ALL_PERMISSIONS
from app.routes.auth import get_current_user
from app.services.auth_service import hash_password, revoke_all_user_sessions

router = APIRouter(prefix="/api/users", tags=["Gestione Utenti"])

def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Accesso riservato all'amministratore.")
    return user

class UserCreateRequest(BaseModel):
    username: str
    password: str
    nome_completo: Optional[str] = None
    full_name: Optional[str] = None
    is_admin: bool = False
    is_active: bool = True
    permessi_per_sede: Optional[List[Any]] = []
    permissions: Optional[List[Any]] = []

class UserUpdateRequest(BaseModel):
    nome_completo: Optional[str] = None
    full_name: Optional[str] = None
    password: Optional[str] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None
    permessi_per_sede: Optional[List[Any]] = None
    permissions: Optional[List[Any]] = None

class PasswordResetRequest(BaseModel):
    new_password: str

@router.get("/permissions-catalog")
def get_permissions_catalog(_: dict = Depends(require_admin)):
    """Restituisce l'elenco completo dei permessi configurabili raggruppati per sezione"""
    grouped: Dict[str, List[Dict[str, str]]] = {}
    catalog_list = []
    
    for code, section, desc in ALL_PERMISSIONS:
        if section not in grouped:
            grouped[section] = []
        item = {"code": code, "codice": code, "label": desc, "descrizione": desc}
        grouped[section].append(item)

    for section, perms in grouped.items():
        catalog_list.append({
            "section": section,
            "permissions": perms
        })

    return {
        "catalog": catalog_list,
        "grouped": grouped,
        "all": [{"code": c, "codice": c, "section": s, "sezione": s, "label": d, "descrizione": d} for c, s, d in ALL_PERMISSIONS]
    }

@router.get("")
def list_users(_: dict = Depends(require_admin)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, nome_completo, is_admin, is_active, created_at
        FROM utenti
        ORDER BY is_admin DESC, username ASC
    """)
    users = []
    for r in cursor.fetchall():
        u = dict(r)
        u["is_admin"] = bool(u.get("is_admin"))
        u["is_active"] = bool(u.get("is_active"))
        u["full_name"] = u.get("nome_completo")

        # Carica permessi per ciascuna sede
        cursor.execute("""
            SELECT p.sede_id, s.nome as sede_nome, p.permesso
            FROM permessi_utente p
            JOIN sedi s ON p.sede_id = s.id
            WHERE p.utente_id = ?
        """, (u["id"],))
        
        perms_rows = cursor.fetchall()
        p_by_sede: Dict[int, Dict[str, Any]] = {}
        flat_perms = []
        authorized_sedi = set()

        for pr in perms_rows:
            sid = pr["sede_id"]
            authorized_sedi.add(sid)
            flat_perms.append({"sede_id": sid, "permesso": pr["permesso"]})
            if sid not in p_by_sede:
                p_by_sede[sid] = {"sede_id": sid, "sede_nome": pr["sede_nome"], "permessi": []}
            p_by_sede[sid]["permessi"].append(pr["permesso"])

        u["permessi_per_sede"] = list(p_by_sede.values())
        u["permissions"] = flat_perms
        u["authorized_sedi"] = list(authorized_sedi) if not u["is_admin"] else [1, 2]
        users.append(u)

    conn.close()
    return {"users": users}

@router.post("")
def create_user(req: UserCreateRequest, _: dict = Depends(require_admin)):
    username = req.username.strip().lower()
    full_name = (req.full_name or req.nome_completo or username).strip()
    if not username or not req.password:
        raise HTTPException(status_code=400, detail="Nome utente e password sono obbligatori.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM utenti WHERE username = ?", (username,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail=f"L'utente '{username}' esiste già.")

    pw_hash, salt = hash_password(req.password)
    cursor.execute("""
        INSERT INTO utenti (username, password_hash, salt, nome_completo, is_admin, is_active)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (username, pw_hash, salt, full_name, 1 if req.is_admin else 0, 1 if req.is_active else 0))
    new_user_id = cursor.lastrowid

    # Salva permessi per sede
    perms_to_insert = []
    if req.permissions:
        for p in req.permissions:
            if isinstance(p, dict) and "sede_id" in p and "permesso" in p:
                perms_to_insert.append((p["sede_id"], p["permesso"]))
    if req.permessi_per_sede:
        for entry in req.permessi_per_sede:
            if isinstance(entry, dict) and "sede_id" in entry:
                sid = entry["sede_id"]
                for perm in entry.get("permessi", []):
                    perms_to_insert.append((sid, perm))

    for sid, perm in perms_to_insert:
        cursor.execute("""
            INSERT OR IGNORE INTO permessi_utente (utente_id, sede_id, permesso)
            VALUES (?, ?, ?)
        """, (new_user_id, sid, perm))

    conn.commit()
    conn.close()
    return {"success": True, "user_id": new_user_id, "message": f"Utente '{username}' creato con successo."}

@router.put("/{user_id}")
def update_user(user_id: int, req: UserUpdateRequest, _: dict = Depends(require_admin)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, nome_completo, is_admin, is_active FROM utenti WHERE id = ?", (user_id,))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Utente non trovato.")

    user_dict = dict(existing)
    full_name = (req.full_name or req.nome_completo or user_dict["nome_completo"]).strip()
    is_admin_val = req.is_admin if req.is_admin is not None else user_dict["is_admin"]
    is_active_val = req.is_active if req.is_active is not None else user_dict["is_active"]

    # Se viene disattivato, revoca subito tutte le sessioni attive
    if is_active_val == 0 or is_active_val is False:
        revoke_all_user_sessions(conn, user_id)

    cursor.execute("""
        UPDATE utenti
        SET nome_completo = ?, is_admin = ?, is_active = ?
        WHERE id = ?
    """, (full_name, 1 if is_admin_val else 0, 1 if is_active_val else 0, user_id))

    if req.password:
        pw_hash, salt = hash_password(req.password)
        cursor.execute("""
            UPDATE utenti
            SET password_hash = ?, salt = ?
            WHERE id = ?
        """, (pw_hash, salt, user_id))
        revoke_all_user_sessions(conn, user_id)

    # Aggiorna permessi solo se esplicitamente forniti
    if req.permissions is not None or req.permessi_per_sede is not None:
        cursor.execute("DELETE FROM permessi_utente WHERE utente_id = ?", (user_id,))
        perms_to_insert = []
        if req.permissions:
            for p in req.permissions:
                if isinstance(p, dict) and "sede_id" in p and "permesso" in p:
                    perms_to_insert.append((p["sede_id"], p["permesso"]))
        if req.permessi_per_sede:
            for entry in req.permessi_per_sede:
                if isinstance(entry, dict) and "sede_id" in entry:
                    sid = entry["sede_id"]
                    for perm in entry.get("permessi", []):
                        perms_to_insert.append((sid, perm))

        for sid, perm in perms_to_insert:
            cursor.execute("""
                INSERT OR IGNORE INTO permessi_utente (utente_id, sede_id, permesso)
                VALUES (?, ?, ?)
            """, (user_id, sid, perm))

    conn.commit()
    conn.close()
    return {"success": True, "message": "Utente e permessi aggiornati con successo."}

@router.delete("/{user_id}")
def delete_user(user_id: int, _: dict = Depends(require_admin)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT username, is_admin FROM utenti WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Utente non trovato.")
    if row["username"] == "admin":
        conn.close()
        raise HTTPException(status_code=400, detail="Impossibile eliminare l'amministratore principale.")

    revoke_all_user_sessions(conn, user_id)
    cursor.execute("DELETE FROM permessi_utente WHERE utente_id = ?", (user_id,))
    cursor.execute("DELETE FROM utenti WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return {"success": True, "message": f"Utente {row['username']} eliminato."}

@router.post("/{user_id}/reset-password")
def reset_password(user_id: int, req: PasswordResetRequest, _: dict = Depends(require_admin)):
    if not req.new_password:
        raise HTTPException(status_code=400, detail="La nuova password non può essere vuota.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username FROM utenti WHERE id = ?", (user_id,))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Utente non trovato.")

    pw_hash, salt = hash_password(req.new_password)
    cursor.execute("""
        UPDATE utenti
        SET password_hash = ?, salt = ?
        WHERE id = ?
    """, (pw_hash, salt, user_id))

    revoke_all_user_sessions(conn, user_id)
    conn.commit()
    conn.close()
    return {"success": True, "message": f"Password reimpostata con successo per l'utente '{existing['username']}'."}

@router.post("/{user_id}/toggle-active")
def toggle_user_active(user_id: int, _: dict = Depends(require_admin)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, is_active FROM utenti WHERE id = ?", (user_id,))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Utente non trovato.")

    new_state = 0 if existing["is_active"] else 1
    cursor.execute("UPDATE utenti SET is_active = ? WHERE id = ?", (new_state, user_id))
    if new_state == 0:
        revoke_all_user_sessions(conn, user_id)

    conn.commit()
    conn.close()
    stato_msg = "attivato" if new_state == 1 else "disattivato (e disconnesso da tutte le sessioni)"
    return {"success": True, "is_active": bool(new_state), "message": f"Utente {existing['username']} {stato_msg}."}
