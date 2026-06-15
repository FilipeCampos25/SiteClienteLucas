from __future__ import annotations

import re

from starlette.requests import Request

from conftest import extract_csrf_token
from rate_limit import LoginRateLimiter, client_ip


def login_admin(app_client: object) -> str:
    login_page = app_client.get("/admin/login")
    csrf_token = extract_csrf_token(login_page.text)
    login_response = app_client.post(
        "/admin/login",
        data={
            "csrf_token": csrf_token,
            "username": "test-admin",
            "password": "test-admin-password",
        },
        follow_redirects=False,
    )
    assert login_response.status_code == 303
    admin_page = app_client.get("/admin")
    return extract_csrf_token(admin_page.text)


def test_login_requires_csrf(app_client: object) -> None:
    response = app_client.post(
        "/admin/login",
        data={"username": "test-admin", "password": "test-admin-password"},
    )
    assert response.status_code == 403


def test_admin_mutations_require_csrf_and_accept_header(app_client: object) -> None:
    authenticated_csrf_token = login_admin(app_client)

    missing_token = app_client.delete("/admin/produto/999")
    assert missing_token.status_code == 403

    valid_token = app_client.delete(
        "/admin/produto/999",
        headers={"X-CSRF-Token": authenticated_csrf_token},
    )
    assert valid_token.status_code == 404

    create_category = app_client.post(
        "/admin/categoria",
        data={
            "csrf_token": authenticated_csrf_token,
            "slug": "categoria-teste",
            "nome": "Categoria teste",
            "nome_exibicao": "Categoria teste",
            "subtitulo_exibicao": "",
            "ordem_exibicao": "99",
        },
        files={"imagem": ("", b"", "application/octet-stream")},
        follow_redirects=False,
    )
    assert create_category.status_code == 303


def test_all_rendered_admin_forms_include_csrf(app_client: object) -> None:
    login_admin(app_client)

    for path in ["/admin/catalogo", "/admin/frontend"]:
        response = app_client.get(path)
        forms = re.findall(r"<form\b.*?</form>", response.text, flags=re.DOTALL)
        admin_forms = [form for form in forms if 'action="/admin/' in form]
        assert admin_forms
        assert all('name="csrf_token"' in form for form in admin_forms)


def test_search_and_cart_are_hidden_only_on_admin_routes(app_client: object) -> None:
    login_page = app_client.get("/admin/login")
    assert 'class="search-container"' not in login_page.text
    assert 'class="header-actions"' not in login_page.text
    assert 'id="carrinhoModal"' not in login_page.text

    login_admin(app_client)
    for path in ["/admin", "/admin/catalogo", "/admin/frontend"]:
        response = app_client.get(path)
        assert response.status_code == 200
        assert 'class="search-container"' not in response.text
        assert 'class="header-actions"' not in response.text
        assert 'id="carrinhoModal"' not in response.text

    for path in ["/", "/quem-somos", "/produtos", "/contato"]:
        assert app_client.get(path).status_code == 200

    import main

    public_request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/public-preview",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 123),
        }
    )
    public_base = main.templates.TemplateResponse(
        "base.html",
        {"request": public_request},
    ).body.decode()
    assert 'class="search-container"' in public_base
    assert 'class="header-actions"' in public_base
    assert 'id="carrinhoModal"' in public_base


def test_public_whatsapp_endpoint_does_not_require_csrf(app_client: object) -> None:
    response = app_client.post("/api/whatsapp", json=[])
    assert response.status_code == 200
    assert "url" in response.json()


def test_login_is_blocked_after_five_failures(app_client: object) -> None:
    login_page = app_client.get("/admin/login")
    csrf_token = extract_csrf_token(login_page.text)

    for _ in range(5):
        response = app_client.post(
            "/admin/login",
            data={
                "csrf_token": csrf_token,
                "username": "test-admin",
                "password": "wrong-password",
            },
        )
        assert response.status_code == 200

    blocked = app_client.post(
        "/admin/login",
        data={
            "csrf_token": csrf_token,
            "username": "test-admin",
            "password": "wrong-password",
        },
    )
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    assert "Tente novamente mais tarde" in blocked.text


def test_rate_limit_reset_clears_failures() -> None:
    now = [1000.0]
    limiter = LoginRateLimiter(clock=lambda: now[0])

    for _ in range(4):
        limiter.record_failure("127.0.0.1")
    limiter.reset("127.0.0.1")
    for _ in range(4):
        limiter.record_failure("127.0.0.1")

    assert limiter.retry_after("127.0.0.1") == 0


def test_trusted_proxy_uses_last_valid_forwarded_address() -> None:
    request = Request(
        {
            "type": "http",
            "headers": [
                (
                    b"x-forwarded-for",
                    b"203.0.113.10, invalid-address, 198.51.100.20",
                )
            ],
            "client": ("127.0.0.1", 1234),
        }
    )

    assert client_ip(request, trust_proxy_headers=True) == "198.51.100.20"
    assert client_ip(request, trust_proxy_headers=False) == "127.0.0.1"
