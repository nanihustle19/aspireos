"""Run against a freshly migrated, disposable PostgreSQL database.

From backend, run: python -m unittest discover -s tests -p postgres_integration.py
"""
import asyncio
import re
import unittest
from uuid import uuid4

import httpx
import pyotp
from sqlalchemy import select

from app.database import async_session, engine
from app.main import app
from app.models.audit import AuditLog, EmailOutbox
from app.models.organization import Organization
from app.models.user import Invitation, User
from app.services.auth_service import hash_password, make_token

PASSWORD = "Integration@123"
NEW_PASSWORD = "Integration@456"


class PostgreSQLIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.suffix = uuid4().hex[:12]
        self.secret = pyotp.random_base32()
        self.platform = f"platform-{self.suffix}@example.test"
        self.peer = f"peer-{self.suffix}@example.test"
        async with async_session.begin() as db:
            org = Organization(name="Integration", slug=f"integration-{self.suffix}")
            db.add(org)
            await db.flush()
            for email in (self.platform, self.peer):
                db.add(User(
                    organization_id=org.id, email=email, name=email, role="ADMIN",
                    status="ACTIVE", password_hash=hash_password(PASSWORD),
                    mfa_enabled=True, mfa_secret=self.secret,
                    is_platform_admin=email == self.platform,
                ))
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        await engine.dispose()

    async def call(self, method, path, body=None, *, headers=None, status=200):
        response = await self.client.request(method, f"/api{path}", json=body, headers=headers)
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    async def challenge(self, email, password=PASSWORD):
        return await self.call("POST", "/auth/login", {"email": email, "password": password})

    async def verify(self, challenge, secret, *, status=200):
        result = await self.call("POST", "/auth/mfa/verify", {
            "mfa_token": challenge["mfa_token"], "code": pyotp.TOTP(secret).now(),
        }, status=status)
        return {"Authorization": f"Bearer {result['access_token']}"} if status == 200 else result

    async def test_recovery_onboarding_and_tenant_isolation(self):
        platform_headers = await self.verify(await self.challenge(self.platform), self.secret)
        peer_headers = await self.verify(await self.challenge(self.peer), self.secret)
        peer_id = (await self.call("GET", "/auth/me", headers=peer_headers))["user"]["id"]
        callback_proof = make_token(peer_id, "google-callback", 1, {"sv": 0})
        google = await self.call("POST", "/auth/google/session", {"session_id": callback_proof})
        self.assertTrue(google["mfa_required"])
        self.assertNotIn("access_token", google)
        stale_challenge = await self.challenge(self.peer)
        await self.call("POST", f"/users/{peer_id}/reset-mfa", {"reason": "Lost phone"}, headers=platform_headers)
        async with async_session() as db:
            reset_log = await db.scalar(select(AuditLog).where(
                AuditLog.action == "MFA_RESET", AuditLog.entity_id == peer_id,
            ))
            self.assertEqual((reset_log.actor_name, reset_log.reason), (self.platform, "Lost phone"))
            self.assertIsNotNone(reset_log.created_at)
        await self.call("GET", "/auth/me", headers=peer_headers, status=401)
        await self.call("POST", "/auth/google/session", {"session_id": callback_proof}, status=401)
        await self.verify(stale_challenge, self.secret, status=401)
        enrollment = await self.challenge(self.peer)
        peer_headers = await self.verify(enrollment, enrollment["secret"])

        request = {"email": self.peer}
        known = await self.call("POST", "/auth/forgot-password", request)
        unknown = await self.call("POST", "/auth/forgot-password", {"email": "missing@example.test"})
        self.assertEqual(known, unknown)
        self.assertEqual(await self.call("POST", "/auth/forgot-password", request), known)
        cross_site = await self.client.post("/api/auth/forgot-password", json=request, headers={"Origin": "https://untrusted.example"})
        self.assertEqual(cross_site.status_code, 403)
        async with async_session() as db:
            messages = (await db.scalars(select(EmailOutbox).where(
                EmailOutbox.to == self.peer, EmailOutbox.subject == "Reset your AspireOs password",
            ))).all()
            self.assertEqual(len(messages), 1)
            token = re.search(r"token=([\w-]+)", messages[0].body)[1]
        await self.call("POST", "/auth/reset-password/check", {"token": token})
        reset = {"token": token, "password": NEW_PASSWORD}
        responses = await asyncio.gather(*(
            self.client.post("/api/auth/reset-password", json=reset) for _ in range(2)
        ))
        self.assertEqual(sorted(response.status_code for response in responses), [200, 422])
        await self.call("GET", "/auth/me", headers=peer_headers, status=401)
        await self.call("POST", "/auth/login", {"email": self.peer, "password": PASSWORD}, status=401)
        peer_headers = await self.verify(await self.challenge(self.peer, NEW_PASSWORD), enrollment["secret"])

        org_input = {
            "name": "Client Consultancy", "slug": f"client-{self.suffix}",
            "admin_name": "Client Admin", "admin_email": f"client-{self.suffix}@example.test",
            "default_groups": ["Core Bench", "Second Group"],
        }
        await self.call("POST", "/platform/organizations", org_input, headers=peer_headers, status=403)
        org = await self.call("POST", "/platform/organizations", org_input, headers=platform_headers)
        availability = f"/platform/organizations/slug-availability?slug={org_input['slug']}"
        self.assertEqual(await self.call("GET", availability, headers=platform_headers), {"available": False})
        await self.call("GET", availability, headers=peer_headers, status=403)
        async with async_session.begin() as db:
            invite = await db.scalar(select(Invitation).where(Invitation.organization_id == org["id"]))
            message = await db.get(EmailOutbox, invite.delivery_id)
            message.status = "FAILED"
            message.attempts = 5
        retry = f"/platform/organizations/{org['id']}/retry-invite"
        await self.call("POST", retry, headers=peer_headers, status=403)
        await self.call("POST", retry, headers=platform_headers)
        async with async_session() as db:
            message = await db.get(EmailOutbox, invite.delivery_id)
            self.assertEqual((message.status, message.attempts), ("PENDING", 0))
        await self.call("POST", "/platform/organizations", org_input, headers=platform_headers, status=409)
        activation = await self.call("POST", "/auth/activate", {
            "token": org["activation_path"].split("token=")[1], "password": PASSWORD,
        })
        client_headers = await self.verify(activation, activation["secret"])
        self.assertTrue(activation["qr_image"].startswith("data:image/svg+xml;base64,"))
        temp_org = await self.call("POST", "/platform/organizations", {
            **org_input, "slug": f"temp-{self.suffix}", "admin_email": f"temp-{self.suffix}@example.test",
            "industry": "Recruitment", "size": "11–50", "temporary_password": "Temporary@123",
        }, headers=platform_headers)
        self.assertIsNone(temp_org["invite_status"])
        temp_activation = {"token": temp_org["activation_path"].split("token=")[1], "password": PASSWORD}
        await self.call("POST", "/auth/activate", temp_activation, status=422)
        temp_activation["temporary_password"] = "Temporary@123"
        self.assertTrue((await self.call("POST", "/auth/activate", temp_activation))["mfa_setup_required"])
        await self.call("POST", "/auth/activate", temp_activation, status=422)
        me = await self.call("GET", "/auth/me", headers=client_headers)
        self.assertEqual(me["organization"]["id"], org["id"])
        await self.call("POST", f"/users/{peer_id}/reset-mfa", {"reason": "Lost phone"}, headers=client_headers, status=404)
        await self.call("GET", "/platform/organizations", headers=client_headers, status=403)

        groups = await self.call("GET", "/groups", headers=client_headers)
        candidate = await self.call("POST", "/candidates", {
            "first_name": "Ada", "last_name": "Lovelace", "group_id": groups[0]["id"],
        }, headers=client_headers)
        self.assertEqual(candidate["status"], "BENCH")
        report = await self.call("GET", "/reports/summary", headers=client_headers)
        self.assertEqual([row["id"] for row in report["bench_aging"]], [candidate["id"]])
        self.assertEqual(report["recruiter_activity"], [])
        other_report = await self.call("GET", "/reports/summary", headers=platform_headers)
        self.assertNotIn(candidate["id"], [row["id"] for row in other_report["bench_aging"]])
        path = f"/candidates/{candidate['id']}"
        await self.call("GET", path, headers=platform_headers, status=404)
        candidate = await self.call("PATCH", path, {
            "version": candidate["version"], "location": "London",
        }, headers=client_headers)
        self.assertEqual(candidate["location"], "London")
        candidate = await self.call("POST", f"{path}/transfer", {
            "version": candidate["version"], "to_group_id": groups[1]["id"], "reason": "Team change",
        }, headers=client_headers)
        self.assertEqual(candidate["current_group_id"], groups[1]["id"])
        candidate = await self.call("POST", f"{path}/transition", {
            "version": candidate["version"], "to_status": "ON_HOLD", "reason": "Unavailable",
        }, headers=client_headers)
        self.assertEqual(candidate["status"], "ON_HOLD")
        archived = await self.call("POST", f"{path}/archive", {
            "version": candidate["version"], "reason": "Closed",
        }, headers=client_headers)
        self.assertEqual(archived["status"], "ARCHIVED")

