from fastapi import APIRouter, HTTPException
from app.models.schemas import DashboardConfig, DashboardResponse
from app.apis.grafana_api import create_dashboard_dynamic


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
