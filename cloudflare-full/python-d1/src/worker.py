"""Entry point for the official Python Worker + D1 web application."""
from __future__ import annotations

from urllib.parse import urlsplit

from workers import Response, WorkerEntrypoint

from api import dispatch
from scheduled import run_scheduled


class _EngineEnvironment:
    """Secrets supplied by the trusted edge over a non-public service binding."""
    def __init__(self, base, token_key, job_secret, gitee_client_id="", gitee_client_secret="", gitee_redirect_uri=""):
        self._base = base
        self.TOKEN_ENCRYPTION_KEY = token_key
        self.APP_JOB_SHARED_SECRET = job_secret
        self.GITEE_CLIENT_ID = gitee_client_id
        self.GITEE_CLIENT_SECRET = gitee_client_secret
        self.GITEE_REDIRECT_URI = gitee_redirect_uri

    def __getattr__(self, name):
        return getattr(self._base, name)


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        env = self.env
        private_engine = str(getattr(env, "PRIVATE_ENGINE", "")) == "1"
        if private_engine:
            token_key = str(request.headers.get("X-Ledger-Engine-Token", ""))
            job_secret = str(request.headers.get("X-Ledger-Engine-Jobs", ""))
            gitee_client_id = str(request.headers.get("X-Ledger-Gitee-Client-ID", ""))
            gitee_client_secret = str(request.headers.get("X-Ledger-Gitee-Client-Secret", ""))
            gitee_redirect_uri = str(request.headers.get("X-Ledger-Gitee-Redirect-URI", ""))
            if not token_key or not job_secret:
                return Response.json({"error": "Private engine transport required."}, status=403)
            env = _EngineEnvironment(
                env, token_key, job_secret, gitee_client_id, gitee_client_secret, gitee_redirect_uri,
            )
        request_url = urlsplit(str(request.url))
        path = request_url.path.rstrip("/") or "/"
        if path == "/__internal/run-scheduled":
            if not private_engine or str(request.method).upper() != "POST":
                return Response.json({"error": "Not found."}, status=404)
            await run_scheduled(env)
            return Response.json({"ok": True})
        if path == "/__internal/health":
            try:
                result = await env.DB.prepare(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).run()
                tables = [row["name"] for row in result.results]
                return Response.json({"ok": True, "tables": tables})
            except Exception:
                return Response.json({"ok": False, "error": "D1 is not initialized."}, status=503)

        if path.startswith(("/api/", "/__internal/")):
            response = await dispatch(request, env)
            if response is not None:
                return response
            return Response.json(
                {"error": "网页版暂不支持此请求。"},
                status=503,
                headers={"cache-control": "no-store"},
            )

        if private_engine:
            return Response.json({"error": "Not found."}, status=404)
        return await env.ASSETS.fetch(request)

    async def scheduled(self, controller, env=None, ctx=None):
        await run_scheduled(env if env is not None else self.env)
