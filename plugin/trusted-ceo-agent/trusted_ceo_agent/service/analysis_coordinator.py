from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from trusted_ceo_agent.application.models import RunRequest
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.service.contracts import MutationBase, RunSnapshot
from trusted_ceo_agent.service.openai_gateway import AIServiceError
from trusted_ceo_agent.service.orchestrator import AnalysisOrchestrator
from trusted_ceo_agent.service.run_store import ServiceStoreError


ProviderAction = Literal['continue', 'retry', 'resume']
WorkerStarter = Callable[[Callable[[], None]], threading.Thread | None]
_SHUTDOWN_GRACE_SECONDS = 0.5


def _start_daemon_worker(work: Callable[[], None]) -> threading.Thread:
    worker = threading.Thread(
        target=work,
        name='trusted-ceo-analysis',
        daemon=True,
    )
    worker.start()
    return worker


@dataclass(frozen=True)
class _ActiveAnalysis:
    run_id: str
    action: ProviderAction
    request: MutationBase
    request_body: dict[str, object]
    manifest_generation: int
    snapshot: RunSnapshot

    def matches(
        self,
        run_id: str,
        action: ProviderAction,
        request: MutationBase,
        request_body: dict[str, object],
    ) -> bool:
        return (
            self.run_id == run_id
            and self.action == action
            and self.request.idempotency_key == request.idempotency_key
            and self.request_body == request_body
        )


