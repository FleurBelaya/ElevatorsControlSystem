# 4.2 BFF (Backend for Frontend): корневой роутер, объединяющий BFF-эндпоинты
# для трёх клиентов (web/mobile/desktop). Каждый клиент имеет СВОЙ backend.

from fastapi import APIRouter

from elevator_control.adapters.inbound.api.bff import desktop, mobile, web

bff_router = APIRouter()
# 4.2.1 У каждого клиента свой маленький backend (BFF):
bff_router.include_router(web.router, prefix="/web", tags=["bff-web"])
bff_router.include_router(mobile.router, prefix="/mobile", tags=["bff-mobile"])
bff_router.include_router(desktop.router, prefix="/desktop", tags=["bff-desktop"])
