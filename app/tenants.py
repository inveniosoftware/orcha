"""Tenant registry for multi-tenant JWT authentication."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class TenantConfig:
    """Configuration for a single tenant."""

    tenant_id: str
    name: str
    public_key: str


# TODO: Integrate this, not being used as of now, but good to have for future
class TenantLookup(Protocol):
    """Protocol for tenant lookup implementations."""

    def get_tenant(self, tenant_id: str) -> TenantConfig | None:
        """Look up a tenant by ID."""
        ...


class TenantRegistry:
    r"""In-memory tenant registry loaded from a JSON config file.

    The JSON file should have the structure:
    {
        "tenant-id": {
            "name": "Human-readable Name",
            "public_key": "-----BEGIN PUBLIC KEY-----\\n...\\n-----END PUBLIC KEY-----"
        }
    }
    """

    def __init__(self, tenants: dict[str, TenantConfig] | None = None):
        """Initialize with an optional pre-built tenant map.

        Args:
            tenants: Mapping of tenant_id to TenantConfig.
        """
        self._tenants: dict[str, TenantConfig] = tenants or {}

    @classmethod
    def from_file(cls, path: str | Path) -> "TenantRegistry":
        """Load tenants from a JSON configuration file.

        Args:
            path: Path to the tenants JSON file.

        Returns:
            A TenantRegistry populated with the tenants from the file.

        Raises:
            FileNotFoundError: If the config file does not exist.
            ValueError: If the JSON structure is invalid.
        """
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Tenant config file not found: {config_path}")

        raw = json.loads(config_path.read_text())
        tenants: dict[str, TenantConfig] = {}

        for tenant_id, config in raw.items():
            if "public_key" not in config:
                raise ValueError(f"Tenant '{tenant_id}' is missing 'public_key'")
            tenants[tenant_id] = TenantConfig(
                tenant_id=tenant_id,
                name=config.get("name", tenant_id),
                public_key=config["public_key"],
            )

        return cls(tenants)

    def get_tenant(self, tenant_id: str) -> TenantConfig | None:
        """Look up a tenant by its ID.

        Args:
            tenant_id: The tenant identifier (matches JWT 'iss' claim).

        Returns:
            The tenant config, or None if not found.
        """
        return self._tenants.get(tenant_id)

    @property
    def tenant_ids(self) -> list[str]:
        """Return all registered tenant IDs."""
        return list(self._tenants.keys())
