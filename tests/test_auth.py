def test_register_login_me_flow(client):
    r = client.post("/api/v1/auth/register",
                    json={"username": "zhangsan", "password": "pass12345"})
    assert r.status_code == 201, r.text
    assert r.json()["username"] == "zhangsan"

    # 重复用户名 → 409
    r = client.post("/api/v1/auth/register",
                    json={"username": "zhangsan", "password": "pass12345"})
    assert r.status_code == 409

    # 密码错误 → 401，且不区分用户名与密码错误
    r = client.post("/api/v1/auth/login",
                    json={"username": "zhangsan", "password": "wrong-pass"})
    assert r.status_code == 401

    r = client.post("/api/v1/auth/login",
                    json={"username": "zhangsan", "password": "pass12345"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    assert r.json()["token_type"] == "bearer"

    # 无 token → 401；带 token → 当前用户
    assert client.get("/api/v1/auth/me").status_code == 401
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == "zhangsan"

    # 伪造 token → 401
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer fake.token.here"})
    assert r.status_code == 401


def test_register_validation(client):
    # 用户名太短
    r = client.post("/api/v1/auth/register",
                    json={"username": "ab", "password": "pass12345"})
    assert r.status_code == 422
    # 用户名含非法字符
    r = client.post("/api/v1/auth/register",
                    json={"username": "bad name!", "password": "pass12345"})
    assert r.status_code == 422
    # 密码太短（少于 4 位）
    r = client.post("/api/v1/auth/register",
                    json={"username": "ok_name", "password": "abc"})
    assert r.status_code == 422


def test_security_primitives():
    from app.core.security import (
        create_access_token,
        decode_token,
        hash_password,
        verify_password,
    )

    hashed = hash_password("secret-pass")
    assert hashed != "secret-pass"
    assert verify_password("secret-pass", hashed)
    assert not verify_password("bad-pass", hashed)

    token = create_access_token(42)
    assert decode_token(token) == 42
