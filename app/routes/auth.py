# Authentication API Routes
from fastapi import APIRouter, HTTPException, Request, Header, Depends
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.services.auth_service import (
    verify_password, hash_password, create_session,
    revoke_session, get_current_user_from_token
)

router = APIRouter(prefix="/api/auth", tags=["Autenticazione"])

class LoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    
    if not token:
        raise HTTPException(status_code=401, detail="Sessione non valida o mancante. Effettua l'accesso.")

    conn = get_db()
    user = get_current_user_from_token(conn, token)
    conn.close()

    if not user:
        raise HTTPException(status_code=401, detail="Sessione scaduta o account disattivato. Riaccedi.")
    return user

@router.post("/login")
def login(req: LoginRequest):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, password_hash, salt, nome_completo, is_admin, is_active
        FROM utenti
        WHERE username = ?
    """, (req.username.strip(),))
    user_row = cursor.fetchone()

    if not user_row:
        conn.close()
        raise HTTPException(status_code=401, detail="Nome utente o password errati.")

    user = dict(user_row)
    if not user.get("is_active"):
        conn.close()
        raise HTTPException(status_code=403, detail="Account disattivato. Contatta l'amministratore.")

    if not verify_password(req.password, user["password_hash"], user["salt"]):
        conn.close()
        raise HTTPException(status_code=401, detail="Nome utente o password errati.")

    token = create_session(conn, user["id"])
    full_user = get_current_user_from_token(conn, token)
    conn.close()

    return {
        "success": True,
        "session_token": token,
        "token": token,
        "user": full_user
    }

@router.get("/me")
def get_me(user: dict = Depends(get_current_user)):
    return {"user": user}

@router.post("/logout")
def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        conn = get_db()
        revoke_session(conn, token)
        conn.close()
    return {"success": True, "message": "Disconnesso con successo."}

@router.post("/change-password")
def change_password(req: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, salt FROM utenti WHERE id = ?", (user["id"],))
    row = cursor.fetchone()
    if not row or not verify_password(req.current_password, row["password_hash"], row["salt"]):
        conn.close()
        raise HTTPException(status_code=400, detail="Password attuale non corretta.")

    new_hash, new_salt = hash_password(req.new_password)
    cursor.execute("""
        UPDATE utenti
        SET password_hash = ?, salt = ?
        WHERE id = ?
    """, (new_hash, new_salt, user["id"]))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Password aggiornata con successo."}
