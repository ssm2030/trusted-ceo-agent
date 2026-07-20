from __future__ import annotations

from dataclasses import replace

import uvicorn

from trusted_ceo_agent.application.run_application import (
    TrustedCeoApplication,
)
from trusted_ceo_agent.service.app import create_app
from trusted_ceo_agent.service.orchestrator import AnalysisOrchestrator
from trusted_ceo_agent.service.questions import QuestionService
from trusted_ceo_agent.service.run_store import RunStore
from trusted_ceo_agent.service.settings import ServiceSettings
from trusted_ceo_agent.service.testing.fake_openai import (
    KeylessFakeReasoningGateway,
)


def build_app():
    configured = ServiceSettings.from_environment()
    settings = replace(configured, openai_api_key="keyless-e2e-ready")
    store = RunStore(settings.service_root)
    application = TrustedCeoApplication(store.runs_root)
    gateway = KeylessFakeReasoningGateway(application.artifact_root)
    orchestrator = AnalysisOrchestrator(
        application,
        store,
        gateway,
    )
    questions = QuestionService(application, store, gateway)
    return settings, create_app(
        settings,
        application,
        orchestrator,
        questions,
    )


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