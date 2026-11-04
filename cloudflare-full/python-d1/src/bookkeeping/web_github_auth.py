"""GitHub device sign-in bound to one browser, separate from cloud uploads."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone

from .github_sync import GITHUB_APP_CLIENT_ID, GitHubClient, request_device_code, poll_device_token
from .storage import Database, LedgerError


def ensure_identity_schema(connection):
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS web_identities (
            provider TEXT NOT NULL,
            subject TEXT NOT NULL,
            user_id TEXT NOT NULL REFERENCES web_users(id),
            login TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(provider,subject),
            UNIQUE(provider,user_id)
        );
    """)


class GitHubSignIn:
    def __init__(self, server):
        self.server = server
        self.flows = {}
        self.attempts = {}
        self.guard = threading.RLock()

    def close(self):
        with self.guard:
            for flow in self.flows.values():
                flow["cancel"].set()

    def start(self, client, *, link_user=None, previous_cookie=""):
        with self.guard:
            now = time.monotonic()
            self.flows = {key: flow for key, flow in self.flows.items()
                          if flow["expires"] > now and not flow["consumed"] and not flow["cancel"].is_set()}
            self.attempts = {key: [stamp for stamp in stamps if now - stamp < 600]
                             for key, stamps in self.attempts.items() if any(now - stamp < 600 for stamp in stamps)}
            attempts = self.attempts.setdefault(client, [])
            if len(attempts) >= 10 or len(self.flows) >= 64:
                raise LedgerError("GitHub 登录请求过多，请稍后再试。")
            attempts.append(now)
            if previous_cookie:
                try:
                    self._flow(previous_cookie)["cancel"].set()
                except LedgerError:
                    pass
        challenge = request_device_code(GITHUB_APP_CLIENT_ID)
        if challenge.get("verification_uri") != "https://github.com/login/device":
            raise LedgerError("GitHub 授权地址校验失败，请稍后再试。")
        flow_id, secret = uuid.uuid4().hex, secrets.token_urlsafe(32)
        duration = min(max(int(challenge["expires_in"]), 1), 900)
        flow = {"id": flow_id, "secret_hash": hashlib.sha256(secret.encode()).digest(),
                "expires": time.monotonic() + duration, "cancel": threading.Event(),
                "state": "pending", "userCode": str(challenge["user_code"]), "identity": None, "link_user": link_user, "consumed": False}
        with self.guard:
            self.flows[flow_id] = flow
        threading.Thread(target=self._authorize, args=(flow, challenge), daemon=True).start()
        return {"flowId": flow_id, "userCode": str(challenge["user_code"]),
                "verificationUri": challenge["verification_uri"], "expiresIn": duration,
                "state": "pending"}, flow_id + "." + secret

    def _authorize(self, flow, challenge):
        try:
            tokens = poll_device_token(GITHUB_APP_CLIENT_ID, challenge["device_code"],
                int(challenge["interval"]), int(challenge["expires_in"]), lambda: flow["cancel"].is_set() or time.monotonic() >= flow["expires"])
            identity = GitHubClient(tokens["access_token"], refresh_token=tokens.get("refresh_token", ""),
                                    client_id=GITHUB_APP_CLIENT_ID).current_user()
            # Login/email is mutable; only GitHub's authenticated numeric ID identifies an owner.
            subject, login = str(identity.get("id", "")), str(identity.get("login", ""))
            if not re.fullmatch(r"[1-9][0-9]{0,20}", subject) or not re.fullmatch(r"[A-Za-z0-9-]{1,39}", login):
                raise LedgerError("GitHub 身份校验失败，请重新登录。")
            if identity.get("type") not in (None, "User"):
                raise LedgerError("请使用个人 GitHub 账号登录。")
            with self.guard:
                if flow["cancel"].is_set() or time.monotonic() >= flow["expires"]:
                    return
                flow["identity"] = {"subject": subject, "login": login}
                flow['cloud_credentials'] = tokens
                flow["state"] = "authorized"
            # Credentials stay server-side, encrypted after finish, for the
            # user-requested startup download. They never enter a JSON response.
        except Exception:
            with self.guard:
                flow.update(state="failed", error="GitHub 登录未完成，请重新发起并在 GitHub 确认授权。")

    def _flow(self, cookie, flow_id=None):
        parts = str(cookie).split(".", 1)
        if len(parts) != 2:
            raise LedgerError("GitHub 登录已过期，请重新开始。")
        flow = self.flows.get(parts[0])
        if (not flow or (flow_id is not None and parts[0] != flow_id) or
            flow["consumed"] or flow["cancel"].is_set() or time.monotonic() >= flow["expires"] or
            not hmac.compare_digest(flow["secret_hash"], hashlib.sha256(parts[1].encode()).digest())):
            raise LedgerError("GitHub 登录已过期，请重新开始。")
        return flow

    def status(self, cookie, flow_id):
        with self.guard:
            flow = self._flow(cookie, flow_id)
            return {"state": flow["state"], "userCode": flow["userCode"], "verificationUri": "https://github.com/login/device", **({"error": flow["error"]} if flow.get("error") else {})}

    def cancel(self, cookie, flow_id):
        with self.guard:
            flow = self._flow(cookie, flow_id)
            flow["cancel"].set()
            flow.pop('cloud_credentials', None)
            flow["consumed"] = True

    def finish(self, cookie, flow_id, *, current_user=None):
        with self.guard:
            flow = self._flow(cookie, flow_id)
            if flow["state"] != "authorized":
                raise LedgerError("请先在 GitHub 完成授权。")
            if flow["link_user"] and flow["link_user"] != current_user:
                raise LedgerError("原账号会话已变化，请重新验证原账号后关联。")
            user = self._resolve_identity(flow["identity"], flow["link_user"])
            credentials = flow.pop('cloud_credentials', None)
            if credentials:
                workspace = self.server.workspace
                with workspace.lock(user['id']):
                    from .cloud_pull import PullState
                    PullState(workspace.folder(user['id']) / 'cloud_pull_state.json').pause_downloads(choice_pending=True)
                    cfg = workspace.config(user['id'])
                    cloud = cfg['cloud'].setdefault('github', {})
                    name = cloud.get('repositoryName') or 'household-bookkeeping-data'
                    cloud.update(token=credentials['access_token'], refresh_token=credentials.get('refresh_token', ''),
                                 repositoryName=name, repository=cloud.get('repository') or user['username'] + '/' + name)
                    workspace.save_config(user['id'], cfg)
            flow["consumed"] = True
            flow["identity"] = None
            return user

    def _resolve_identity(self, identity, link_user=None):
        connection = sqlite3.connect(self.server.auth_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        created_path = None
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT user_id FROM web_identities WHERE provider='github' AND subject=?",
                                          (identity["subject"],)).fetchone()
            if existing:
                uid = existing["user_id"]
                if link_user and uid != link_user:
                    raise LedgerError("这个 GitHub 已关联另一份账本。当前账本保持不变，请使用原关联账号。")
                connection.execute("UPDATE web_identities SET login=? WHERE provider='github' AND subject=?",
                                   (identity["login"], identity["subject"]))
            elif link_user:
                uid = link_user
                if connection.execute("SELECT 1 FROM web_identities WHERE provider='github' AND user_id=?", (uid,)).fetchone():
                    raise LedgerError("当前账本已关联其他 GitHub，不能直接替换。")
                if not connection.execute("SELECT 1 FROM web_users WHERE id=?", (uid,)).fetchone():
                    raise LedgerError("原账号不存在，请重新登录。")
            else:
                uid = str(uuid.uuid4())
                created_path = self.server.ledger_dir / f"{uid}.sqlite3"
                db = Database(created_path)
                try:
                    db.initialize()
                finally:
                    db.close()
                now = datetime.now(timezone.utc).isoformat()
                connection.execute("INSERT INTO web_users VALUES(?,?,?,?,?,?,?)", (uid,
                    "gh-" + uuid.uuid4().hex, secrets.token_bytes(16), secrets.token_bytes(32),
                    secrets.token_bytes(16), secrets.token_bytes(32), now))
            if not existing:
                connection.execute("INSERT INTO web_identities VALUES('github',?,?,?,?)", (
                    identity["subject"], uid, identity["login"], datetime.now(timezone.utc).isoformat()))
            if not (self.server.ledger_dir / f"{uid}.sqlite3").is_file():
                raise LedgerError("找不到账号账本，请检查服务备份。")
            if link_user:
                # Retire old password/recovery credentials and old sessions after proven linking.
                connection.execute("UPDATE web_users SET password_hash=?,recovery_hash=? WHERE id=?",
                                   (secrets.token_bytes(32), secrets.token_bytes(32), uid))
                connection.execute("DELETE FROM web_sessions WHERE user_id=?", (uid,))
            connection.commit()
            return {"id": uid, "username": identity["login"], "authProvider": "github"}
        except BaseException:
            connection.rollback()
            if created_path:
                created_path.unlink(missing_ok=True)
            raise
        finally:
            connection.close()
