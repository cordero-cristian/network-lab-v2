"""Publish one validated render or deployment request event."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from uuid import uuid4

from network_automation.events.models import (
    DeploymentRequested,
    RenderRequested,
    deployment_workflow_id_for,
    workflow_id_for,
)
from network_automation.events.producer import publish_event


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Request durable automation for one device")
    parser.add_argument(
        "--deploy",
        action="store_true",
        help="render, deploy, and validate the requested device",
    )
    parser.add_argument("device", help="exact Nautobot device name")
    args = parser.parse_args(argv)
    try:
        event_id = uuid4()
        event_values = {
            "event_version": 1,
            "event_id": event_id,
            "correlation_id": uuid4(),
            "device_name": args.device,
            "requested_at": datetime.now(timezone.utc),
            "source": "cli",
        }
        if args.deploy:
            event = DeploymentRequested(
                event_type="network.deployment.requested", **event_values
            )
            workflow_id = deployment_workflow_id_for(event_id)
        else:
            event = RenderRequested(
                event_type="network.render.requested", **event_values
            )
            workflow_id = workflow_id_for(event_id)
        publish_event(event)
    except Exception as exc:
        print(
            f"error: request publication failed ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 1
    print(f"event_id={event.event_id}")
    print(f"correlation_id={event.correlation_id}")
    print(f"workflow_id={workflow_id}")
    return 0
