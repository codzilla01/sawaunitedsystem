-- MFA secrets are application-encrypted with MFA_ENCRYPTION_KEY; never store raw TOTP secrets.
ALTER TABLE users
    ADD COLUMN mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN mfa_secret_encrypted VARCHAR(500),
    ADD COLUMN mfa_pending_secret_encrypted VARCHAR(500),
    ADD COLUMN mfa_last_counter INTEGER NOT NULL DEFAULT -1;

ALTER TABLE session_tokens
    ADD COLUMN mfa_verified BOOLEAN NOT NULL DEFAULT FALSE;
