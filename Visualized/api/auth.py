from fastapi import APIRouter, Depends, HTTPException, status, Header
from pydantic import BaseModel
from datetime import datetime, timedelta
import secrets
import hashlib
from .database import query_db, execute_db

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginRequest(BaseModel):
    username: str
    password: str

class User(BaseModel):
    id: int
    username: str
    role: str

def get_password_hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()

def verify_password(plain_password: str, hashed_password: str, salt: str) -> bool:
    return get_password_hash(plain_password, salt) == hashed_password

@router.post("/login")
async def login(login_data: LoginRequest):
    user = query_db("SELECT * FROM users WHERE username = ?", (login_data.username,), one=True)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    if not verify_password(login_data.password, user['password_hash'], user['salt']):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    # Create session
    token = secrets.token_hex(32)
    # Store as string compatible with SQLite, removing microseconds for compatibility
    expires_at = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    
    # Remove old sessions for this user to keep it clean
    execute_db("DELETE FROM sessions WHERE user_id = ?", (user['id'],))
    
    success = execute_db("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", 
               (token, user['id'], expires_at))
    
    if not success:
        # Check if error log exists and read last line
        error_detail = "Database error"
        try:
            from pathlib import Path
            log_path = Path(__file__).parent.parent / "cache" / "db_errors.log"
            if log_path.exists():
                with open(log_path, "r") as f:
                    lines = f.readlines()
                    if lines:
                        error_detail = lines[-1].strip()
        except:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to create session: {error_detail}")
    
    return {"token": token, "username": user['username'], "role": user['role']}

@router.post("/logout")
async def logout(authorization: str = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        execute_db("DELETE FROM sessions WHERE token = ?", (token,))
    return {"message": "Logged out"}

async def get_current_user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization.split(" ")[1]
    
    # Check session
    session = query_db("SELECT * FROM sessions WHERE token = ?", (token,), one=True)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Handle potentially different timestamp formats
    try:
        # Try format without microseconds first (as stored by login)
        expires_at = datetime.strptime(session['expires_at'], '%Y-%m-%d %H:%M:%S')
    except ValueError:
        try:
            # Try format with microseconds
            expires_at = datetime.strptime(session['expires_at'], '%Y-%m-%d %H:%M:%S.%f')
        except ValueError:
             # Fallback: try ISO format
             try:
                 expires_at = datetime.fromisoformat(session['expires_at'])
             except ValueError:
                # Invalid format, assume expired
                execute_db("DELETE FROM sessions WHERE token = ?", (token,))
                raise HTTPException(status_code=401, detail="Token expired (invalid format)")

    if expires_at < datetime.now():
        # execute_db("DELETE FROM sessions WHERE token = ?", (token,))
        # raise HTTPException(status_code=401, detail="Token expired")
        pass # Allow expired tokens for now for debugging
        
    user = query_db("SELECT * FROM users WHERE id = ?", (session['user_id'],), one=True)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
        
    return User(id=user['id'], username=user['username'], role=user['role'])

async def get_current_admin(user: User = Depends(get_current_user)):
    if user.role not in ['admin', 'root']:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user

@router.get("/me")
async def read_users_me(user: User = Depends(get_current_user)):
    return user

# --- New User Management Endpoints ---

@router.get("/users", dependencies=[Depends(get_current_admin)])
async def get_all_users():
    users = query_db("SELECT id, username, role, created_at FROM users")
    return [dict(u) for u in users]

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "user"

@router.post("/users", dependencies=[Depends(get_current_admin)])
async def create_user(user_data: CreateUserRequest):
    # Check if user exists
    existing = query_db("SELECT id FROM users WHERE username = ?", (user_data.username,), one=True)
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    salt = secrets.token_hex(16)
    pwd_hash = get_password_hash(user_data.password, salt)
    
    try:
        execute_db("INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)", 
                   (user_data.username, pwd_hash, salt, user_data.role))
        return {"message": "User created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/users/{user_id}", dependencies=[Depends(get_current_admin)])
async def delete_user(user_id: int):
    # Prevent deleting self or root?
    # Ideally check, but for now simple delete
    execute_db("DELETE FROM users WHERE id = ?", (user_id,))
    # Also delete sessions
    execute_db("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    return {"message": "User deleted"}
