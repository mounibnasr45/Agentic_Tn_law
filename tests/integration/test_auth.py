"""Auth end-to-end against a real Postgres: register, login, rotate, replay, revoke."""
import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.main import create_app
from tests.fakes import FakeEmbedder

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="no DATABASE_URL; integration tests need Postgres"
)

CREDENTIALS = {"email": "avocat@example.tn", "password": "correct-horse-battery"}


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE users, refresh_tokens RESTART IDENTITY CASCADE"))
    await engine.dispose()

    app = create_app()

    # The real lifespan loads a 450MB SentenceTransformer. Running it per test loaded the
    # model ~20 times and killed the process with a Windows access violation — and none of
    # these tests touch the embedder anyway. Injecting the fake instead is the whole point
    # of depending on the Embedder Protocol rather than on SentenceTransformer: the auth
    # suite runs in milliseconds with no model, no download, and no GPU-adjacent memory.
    app.state.embedder = FakeEmbedder()

    # ASGITransport drives the app in-process: no port, no uvicorn, no sleep-and-poll.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def register(client) -> dict:
    response = await client.post("/api/auth/register", json=CREDENTIALS)
    assert response.status_code == 201
    return response.json()


class TestRegistration:
    async def test_registering_returns_a_token_pair(self, client):
        tokens = await register(client)

        assert tokens["access_token"]
        assert tokens["refresh_token"]
        assert tokens["token_type"] == "bearer"
        assert tokens["expires_in"] == 15 * 60

    async def test_the_same_email_cannot_register_twice(self, client):
        await register(client)

        response = await client.post("/api/auth/register", json=CREDENTIALS)

        assert response.status_code == 409

    async def test_a_short_password_is_rejected_before_it_reaches_the_database(self, client):
        response = await client.post(
            "/api/auth/register", json={"email": "x@example.tn", "password": "short"}
        )

        assert response.status_code == 422

    async def test_the_password_is_never_returned_or_echoed(self, client):
        tokens = await register(client)

        assert CREDENTIALS["password"] not in str(tokens)

    async def test_the_stored_hash_is_argon2id_not_a_bare_sha256(self, client):
        await register(client)

        engine = create_async_engine(os.environ["DATABASE_URL"])
        async with engine.connect() as conn:
            stored = (await conn.execute(text("SELECT password_hash FROM users"))).scalar_one()
        await engine.dispose()

        # A single fast hash is what a GPU cracks at billions of guesses/sec. Password
        # hashing must be deliberately slow and memory-hard.
        assert stored.startswith("$argon2id$")
        assert CREDENTIALS["password"] not in stored


class TestLogin:
    async def test_correct_credentials_return_tokens(self, client):
        await register(client)

        response = await client.post("/api/auth/login", json=CREDENTIALS)

        assert response.status_code == 200
        assert response.json()["access_token"]

    async def test_a_wrong_password_is_rejected(self, client):
        await register(client)

        response = await client.post(
            "/api/auth/login", json={**CREDENTIALS, "password": "wrong-password-here"}
        )

        assert response.status_code == 401

    async def test_an_unknown_email_gives_the_same_answer_as_a_wrong_password(self, client):
        await register(client)

        unknown = await client.post(
            "/api/auth/login",
            json={"email": "nobody@example.tn", "password": "correct-horse-battery"},
        )
        wrong = await client.post(
            "/api/auth/login", json={**CREDENTIALS, "password": "wrong-password-here"}
        )

        # Identical status AND identical body. Any difference is a user-enumeration
        # oracle: an attacker learns which addresses are registered.
        assert unknown.status_code == wrong.status_code == 401
        assert unknown.json() == wrong.json()


class TestProtectedRoutes:
    async def test_me_requires_a_token(self, client):
        response = await client.get("/api/auth/me")

        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"

    async def test_me_returns_the_authenticated_user(self, client):
        tokens = await register(client)

        response = await client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )

        assert response.status_code == 200
        assert response.json()["email"] == CREDENTIALS["email"]

    async def test_a_garbage_token_is_rejected(self, client):
        response = await client.get(
            "/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"}
        )

        assert response.status_code == 401

    async def test_a_refresh_token_cannot_be_used_as_an_access_token(self, client):
        tokens = await register(client)

        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
        )

        # Refresh tokens are long-lived by design. If one were accepted as an access
        # token, a stolen refresh token would become a 14-day access token and the whole
        # point of a 15-minute access expiry would be gone.
        assert response.status_code == 401


class TestRotation:
    async def test_refreshing_returns_a_new_pair(self, client):
        tokens = await register(client)

        response = await client.post(
            "/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )

        assert response.status_code == 200
        rotated = response.json()
        assert rotated["refresh_token"] != tokens["refresh_token"]

    async def test_the_new_access_token_works(self, client):
        tokens = await register(client)

        rotated = (
            await client.post(
                "/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
            )
        ).json()

        response = await client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {rotated['access_token']}"}
        )

        assert response.status_code == 200

    async def test_the_old_refresh_token_stops_working(self, client):
        """Rotation. Without this, a 'refresh token' is just a 14-day access token."""
        tokens = await register(client)
        await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

        response = await client.post(
            "/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )

        assert response.status_code == 401

    async def test_an_unknown_refresh_token_is_rejected(self, client):
        await register(client)

        response = await client.post(
            "/api/auth/refresh", json={"refresh_token": "never-issued-this"}
        )

        assert response.status_code == 401


class TestReplayDetection:
    async def test_replaying_a_used_token_revokes_the_entire_chain(self, client):
        """The reason the rotation chain exists.

        An already-revoked token means one of two things: the legitimate client is
        retrying, or an attacker stole the token and used it after the client rotated. We
        cannot tell which, so we assume the worse case and revoke everything — the
        attacker's stolen token AND the victim's current one — forcing re-authentication.

        Without the chain, a replayed token would just look "unknown" and the theft would
        be silent.
        """
        original = await register(client)

        # The legitimate client rotates once.
        current = (
            await client.post(
                "/api/auth/refresh", json={"refresh_token": original["refresh_token"]}
            )
        ).json()

        # The attacker replays the token they stole BEFORE that rotation.
        replay = await client.post(
            "/api/auth/refresh", json={"refresh_token": original["refresh_token"]}
        )
        assert replay.status_code == 401

        # And the victim's CURRENT, still-valid token is now dead too. That is the point:
        # we do not know who the thief is, so we log everyone out.
        after = await client.post(
            "/api/auth/refresh", json={"refresh_token": current["refresh_token"]}
        )
        assert after.status_code == 401, "the chain was not revoked — replay went undetected"

    async def test_the_user_can_log_in_again_after_a_chain_revocation(self, client):
        original = await register(client)
        await client.post("/api/auth/refresh", json={"refresh_token": original["refresh_token"]})
        await client.post("/api/auth/refresh", json={"refresh_token": original["refresh_token"]})

        response = await client.post("/api/auth/login", json=CREDENTIALS)

        assert response.status_code == 200


class TestLogout:
    async def test_logout_revokes_the_refresh_token(self, client):
        tokens = await register(client)

        assert (
            await client.post("/api/auth/logout", json={"refresh_token": tokens["refresh_token"]})
        ).status_code == 204

        response = await client.post(
            "/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert response.status_code == 401

    async def test_logout_is_idempotent(self, client):
        tokens = await register(client)
        await client.post("/api/auth/logout", json={"refresh_token": tokens["refresh_token"]})

        # A logout that can fail is a logout users will skip.
        response = await client.post(
            "/api/auth/logout", json={"refresh_token": tokens["refresh_token"]}
        )

        assert response.status_code == 204
