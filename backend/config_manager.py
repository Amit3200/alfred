"""Load, save, and merge Alfred configuration and secrets."""

from __future__ import annotations

import secrets
from pathlib import Path

import yaml

from backend.models.config import (
    AlfredConfig,
    AlfredSecrets,
    default_ai_providers,
    default_config,
)
from backend.paths import config_path, get_data_dir, key_path, playbooks_dir, secrets_path
from backend.secrets import decrypt_secrets, encrypt_secrets, ensure_encryption_key


class ConfigManager:
    """Manages config.yaml (plain) and secrets.enc (encrypted)."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = get_data_dir(data_dir)
        self._config_path = config_path(self.data_dir)
        self._secrets_path = secrets_path(self.data_dir)
        self._key_path = key_path(self.data_dir)

    def is_initialized(self) -> bool:
        return self._config_path.exists() and self.load_config().initialized

    def init(
        self,
        force: bool = False,
        username: str | None = None,
        password: str | None = None,
        token: str | None = None,
    ) -> AlfredConfig:
        if self._config_path.exists() and not force:
            config = self.load_config()
            if config.initialized:
                # Patch/ensure username & password
                _ = self.load_secrets()
                return config
        ensure_encryption_key(self._key_path)
        config = default_config()
        config.initialized = True
        
        admin_username = username or "admin"
        
        import secrets as py_secrets
        admin_password = password or py_secrets.token_urlsafe(16)
        admin_token = token or py_secrets.token_urlsafe(32)
        
        config.server.admin_token = admin_token
        config.server.admin_username = admin_username
        config.server.admin_password = admin_password
        
        secrets_obj = AlfredSecrets(
            server_admin_token=admin_token,
            server_admin_username=admin_username,
            server_admin_password=admin_password,
        )
        self.save_merged(config, secrets_obj)
        self._seed_playbooks()
        return config

    def _seed_playbooks(self) -> None:
        """Create `.alfred/playbooks/` with an example file when empty."""
        import shutil

        from backend.paths import bundled_playbooks_dir

        dest = playbooks_dir(self.data_dir)
        dest.mkdir(parents=True, exist_ok=True)
        if any(dest.glob("*.md")):
            return
        example = bundled_playbooks_dir() / "example-slack-summaries.md"
        if example.is_file():
            shutil.copy(example, dest / "slack-summaries.md")

    def load_config(self) -> AlfredConfig:
        if not self._config_path.exists():
            return default_config()
        raw = yaml.safe_load(self._config_path.read_text()) or {}
        config = AlfredConfig.model_validate(raw)
        self._merge_default_providers(config)
        return config

    @staticmethod
    def _merge_default_providers(config: AlfredConfig) -> None:
        """Backfill newly added providers into existing config.yaml files."""
        for name, provider in default_ai_providers().items():
            if name not in config.ai.providers:
                config.ai.providers[name] = provider

    def save_config(self, config: AlfredConfig) -> None:
        payload = config.model_dump(mode="json")
        self._config_path.write_text(yaml.safe_dump(payload, sort_keys=False))

    def load_secrets(self) -> AlfredSecrets:
        if not self._secrets_path.exists():
            return AlfredSecrets()
        ensure_encryption_key(self._key_path)
        secrets_obj = decrypt_secrets(self._secrets_path, self._key_path)
        
        # Patch for existing applications
        modified = False
        if not secrets_obj.server_admin_username:
            secrets_obj.server_admin_username = "admin"
            modified = True
        if not secrets_obj.server_admin_password:
            import secrets as py_secrets
            secrets_obj.server_admin_password = py_secrets.token_urlsafe(16)
            modified = True
        if not secrets_obj.server_admin_token:
            import secrets as py_secrets
            secrets_obj.server_admin_token = py_secrets.token_urlsafe(32)
            modified = True
            
        if modified:
            self.save_secrets(secrets_obj)
            
        return secrets_obj

    def save_secrets(self, secrets_obj: AlfredSecrets) -> None:
        ensure_encryption_key(self._key_path)
        encrypt_secrets(secrets_obj, self._secrets_path, self._key_path)
        try:
            self._secrets_path.chmod(0o600)
            self._key_path.chmod(0o600)
        except OSError:
            pass

    def load_merged(self) -> tuple[AlfredConfig, AlfredSecrets]:
        config = self.load_config()
        secrets_obj = self.load_secrets()
        self._apply_secrets_to_config(config, secrets_obj)
        return config, secrets_obj

    def save_merged(
        self,
        config: AlfredConfig,
        secrets_obj: AlfredSecrets,
    ) -> None:
        self._extract_secrets_from_config(config, secrets_obj)
        self.save_config(config)
        self.save_secrets(secrets_obj)

    def _apply_secrets_to_config(
        self,
        config: AlfredConfig,
        secrets_obj: AlfredSecrets,
    ) -> None:
        config.server.admin_token = secrets_obj.server_admin_token or config.server.admin_token
        config.server.admin_username = secrets_obj.server_admin_username or config.server.admin_username or "admin"
        config.server.admin_password = secrets_obj.server_admin_password or config.server.admin_password
        config.slack.bot_token = secrets_obj.slack_bot_token
        config.slack.signing_secret = secrets_obj.slack_signing_secret
        config.slack.app_token = secrets_obj.slack_app_token
        config.git.token = secrets_obj.git_token
        config.github.webhook_secret = secrets_obj.github_webhook_secret
        config.github.client_secret = secrets_obj.github_client_secret
        config.aws.access_key_id = secrets_obj.aws_access_key_id
        config.aws.secret_access_key = secrets_obj.aws_secret_access_key
        config.jira.api_token = secrets_obj.jira_api_token
        config.google.credentials_json = secrets_obj.google_credentials_json
        config.google.oauth_refresh_token = secrets_obj.google_oauth_refresh_token
        for name, provider in config.ai.providers.items():
            if key := secrets_obj.ai_api_keys.get(name):
                provider.api_key = key

    def _extract_secrets_from_config(
        self,
        config: AlfredConfig,
        secrets_obj: AlfredSecrets,
    ) -> None:
        if config.server.admin_token:
            secrets_obj.server_admin_token = config.server.admin_token
        if config.server.admin_username:
            secrets_obj.server_admin_username = config.server.admin_username
        if config.server.admin_password:
            secrets_obj.server_admin_password = config.server.admin_password
        if config.slack.bot_token:
            secrets_obj.slack_bot_token = config.slack.bot_token
        if config.slack.signing_secret:
            secrets_obj.slack_signing_secret = config.slack.signing_secret
        if config.slack.app_token:
            secrets_obj.slack_app_token = config.slack.app_token
        if config.git.token:
            secrets_obj.git_token = config.git.token
        if config.github.webhook_secret:
            secrets_obj.github_webhook_secret = config.github.webhook_secret
        if config.github.client_secret:
            secrets_obj.github_client_secret = config.github.client_secret
        if config.aws.access_key_id:
            secrets_obj.aws_access_key_id = config.aws.access_key_id
        if config.aws.secret_access_key:
            secrets_obj.aws_secret_access_key = config.aws.secret_access_key
        if config.jira.api_token:
            secrets_obj.jira_api_token = config.jira.api_token
        if config.google.credentials_json:
            secrets_obj.google_credentials_json = config.google.credentials_json
        if config.google.oauth_refresh_token:
            secrets_obj.google_oauth_refresh_token = config.google.oauth_refresh_token
        for name, provider in config.ai.providers.items():
            if provider.api_key:
                secrets_obj.ai_api_keys[name] = provider.api_key
        config.slack.bot_token = ""
        config.slack.signing_secret = ""
        config.slack.app_token = ""
        config.git.token = ""
        config.github.webhook_secret = ""
        config.github.client_secret = ""
        config.aws.access_key_id = ""
        config.aws.secret_access_key = ""
        config.jira.api_token = ""
        config.google.credentials_json = ""
        config.google.oauth_refresh_token = ""
        config.server.admin_token = ""
        config.server.admin_username = ""
        config.server.admin_password = ""
        for provider in config.ai.providers.values():
            provider.api_key = ""

    def public_config(self) -> dict:
        """Config safe for API responses (secrets stripped)."""
        config, _ = self.load_merged()
        self._extract_secrets_from_config(config, AlfredSecrets())
        data = config.model_dump(mode="json")
        data["_secrets_configured"] = self._secrets_status()
        return data

    @staticmethod
    def _mask_secret(value: str, prefix_len: int = 8) -> str | None:
        if not value:
            return None
        if len(value) <= prefix_len:
            return f"{value!r} (too short — paste full token and save)"
        return f"{value[:prefix_len]}…{value[-4:]}"

    def _secrets_status(self) -> dict:
        secrets_obj = self.load_secrets()
        bot = secrets_obj.slack_bot_token
        google_raw = secrets_obj.google_credentials_json
        google_cred_type: str | None = None
        if google_raw.strip():
            try:
                from backend.google.credentials import credentials_json_type

                google_cred_type = credentials_json_type(google_raw)
            except ValueError:
                google_cred_type = "invalid"
        google_connected = bool(
            google_cred_type == "service_account"
            or (
                google_cred_type == "oauth_client"
                and secrets_obj.google_oauth_refresh_token.strip()
            )
        )
        return {
            "slack_bot_token": bool(bot),
            "slack_bot_token_valid": bot.startswith("xoxb-") if bot else False,
            "slack_bot_token_hint": self._mask_secret(bot),
            "slack_signing_secret": bool(secrets_obj.slack_signing_secret),
            "slack_app_token": bool(secrets_obj.slack_app_token),
            "git_token": bool(secrets_obj.git_token),
            "github_webhook_secret": bool(secrets_obj.github_webhook_secret),
            "github_client_secret": bool(secrets_obj.github_client_secret),
            "aws_access_key_id": bool(secrets_obj.aws_access_key_id),
            "aws_secret_access_key": bool(secrets_obj.aws_secret_access_key),
            "jira_api_token": bool(secrets_obj.jira_api_token),
            "google_credentials_json": bool(google_raw.strip()),
            "google_oauth_refresh_token": bool(secrets_obj.google_oauth_refresh_token.strip()),
            "google_credentials_type": google_cred_type,
            "google_oauth_connected": google_connected,
            "server_admin_token": bool(secrets_obj.server_admin_token),
            "server_admin_username": bool(secrets_obj.server_admin_username),
            "server_admin_password": bool(secrets_obj.server_admin_password),
            "ai_api_keys": {
                name: bool(key) for name, key in secrets_obj.ai_api_keys.items()
            },
        }
