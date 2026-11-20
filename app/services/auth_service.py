# Authentication and Authorization Service for Fatture Locali & HACCP
import os
import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from fastapi import HTTPException, Security, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer(auto_error=False)

def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """Genera hash sicuro della password utilizzando PBKDF2-HMAC-SHA256 con salt casuale"""
    if not salt:
        salt = secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()
    return pw_hash, salt

def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """Verifica se la password corrisponde all'hash salvato"""
    computed_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(computed_hash, stored_hash)

def create_session(conn: sqlite3.Connection, user_id: int, days_valid: int = 7) -> str:
    """Crea una nuova sessione e restituisce il token univoco"""
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now() + timedelta(days=days_valid)).strftime("%Y-%m-%d %H:%M:%S")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sessioni (token, utente_id, expires_at)
        VALUES (?, ?, ?)
    """, (token, user_id, expires_at))
    conn.commit()
    return token

def revoke_session(conn: sqlite3.Connection, token: str) -> None:
    """Elimina una sessione (logout)"""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessioni WHERE token = ?", (token,))
    conn.commit()

def revoke_all_user_sessions(conn: sqlite3.Connection, user_id: int) -> None:
    """Revoca tutte le sessioni di un utente (es. disattivazione o cambio password)"""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessioni WHERE utente_id = ?", (user_id,))
    conn.commit()

def get_user_permissions_map(conn: sqlite3.Connection, user_id: int) -> Dict[int, List[str]]:
    """Restituisce la mappa dei permessi per sede: {sede_id: ['fatture.view', ...]}"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT sede_id, permesso
        FROM permessi_utente
        WHERE utente_id = ?
    """, (user_id,))
    res: Dict[int, List[str]] = {}
    for row in cursor.fetchall():
        s_id = row["sede_id"]
        perm = row["permesso"]
        if s_id not in res:
            res[s_id] = []
        res[s_id].append(perm)
    return res

def get_current_user_from_token(conn: sqlite3.Connection, token: str) -> Optional[Dict[str, Any]]:
    """Recupera l'utente associato al token se valido e attivo"""
    if not token:
        return None
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        SELECT u.id, u.username, u.nome_completo, u.is_admin, u.is_active, s.expires_at
        FROM sessioni s
        JOIN utenti u ON s.utente_id = u.id
        WHERE s.token = ? AND s.expires_at > ?
    """, (token, now_str))
    user_row = cursor.fetchone()
    if not user_row:
        return None
    
    user = dict(user_row)
    user["is_admin"] = bool(user.get("is_admin"))
    user["is_active"] = bool(user.get("is_active"))
    user["full_name"] = user.get("nome_completo")

    if not user.get("is_active"):
        # Se l'utente è stato disattivato, revoca la sessione immediatamente
        revoke_session(conn, token)
        return None

    # Carica le sedi a cui l'utente ha accesso
    user_id = user["id"]
    is_admin = user["is_admin"]

    if is_admin:
        # L'amministratore ha tutte le sedi e tutti i permessi
        cursor.execute("SELECT id, nome, codice, comune FROM sedi WHERE is_active = 1 ORDER BY id")
        sedi_list = [dict(r) for r in cursor.fetchall()]
        user["authorized_sedi"] = [s["id"] for s in sedi_list]
        user["authorized_sedi_details"] = sedi_list
        user["permissions"] = {s["id"]: ["*"] for s in sedi_list}
        user["permissions_list"] = [{"sede_id": s["id"], "permesso": "*"} for s in sedi_list]
    else:
        perms_map = get_user_permissions_map(conn, user_id)
        user["permissions"] = perms_map
        if perms_map:
            sedi_ids = list(perms_map.keys())
            placeholders = ",".join(["?"] * len(sedi_ids))
            cursor.execute(f"SELECT id, nome, codice, comune FROM sedi WHERE id IN ({placeholders}) AND is_active = 1 ORDER BY id", sedi_ids)
            sedi_list = [dict(r) for r in cursor.fetchall()]
            user["authorized_sedi"] = [s["id"] for s in sedi_list]
            user["authorized_sedi_details"] = sedi_list
        else:
            user["authorized_sedi"] = []
            user["authorized_sedi_details"] = []

        perms_list = []
        for sid, perms in perms_map.items():
            for p in perms:
                perms_list.append({"sede_id": sid, "permesso": p})
        user["permissions_list"] = perms_list

    return user

def user_has_permission(user: Dict[str, Any], sede_id: Optional[int], permission_name: str) -> bool:
    """Verifica se l'utente possiede il permesso per la sede specificata"""
    if not user:
        return False
    if user.get("is_admin"):
        return True
    if sede_id is None:
        # Se non è specificata una sede, controlla se ha il permesso in almeno una sede autorizzata
        for perms in user.get("permissions", {}).values():
            if permission_name in perms or "*" in perms:
                return True
        return False

    sede_perms = user.get("permissions", {}).get(sede_id, [])
    return (permission_name in sede_perms) or ("*" in sede_perms)
