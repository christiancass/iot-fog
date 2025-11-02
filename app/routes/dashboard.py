from fastapi import APIRouter, HTTPException
from app.models.schemas import DashboardConfig, DashboardResponse
from app.apis.grafana_api import create_dashboard_dynamic, regenerate_public_dashboard


router = APIRouter(prefix="/grafana", tags=["Grafana"])



@router.post("/dashboards/custom", response_model=DashboardResponse)
async def create_custom_dashboard(cfg: DashboardConfig):
    """
    Crea un dashboard en Grafana con la configuración pasada en el body.
    """
    try:
        url = await create_dashboard_dynamic(cfg)
        return {"url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dashboards/share/{dashboard_uid}")
async def share_existing_dashboard(dashboard_uid: str):
    """
    Regenera (o habilita) el enlace público de un dashboard existente en Grafana.
    Devuelve la URL pública que puede abrirse sin autenticación.
    """
    try:
        data = regenerate_public_dashboard(dashboard_uid)
        public_uid = data.get("uid")
        grafana_url = os.getenv("GRAFANA_URL", "http://grafana:3000").rstrip("/")
        public_url = f"{grafana_url}/public-dashboards/{public_uid}"
        return {
            "message": "Public dashboard regenerado correctamente",
            "grafana_public_uid": public_uid,
            "grafana_public_url": public_url,
            "accessToken": data.get("accessToken")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
