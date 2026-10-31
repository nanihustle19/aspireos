# Auth Testing Playbook (BenchOS)
- Password login: POST /api/auth/login. Admin accounts require TOTP: response {mfa_required, mfa_token}; then POST /api/auth/mfa/verify {mfa_token, code} where code = pyotp.TOTP('B3ES4OQPDKPZ452SAHMCNNB3FOL2RRXU').now().
- Non-admin login returns {user, access_token, refresh_token}; use `Authorization: Bearer <access_token>`.
- Invitation flow: POST /api/invitations (admin/ops) -> activation_path /activate?token=...; GET /api/auth/invitations/{token}; POST /api/auth/activate {token,password,name}.
- Google login (Emergent) is invitation-only: unknown emails get 403. Cannot be fully automated.
- Brute force: 5 failed attempts -> 429 for 15 min (per ip+email).
- Deactivating a user bumps session_version -> existing tokens get 401.
- See /app/memory/test_credentials.md for accounts.
