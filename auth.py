from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import hashlib
import jwt      

from database import UserDB, get_db


SECRET_KEY = "my_super_secret_key_change_in_production"


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()



def verify_password(plain: str, hashed: str) -> bool:
    return hash_password(plain)== hashed


def create_jwt_token(user_id: int, username: str) -> str:
    payload = {
        "user_id":  user_id,
        "username": username,
        "exp":  datetime.now(timezone.utc) + timedelta(hours=24)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

#  JWT TOKEN DECODING


def decode_jwt_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired. Please login again.")
    except jwt.InvalidTokenError:
        
        raise HTTPException(status_code=401, detail="Invalid token.")


security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials =Depends(security),
    db: Session = Depends(get_db)):
    token   = credentials.credentials         
     
    payload = decode_jwt_token(token)          
    user = db.query(UserDB).filter(UserDB.id== payload["user_id"]).first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found.")

    return user  

