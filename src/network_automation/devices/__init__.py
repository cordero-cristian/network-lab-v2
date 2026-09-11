"""Concrete network-device boundaries."""

from network_automation.devices.srlinux import (
    DeviceAuthenticationError,
    DeviceConfigurationError,
    DeviceConnectionError,
    DeviceIdentityError,
    DevicePathError,
    DevicePlatformError,
    DeviceResponseError,
    SRLinuxClient,
    SRLinuxDeviceError,
)

__all__ = [
    "DeviceAuthenticationError",
    "DeviceConfigurationError",
    "DeviceConnectionError",
    "DeviceIdentityError",
    "DevicePathError",
    "DevicePlatformError",
    "DeviceResponseError",
    "SRLinuxClient",
    "SRLinuxDeviceError",
]
