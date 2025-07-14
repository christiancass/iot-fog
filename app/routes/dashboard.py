from fastapi import APIRouter, HTTPException
from app.models.schemas import DashboardConfig
from app.utils.grafana import create_dashboard_dynamic
from pydantic import BaseModel

router = APIRouter(prefix="/grafana", tags=["Grafana"])

class DashboardResponse(BaseModel):
    url: str

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