class AnalysisCoordinator:
    '''Own the service's single background provider worker.'''

    def __init__(
        self,
        orchestrator: AnalysisOrchestrator,
        *,
        worker_starter: WorkerStarter = _start_daemon_worker,
    ) -> None:
        self.orchestrator = orchestrator
        self._worker_starter = worker_starter
        self._lock = threading.Lock()
        self._active: _ActiveAnalysis | None = None
        self._worker: threading.Thread | None = None
        self._on_drained: Callable[[], None] | None = None
        self._closed = False
        self._recover_pending_receipts()

    def close(
        self,
        *,
        on_drained: Callable[[], None] | None = None,
    ) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            worker = self._worker
        if worker is not None:
            worker.join(timeout=_SHUTDOWN_GRACE_SECONDS)
        release = None
        with self._lock:
            if (
                worker is not None
                and worker.is_alive()
                and self._worker is worker
            ):
                self._on_drained = on_drained
            else:
                release = on_drained
        if release is not None:
            release()

    def snapshot(self, run_id: str) -> RunSnapshot:
        with self._lock:
            active = self._active
            if active is not None and active.run_id == run_id:
                return active.snapshot
        return self.orchestrator.snapshot(run_id)

    def assert_mutation_allowed(self) -> None:
        with self._lock:
            if self._active is not None:
                raise ServiceStoreError(
                    'IDEMPOTENCY_CONFLICT',
                    'another analysis step is active',
                )

    def start(
        self,
        run_id: str,
        action: ProviderAction,
        request: MutationBase,
    ) -> RunSnapshot:
        if action not in {'continue', 'retry', 'resume'}:
            raise ValueError('unsupported provider action')
        request_body = self._request_body(action, request)
        with self._lock:
            if self._closed:
                raise ContractError('analysis coordinator is closed')
            active = self._active
            if active is not None and active.matches(
                run_id,
                action,
                request,
                request_body,
            ):
                return active.snapshot

            replay = self.orchestrator.run_store.read_idempotency_receipt(
                run_id,
                idempotency_key=request.idempotency_key,
                request_body=request_body,
            )
            if replay is not None:
                return RunSnapshot.model_validate(replay.response)
            if active is not None:
                raise ServiceStoreError(
                    'IDEMPOTENCY_CONFLICT',
                    'another analysis step is active',
                )

            manifest = self.orchestrator.run_store.assert_revision(
                run_id,
                expected_revision=request.expected_revision,
            )
            current = self.orchestrator.snapshot(run_id)
            if action not in current.allowed_actions:
                raise ContractError(f'{action} is not allowed for this run')
            active_snapshot = self._active_snapshot(current)
            active = _ActiveAnalysis(
                run_id=run_id,
                action=action,
                request=request,
                request_body=request_body,
                manifest_generation=manifest.generation,
                snapshot=active_snapshot,
            )
            self.orchestrator.run_store.store_idempotency_receipt(
                active.run_id,
                idempotency_key=active.request.idempotency_key,
                request_body=active.request_body,
                status_code=202,
                response=active.snapshot.model_dump(mode='json'),
            )
            self._active = active
            try:
                self._worker = self._worker_starter(
                    lambda: self._execute(active),
                )
            except Exception:
                self._active = None
                self._worker = None
                self.orchestrator.run_store.discard_pending_idempotency_receipt(
                    active.run_id,
                    idempotency_key=active.request.idempotency_key,
                    request_body=active.request_body,
                )
                raise
            return active_snapshot

    def _execute(self, active: _ActiveAnalysis) -> None:
        try:
            if active.action == 'continue':
                completed = self.orchestrator.continue_run(
                    active.run_id,
                    MutationBase(
                        expected_revision=active.request.expected_revision,
                        idempotency_key=self._internal_key(active, 'continue'),
                    ),
                )
            else:
                completed = self._execute_controlled_provider_action(active)
            self.orchestrator.run_store.complete_idempotency_receipt(
                active.run_id,
                idempotency_key=active.request.idempotency_key,
                request_body=active.request_body,
                status_code=200,
                response=completed.model_dump(mode='json'),
            )
        except Exception as error:
            self._recover_failed_worker(active.run_id, error)
            self._complete_receipt_from_current(active)
        finally:
            release = None
            with self._lock:
                if self._active is active:
                    self._active = None
                    self._worker = None
                    if self._closed:
                        release = self._on_drained
                        self._on_drained = None
            if release is not None:
                release()

    def _recover_pending_receipts(self) -> None:
        pending = self.orchestrator.run_store.pending_analysis_receipts()
        if not pending:
            return
        self.orchestrator.run_store.recover_interrupted(
            (run_id for run_id, _receipt in pending),
            recover_stopped=True,
        )
        snapshots = {
            run_id: self.orchestrator.snapshot(run_id)
            for run_id in {run_id for run_id, _receipt in pending}
        }
        for run_id, receipt in pending:
            self.orchestrator.run_store.complete_pending_idempotency_receipt(
                run_id,
                idempotency_key=receipt.idempotency_key,
                expected_request_hash=receipt.request_hash,
                status_code=200,
                response=snapshots[run_id].model_dump(mode='json'),
            )

    def _execute_controlled_provider_action(
        self,
        active: _ActiveAnalysis,
    ) -> RunSnapshot:
        transition = self.orchestrator.control_run(
            active.run_id,
            active.action,
            MutationBase(
                expected_revision=active.request.expected_revision,
                idempotency_key=self._internal_key(active, 'control'),
            ),
        )
        completed = transition
        if transition.pending_action == 'provider_work':
            completed = self.orchestrator.continue_run(
                active.run_id,
                MutationBase(
                    expected_revision=transition.revision,
                    idempotency_key=self._internal_key(active, 'continue'),
                ),
            )
        return completed

    def _recover_failed_worker(self, run_id: str, error: Exception) -> None:
        try:
            manifest = self.orchestrator.run_store.read_manifest(run_id)
            if manifest.status != 'running':
                return
            state = self.orchestrator.application.status(RunRequest(run_id=run_id))
            if state.revision is None:
                return
            failed = manifest.model_copy(update={
                'engine_revision': state.revision,
                'last_checkpoint_revision': state.revision,
                'status': 'retryable_failure',
                'stage': state.state,
                'attempt': min(100, manifest.attempt + 1),
                'error_code': (
                    error.code
                    if isinstance(error, AIServiceError)
                    else 'ENGINE_FAILURE'
                ),
                'pending_approval_request_id': None,
                'pending_approval_nonce': None,
            })
            self.orchestrator.run_store.save_manifest(
                failed,
                expected_revision=manifest.engine_revision,
            )
        except Exception:
            return

    def _complete_receipt_from_current(self, active: _ActiveAnalysis) -> None:
        try:
            current = self.orchestrator.snapshot(active.run_id)
            self.orchestrator.run_store.complete_idempotency_receipt(
                active.run_id,
                idempotency_key=active.request.idempotency_key,
                request_body=active.request_body,
                status_code=200,
                response=current.model_dump(mode='json'),
            )
        except Exception:
            return

    @staticmethod
    def _active_snapshot(snapshot: RunSnapshot) -> RunSnapshot:
        return RunSnapshot.model_validate({
            **snapshot.model_dump(mode='python'),
            'pending_action': 'provider_work',
            'allowed_actions': [],
            'hitl_card': None,
            'error': None,
        })

    @staticmethod
    def _request_body(
        action: ProviderAction,
        request: MutationBase,
    ) -> dict[str, object]:
        body: dict[str, object] = request.model_dump(mode='json')
        if action != 'continue':
            body['action'] = action
        return body

    @staticmethod
    def _internal_key(active: _ActiveAnalysis, phase: str) -> str:
        digest = hashlib.sha256(
            (
                f'{active.run_id}\0{active.action}\0'
                f'{active.request.idempotency_key}\0'
                f'{active.manifest_generation}\0{phase}'
            ).encode('utf-8')
        ).hexdigest()
        return f'analysis_{phase}_{digest}'
