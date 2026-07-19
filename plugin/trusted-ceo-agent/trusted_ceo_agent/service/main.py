from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import uvicorn

from trusted_ceo_agent.application.run_application import TrustedCeoApplication
from trusted_ceo_agent.service.app import create_app
from trusted_ceo_agent.service.openai_gateway import AIServiceError, OpenAIReasoningGateway
from trusted_ceo_agent.service.orchestrator import AnalysisOrchestrator
from trusted_ceo_agent.service.run_store import RunStore
from trusted_ceo_agent.service.settings import ServiceSettings


class MissingApiKeyGateway:
    def execute(self, _job: Mapping[str, Any]) -> dict[str, Any]:
        raise AIServiceError(
            "AI_AUTH_FAILURE",
            "OpenAI API access is not configured",
        )


def build_app():
    settings = ServiceSettings.from_environment()
    store = RunStore(settings.service_root)
    application = TrustedCeoApplication(store.runs_root)
    gateway = (
        OpenAIReasoningGateway.from_settings(settings)
        if settings.ai_ready
        else MissingApiKeyGateway()
    )
    orchestrator = AnalysisOrchestrator(application, store, gateway)
    return settings, create_app(settings, application, orchestrator)


def main() -> None:
    settings, app = build_app()
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        reload=False,
        access_log=False,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
