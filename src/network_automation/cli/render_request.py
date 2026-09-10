"""Publish one validated render request event."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from uuid import uuid4

from network_automation.events.models import RenderRequested, workflow_id_for
from network_automation.events.producer import publish_event


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Request durable rendering for one device")
    parser.add_argument("device", help="exact Nautobot device name")
    args = parser.parse_args(argv)
    try:
        event = RenderRequested(
            event_type="network.render.requested",
            event_version=1,
            event_id=uuid4(),
            correlation_id=uuid4(),
            device_name=args.device,
            requested_at=datetime.now(timezone.utc),
            source="cli",
        )
        publish_event(event)
    except Exception as exc:
        print(
            f"error: request publication failed ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 1
    print(f"event_id={event.event_id}")
    print(f"correlation_id={event.correlation_id}")
    print(f"workflow_id={workflow_id_for(event.event_id)}")
    return 0
