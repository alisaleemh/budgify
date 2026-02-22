import base64

from transaction_tracker import web


def test_password_encode_decode_roundtrip():
    key = "Altaf Hussain"
    password = "s3cr3t-pass"
    encoded = web._encode_password(password, key)
    assert encoded.startswith("enc:")
    decoded = web._decode_password(encoded, key)
    assert decoded == password


def test_extract_auth_password_basic():
    creds = base64.b64encode(b"user:pass123").decode("utf-8")
    header = f"Basic {creds}"
    assert web._extract_auth_password(header) == "pass123"


def test_extract_auth_password_bearer():
    assert web._extract_auth_password("Bearer token-value") == "token-value"


def test_extract_auth_password_invalid():
    assert web._extract_auth_password("Basic not-base64!!") is None
    assert web._extract_auth_password("Something else") is None


def test_get_categories_prefers_plural_param_and_dedupes():
    query = {
        "category": ["groceries"],
        "categories": ["groceries,restaurants", "restaurants", "  ", "car"],
    }
    assert web._get_categories(query) == ["groceries", "restaurants", "car"]


def test_get_categories_uses_legacy_category_param():
    query = {"category": ["groceries", " restaurants ", "groceries"]}
    assert web._get_categories(query) == ["groceries", "restaurants"]


def test_render_index_html_uses_home_env(monkeypatch):
    monkeypatch.setenv("BUDGIFY_UI_HOME_NAME", "Ali's Home")
    monkeypatch.setenv("BUDGIFY_UI_TITLE_TEMPLATE", "{app} | {home}")

    rendered = web._render_index_html("<title>{{APP_TITLE}}</title><h1>{{APP_HEADLINE}}</h1>")

    assert "<title>Budgify | Ali&#x27;s Home</title>" in rendered
    assert "<h1>Ali&#x27;s Home spending, powered by Budgify.</h1>" in rendered
