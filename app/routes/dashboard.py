# app/routes/dashboard.py

from fastapi import APIRouter, HTTPException, Depends
import os
from datetime import datetime

from app.models.schemas import DashboardConfig, DashboardResponse
from app.apis.grafana_api import (
    create_dashboard_dynamic,
    regenerate_public_dashboard,delete_dashboard_dynamic
)
from app.routes.auth import get_current_user
from app.utils.db import get_db

router = APIRouter(prefix="/grafana", tags=["Grafana"])


def width_to_size(w: int) -> str:
    """
    Mapea el ancho (gridPos.w en Grafana, 24 columnas) a un tamaño lógico.
    Debe ser consistente con lo que hace el frontend:
      - full   -> 24
      - medium -> 12
      - small  -> 8
    """
    try:
        w = int(w)
    except Exception:
        # Por si viene algo raro, usamos 'medium' por defecto
        return "medium"

    if w >= 24:
        return "full"
    elif w >= 12:
        return "medium"
    else:
        return "small"


@router.post("/dashboards/custom", response_model=DashboardResponse)
async def create_custom_dashboard(
    cfg: DashboardConfig,
    user: dict = Depends(get_current_user),
):
    """
    Crea un dashboard en Grafana y guarda referencia en Mongo:
    - username
    - uid, title, slug, url
    - panels: [{id, title, size}]
    """
    try:
        # Aseguramos tagFilters y username
        if cfg.tagFilters is None:
            cfg.tagFilters = {}
        cfg.tagFilters["username"] = user["username"]

        db = get_db()
        if db is None:
            raise HTTPException(status_code=500, detail="Base de datos no inicializada")

        # 1) Crear dashboard en Grafana
        data = await create_dashboard_dynamic(cfg)
        # Respuesta típica:
        # {
        #   "id": 2,
        #   "slug": "dashboard-iot",
        #   "status": "success",
        #   "uid": "9909-...",
        #   "url": "/d/9909-.../dashboard-iot",
        #   ...
        # }

        url = data.get("url")    # /d/uid/slug
        uid = data.get("uid")
        slug = data.get("slug")
        title = cfg.title

        if not url or not uid:
            raise RuntimeError(f"Grafana no devolvió url/uid: {data}")

        # 2) Construir metadata de paneles basados en cfg.panels
        #    IMPORTANTE: el mismo orden que usamos en create_dashboard_dynamic
        panels_meta = []
        for idx, p in enumerate(cfg.panels, start=1):
            # p puede ser un dict o un modelo Pydantic, hacemos esto robusto:
            grid_pos = None
            # Si es Pydantic o tiene atributo:
            if hasattr(p, "gridPos"):
                grid_pos = getattr(p, "gridPos")
            # Si vino como dict "p['gridPos']":
            if grid_pos is None and isinstance(p, dict):
                grid_pos = p.get("gridPos")

            w = None
            if isinstance(grid_pos, dict):
                w = grid_pos.get("w")

            size = width_to_size(w) if w is not None else "medium"

            panels_meta.append(
                {
                    "id": idx,             # coincide con create_dashboard_dynamic
                    "title": getattr(p, "title", None) or (p.get("title") if isinstance(p, dict) else f"Panel {idx}"),
                    "size": size,          # <-- guardamos tamaño
                }
            )

        # 3) Guardar en Mongo
        await db["grafana_dashboards"].insert_one(
            {
                "username": user["username"],
                "uid": uid,
                "title": title,
                "slug": slug,
                "url": url,  # /d/uid/slug
                "created_at": datetime.utcnow(),
                "panels": panels_meta,
            }
        )

        # 4) Responder al front
        return {"url": url}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboards/my")
async def list_my_dashboards(user: dict = Depends(get_current_user)):
    """
    Lista dashboards del usuario (desde Mongo).
    """
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Base de datos no inicializada")

    cursor = (
        db["grafana_dashboards"]
        .find({"username": user["username"]})
        .sort("created_at", -1)
    )

    grafana_public_base = os.getenv(
        "GRAFANA_PUBLIC_URL", os.getenv("GRAFANA_URL", "http://localhost:3000")
    ).rstrip("/")

    dashboards = []
    async for d in cursor:
        url = d.get("url")  # /d/uid/slug
        full_url = f"{grafana_public_base}{url}" if url else None
        dashboards.append(
            {
                "uid": d.get("uid"),
                "title": d.get("title"),
                "slug": d.get("slug"),
                "url": url,
                "fullUrl": full_url,
            }
        )

    return dashboards


@router.get("/dashboards/{dashboard_uid}/panels")
async def list_dashboard_panels(
    dashboard_uid: str,
    user: dict = Depends(get_current_user),
):
    """
    Devuelve los paneles (id, title, size) de un dashboard,
    leyendo la metadata guardada en Mongo al crearlo.
    """
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Base de datos no inicializada")

    doc = await db["grafana_dashboards"].find_one(
        {"uid": dashboard_uid, "username": user["username"]}
    )
    if not doc:
        raise HTTPException(
            status_code=404,
            detail="Dashboard no encontrado para este usuario",
        )

    panels = doc.get("panels") or []
    # Devolver en formato simple
    return [
        {
            "id": p.get("id"),
            "title": p.get("title") or f"Panel {p.get('id')}",
            "size": p.get("size", "medium"),  # <-- devolvemos el tamaño
        }
        for p in panels
        if p.get("id") is not None
    ]


@router.post("/dashboards/share/{dashboard_uid}")
async def share_existing_dashboard(
    dashboard_uid: str,
    user: dict = Depends(get_current_user),
):
    """
    (Opcional) seguir usando public dashboards.
    Ya no es necesario para los iframes de paneles (d-solo),
    pero dejo la ruta por si la usas en otro lado.
    """
    try:
        data = regenerate_public_dashboard(dashboard_uid)

        public_uid = data.get("uid")
        access_token = data.get("accessToken")

        if not access_token:
            raise RuntimeError(
                "Grafana no devolvió 'accessToken' para el public dashboard"
            )

        grafana_public_base = os.getenv(
            "GRAFANA_PUBLIC_URL", os.getenv("GRAFANA_URL", "http://localhost:3000")
        ).rstrip("/")
        public_url = f"{grafana_public_base}/public-dashboards/{access_token}"

        return {
            "message": "Public dashboard listo",
            "grafana_public_uid": public_uid,
            "grafana_public_url": public_url,
            "accessToken": access_token,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/dashboards/{dashboard_uid}")
async def delete_dashboard(
    dashboard_uid: str,
    user: dict = Depends(get_current_user),
):
    """
    Elimina un dashboard tanto en Grafana como en Mongo
    (solo si pertenece al usuario autenticado).
    """
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Base de datos no inicializada")

    # Verificamos que el dashboard sea del usuario
    doc = await db["grafana_dashboards"].find_one(
        {"uid": dashboard_uid, "username": user["username"]}
    )
    if not doc:
        raise HTTPException(
            status_code=404,
            detail="Dashboard no encontrado para este usuario",
        )

    # 1) Intentar eliminarlo en Grafana
    try:
        await delete_dashboard_dynamic(dashboard_uid)
    except Exception as e:
        # Lo logueamos pero no rompemos todo:
        logging.warning(
            f"[Grafana] Error eliminando dashboard uid={dashboard_uid} en Grafana: {e}"
        )

    # 2) Eliminarlo en Mongo
    await db["grafana_dashboards"].delete_one(
        {"uid": dashboard_uid, "username": user["username"]}
    )

    return {"message": "Dashboard eliminado"}
