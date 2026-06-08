"""
auth.py
───────
Everything related to authentication lives here:
  - Password hashing
  - JWT token creation and decoding
  - get_current_user() dependency (used on every protected route)

What is JWT?
  JWT = JSON Web Token. It's a signed "hall pass" the server gives
  you after login. You send it with every future request.
  The server doesn't need to hit the database to check who you are —
  it just verifies the signature on the token.

  Structure:   HEADER . PAYLOAD . SIGNATURE
               (base64)  (base64)  (hmac-sha256)

  Anyone can READ the payload (it's just base64).
  Nobody can FAKE the signature without the SECRET_KEY.
"""

from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import hashlib
import jwt       # pip install pyjwt

from database import UserDB, get_db


# ─────────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────────

SECRET_KEY = "my_super_secret_key_change_in_production"
# ^ In a real app, load this from an environment variable:
#   import os; SECRET_KEY = os.getenv("SECRET_KEY")

ALGORITHM       = "HS256"    # HMAC + SHA-256
TOKEN_EXPIRE_H  = 24         # token valid for 24 hours


# ─────────────────────────────────────────────────────────────────
#  PASSWORD HASHING
#
#  sha256 is a one-way function:
#    "password123" → "ef92b9..." (always the same output)
#    But you can't go from "ef92b9..." back to "password123".
#
#  To verify a login: hash what the user typed, compare to stored hash.
#  If they match → correct password.
# ─────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    return hash_password(plain) == hashed


# ─────────────────────────────────────────────────────────────────
#  JWT TOKEN CREATION
#
#  payload = the data packed INSIDE the token
#  jwt.encode() signs it with SECRET_KEY so nobody can tamper
# ─────────────────────────────────────────────────────────────────

def create_jwt_token(user_id: int, username: str) -> str:
    payload = {
        "user_id":  user_id,
        "username": username,
        "exp":      datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_H)
        # ↑ "exp" is a standard JWT claim. PyJWT checks this automatically
        #   and raises ExpiredSignatureError if the token is past this time.
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ─────────────────────────────────────────────────────────────────
#  JWT TOKEN DECODING
#
#  jwt.decode() does two things at once:
#    1. Verifies the signature hasn't been tampered with
#    2. Checks the "exp" field hasn't expired
#  If either fails → raises an exception
# ─────────────────────────────────────────────────────────────────

def decode_jwt_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired. Please login again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")


# ─────────────────────────────────────────────────────────────────
#  HTTPBearer
#
#  This tells FastAPI: "look for a header that says:
#    Authorization: Bearer <token>
#  and give me what's after 'Bearer'."
# ─────────────────────────────────────────────────────────────────

security = HTTPBearer()


# ─────────────────────────────────────────────────────────────────
#  get_current_user()  —  FastAPI dependency
#
#  Any route that needs the logged-in user adds this:
#    current_user: UserDB = Depends(get_current_user)
#
#  FastAPI will automatically:
#    1. Extract the token from the Authorization header
#    2. Call this function
#    3. Pass the returned UserDB object into the route as current_user
#
#  If the token is missing/invalid/expired → 401 error before the
#  route even runs.
# ─────────────────────────────────────────────────────────────────

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db:          Session                      = Depends(get_db)
) -> UserDB:
    token   = credentials.credentials          # the raw token string
    payload = decode_jwt_token(token)          # verify + unpack
    user    = db.query(UserDB).filter(UserDB.id == payload["user_id"]).first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found.")

    return user                                # this becomes `current_user` in the route
