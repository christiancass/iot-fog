import os
import httpx

EMQX_API_BASE = os.getenv("EMQX_API_BASE", "http://localhost:8081/api/v4")
EMQX_APP_USER = os.getenv("EMQX_MANAGEMENT__DEFAULT_APPLICATION__USERNAME", "admin")
EMQX_APP_PASS = os.getenv("EMQX_MANAGEMENT__DEFAULT_APPLICATION__PASSWORD", "admin123..")

async def list_emqx_resources() -> dict:
    """
    Llama a GET /api/v4/resources y devuelve el JSON completo.
    """
    url = f"{EMQX_API_BASE}/resources"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            auth=(EMQX_APP_USER, EMQX_APP_PASS),
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()
