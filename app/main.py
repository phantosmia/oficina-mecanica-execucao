from fastapi import FastAPI

from app.execution.controller import router as execution_router
from app.shared.logging_config import RequestIDMiddleware, configure_logging
from app.shared.settings import settings
from app.system.controller import router as system_router

configure_logging(settings.log_level)

app = FastAPI(
    title=settings.app_name,
    description=(
        "Microsserviço de Execução da oficina mecânica: fila de diagnóstico e de reparo das ordens de serviço. "
        "As OS chegam pela saga (SQS); o mecânico conduz cada etapa por esta API, com o JWT de admin "
        "emitido pelo OS Service."
    ),
    version="1.0.0",
)

app.add_middleware(RequestIDMiddleware)

app.include_router(system_router)
app.include_router(execution_router)
