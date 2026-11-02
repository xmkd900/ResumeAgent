"""鉴权依赖：从 Bearer token 解析当前用户，供需要登录的接口注入。"""

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(status_code=401, detail="登录已过期，请重新登录")
    try:
        user_id = decode_token(token)
    except JWTError:
        raise unauthorized
    user = db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user
