"""Temporal worker process for durable render execution."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

from network_automation.activities.rendering import (
    publish_render_result,
    render_device_artifact,
)
from network_automation.settings import LabSettings
from network_automation.workflows.render_device import RenderDeviceConfigWorkflow

LOGGER = logging.getLogger(__name__)
HEARTBEAT_INTERVAL_SECONDS = 10.0
READY_PATH = Path("/tmp/network-worker.ready")
HEARTBEAT_PATH = Path("/tmp/network-worker.heartbeat")


async def run_worker(
    settings: LabSettings,
    *,
    stop_event: asyncio.Event | None = None,
    ready_path: Path = READY_PATH,
    heartbeat_path: Path = HEARTBEAT_PATH,
) -> None:
    from network_automation.activities.deployment import (
        deploy_device_artifact,
        prepare_device_deployment,
        validate_device_state,
    )

    stop_event = stop_event or asyncio.Event()
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
        data_converter=pydantic_data_converter,
    )
    with ThreadPoolExecutor(max_workers=4) as executor:
        async with Worker(
            client,
            task_queue=settings.temporal_task_queue,
            workflows=[RenderDeviceConfigWorkflow],
            activities=[
                render_device_artifact,
                publish_render_result,
                prepare_device_deployment,
                deploy_device_artifact,
                validate_device_state,
            ],
            activity_executor=executor,
        ):
            ready_path.touch()
            LOGGER.info("Automation worker ready task_queue=%s", settings.temporal_task_queue)
            while True:
                heartbeat_path.touch()
                if stop_event.is_set():
                    break
                try:
                    await asyncio.wait_for(
                        stop_event.wait(), timeout=HEARTBEAT_INTERVAL_SECONDS
                    )
                except TimeoutError:
                    continue


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    try:
        settings = LabSettings()
        stop_event = asyncio.Event()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        for signal_number in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(signal_number, stop_event.set)
        loop.run_until_complete(run_worker(settings, stop_event=stop_event))
    except Exception as exc:
        print(f"worker startup failed ({type(exc).__name__})", file=sys.stderr)
        return 1
    finally:
        if "loop" in locals():
            loop.close()
    return 0
