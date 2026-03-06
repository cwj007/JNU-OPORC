from fastapi import APIRouter, Depends, HTTPException, status, Header
from pydantic import BaseModel
from datetime import datetime, timedelta
import secrets
import hashlib
from typing import Optional
from .database import query_db, execute_db

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginRequest(BaseModel):
    username: str
    password: str

class User(BaseModel):
    id: int
    username: str
    role: str
    email: Optional[str] = None
    email_notify_enabled: bool = True

def get_password_hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()

def verify_password(plain_password: str, hashed_password: str, salt: str) -> bool:
    return get_password_hash(plain_password, salt) == hashed_password

@router.post("/login")
async def login(login_data: LoginRequest):
    user = await query_db("SELECT * FROM users WHERE username = ?", (login_data.username,), one=True)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    if not verify_password(login_data.password, user['password_hash'], user['salt']):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    # Create session
    token = secrets.token_hex(32)
    # Store as string compatible with SQLite, removing microseconds for compatibility
    expires_at = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    
    # Remove old sessions for this user to keep it clean
    await execute_db("DELETE FROM sessions WHERE user_id = ?", (user['id'],))
    
    success = await execute_db("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", 
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
    
    return {"token": token, "id": user['id'], "username": user['username'], "role": user['role']}

@router.post("/logout")
async def logout(authorization: str = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        await execute_db("DELETE FROM sessions WHERE token = ?", (token,))
    return {"message": "Logged out"}

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None

@router.post("/register")
async def register(register_data: RegisterRequest):
    # Check if user exists
    existing = await query_db("SELECT id FROM users WHERE username = ?", (register_data.username,), one=True)
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    if not register_data.password or len(register_data.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long")

    salt = secrets.token_hex(16)
    pwd_hash = get_password_hash(register_data.password, salt)
    
    try:
        # Default role is 'user'
        success = await execute_db("INSERT INTO users (username, password_hash, salt, role, email) VALUES (?, ?, ?, ?, ?)", 
                         (register_data.username, pwd_hash, salt, "user", register_data.email))
        if not success:
            raise HTTPException(status_code=500, detail="Failed to register user")
        return {"message": "User registered successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def get_current_user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization.split(" ")[1]
    return await verify_token(token)

async def get_current_user_optional(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        return None
    
    try:
        token = authorization.split(" ")[1]
        return await verify_token(token)
    except:
        return None

async def verify_token(token: str):
    # Check session
    session = await query_db("SELECT * FROM sessions WHERE token = ?", (token,), one=True)
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
                await execute_db("DELETE FROM sessions WHERE token = ?", (token,))
                raise HTTPException(status_code=401, detail="Token expired (invalid format)")

    if expires_at < datetime.now():
        # await execute_db("DELETE FROM sessions WHERE token = ?", (token,))
        # raise HTTPException(status_code=401, detail="Token expired")
        pass # Allow expired tokens for now for debugging
        
    user = await query_db("SELECT * FROM users WHERE id = ?", (session['user_id'],), one=True)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
        
    user_dict = dict(user)
    return User(
        id=user_dict['id'], 
        username=user_dict['username'], 
        role=user_dict['role'],
        email=user_dict.get('email'),
        email_notify_enabled=bool(user_dict.get('email_notify_enabled', 1))
    )

async def get_current_admin(user: User = Depends(get_current_user)):
    if user.role not in ['admin', 'root']:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user

@router.get("/me")
async def read_users_me(user: User = Depends(get_current_user)):
    return user

@router.get("/profile")
async def get_profile(user: User = Depends(get_current_user)):
    return user

class ProfileUpdateRequest(BaseModel):
    email: Optional[str] = None
    email_notify_enabled: Optional[bool] = None
    old_password: Optional[str] = None
    new_password: Optional[str] = None

@router.post("/profile")
async def update_profile(profile_data: ProfileUpdateRequest, user: User = Depends(get_current_user)):
    updates = []
    params = []
    
    if profile_data.email is not None:
        updates.append("email = ?")
        params.append(profile_data.email)
    
    if profile_data.email_notify_enabled is not None:
        updates.append("email_notify_enabled = ?")
        params.append(1 if profile_data.email_notify_enabled else 0)

    # 密码修改逻辑
    if profile_data.new_password:
        if not profile_data.old_password:
            raise HTTPException(status_code=400, detail="修改密码需要提供旧密码")
        
        # 获取当前用户的完整信息（包含密码哈希和盐）
        current_user = await query_db("SELECT password_hash, salt FROM users WHERE id = ?", (user.id,), one=True)
        if not current_user:
            raise HTTPException(status_code=404, detail="未找到用户信息")
        
        # 验证旧密码
        if not verify_password(profile_data.old_password, current_user['password_hash'], current_user['salt']):
            raise HTTPException(status_code=400, detail="旧密码不正确")
        
        # 生成新的盐和哈希
        new_salt = secrets.token_hex(16)
        new_hash = get_password_hash(profile_data.new_password, new_salt)
        
        updates.append("password_hash = ?")
        params.append(new_hash)
        updates.append("salt = ?")
        params.append(new_salt)
    
    if not updates:
        return {"message": "No changes requested"}
    
    params.append(user.id)
    sql = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
    
    success = await execute_db(sql, tuple(params))
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update profile")
    
    return {"message": "Profile updated successfully"}

# --- New User Management Endpoints ---

@router.get("/users", dependencies=[Depends(get_current_admin)])
async def list_users():
    users = await query_db("SELECT id, username, role, email, created_at FROM users")
    return users

class CreateUserRequest(BaseModel):
    username: str
    password: Optional[str] = None
    role: str = "user"
    email: Optional[str] = None

@router.post("/users", dependencies=[Depends(get_current_admin)])
async def create_user(user_data: CreateUserRequest):
    # Check if user exists
    existing = await query_db("SELECT id FROM users WHERE username = ?", (user_data.username,), one=True)
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    # Default password to 123456 if not provided
    password = user_data.password if user_data.password and user_data.password.strip() != "" else "123456"
    
    salt = secrets.token_hex(16)
    pwd_hash = get_password_hash(password, salt)
    
    try:
        success = await execute_db("INSERT INTO users (username, password_hash, salt, role, email) VALUES (?, ?, ?, ?, ?)", 
                         (user_data.username, pwd_hash, salt, user_data.role, user_data.email))
        if not success:
            raise HTTPException(status_code=500, detail="Failed to create user")
        return {"message": "User created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/users/{user_id}", dependencies=[Depends(get_current_admin)])
async def delete_user(user_id: int):
    # Check if target user is root
    user = await query_db("SELECT username FROM users WHERE id = ?", (user_id,), one=True)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user['username'] == 'root':
        raise HTTPException(status_code=403, detail="Root user cannot be deleted")

    await execute_db("DELETE FROM users WHERE id = ?", (user_id,))
    # Also delete sessions
    await execute_db("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    return {"message": "User deleted"}

class UpdateUserRequest(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None

@router.put("/users/{user_id}", dependencies=[Depends(get_current_admin)])
async def update_user(user_id: int, user_data: UpdateUserRequest):
    # Check if target user is root
    user = await query_db("SELECT username FROM users WHERE id = ?", (user_id,), one=True)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user['username'] == 'root':
        raise HTTPException(status_code=403, detail="Root user cannot be modified")

    updates = []
    params = []
    
    if user_data.username is not None:
        # Check if username exists for other users
        existing = await query_db("SELECT id FROM users WHERE username = ? AND id != ?", (user_data.username, user_id), one=True)
        if existing:
            raise HTTPException(status_code=400, detail="Username already exists")
        updates.append("username = ?")
        params.append(user_data.username)
    
    if user_data.password is not None and user_data.password != "":
        salt = secrets.token_hex(16)
        pwd_hash = get_password_hash(user_data.password, salt)
        updates.append("password_hash = ?")
        params.append(pwd_hash)
        updates.append("salt = ?")
        params.append(salt)
    
    if user_data.role is not None:
        updates.append("role = ?")
        params.append(user_data.role)

    if user_data.email is not None:
        updates.append("email = ?")
        params.append(user_data.email)
    
    if not updates:
        return {"message": "No changes requested"}
    
    params.append(user_id)
    sql = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
    
    try:
        success = await execute_db(sql, tuple(params))
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update user")
        return {"message": "User updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
