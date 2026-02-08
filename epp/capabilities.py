"""
Capability declarations for EPP envelopes.

Allows senders to declare what permissions/capabilities they require,
enabling recipients to make informed trust decisions.
"""

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class FilesystemCapabilities(BaseModel):
    """Filesystem access capabilities."""

    read: List[str] = Field(
        default_factory=list,
        description="Paths/patterns the sender needs to read (e.g., '~/.config/myapp/*')",
    )
    write: List[str] = Field(
        default_factory=list,
        description="Paths/patterns the sender needs to write",
    )

    @field_validator("read", "write")
    @classmethod
    def validate_paths(cls, v: List[str]) -> List[str]:
        """Validate path patterns are reasonable."""
        for path in v:
            # Basic sanity check - no null bytes or control characters
            if "\x00" in path or any(ord(c) < 32 for c in path):
                raise ValueError(f"Invalid path pattern: {path}")
        return v


class NetworkCapabilities(BaseModel):
    """Network access capabilities."""

    domains: List[str] = Field(
        default_factory=list,
        description="Domains the sender needs to access (e.g., 'api.example.com', '*.trusted.org')",
    )
    protocols: List[str] = Field(
        default_factory=list,
        description="Protocols required (e.g., 'https', 'wss')",
    )
    ports: List[int] = Field(
        default_factory=list,
        description="Specific ports required (empty = standard ports)",
    )

    @field_validator("domains")
    @classmethod
    def validate_domains(cls, v: List[str]) -> List[str]:
        """Validate domain patterns."""
        for domain in v:
            # Allow wildcards like *.example.com
            pattern = domain.replace("*", "wildcard")
            if not re.match(r"^[a-zA-Z0-9\-\.]+$", pattern):
                raise ValueError(f"Invalid domain pattern: {domain}")
        return v

    @field_validator("protocols")
    @classmethod
    def validate_protocols(cls, v: List[str]) -> List[str]:
        """Validate protocol names."""
        allowed = {"http", "https", "ws", "wss", "tcp", "udp", "grpc"}
        for proto in v:
            if proto.lower() not in allowed:
                raise ValueError(f"Unknown protocol: {proto}. Allowed: {allowed}")
        return [p.lower() for p in v]


class Capabilities(BaseModel):
    """
    Capability declarations for an EPP envelope.
    
    These are ADVISORY - the recipient decides whether to honor them.
    Trust registries can require or restrict capabilities per sender.
    """

    filesystem: Optional[FilesystemCapabilities] = Field(
        default=None,
        description="Filesystem access requirements",
    )
    network: Optional[NetworkCapabilities] = Field(
        default=None,
        description="Network access requirements",
    )
    actions: List[str] = Field(
        default_factory=list,
        description="Action identifiers required (e.g., 'send_notification', 'query_calendar')",
    )
    data_access: List[str] = Field(
        default_factory=list,
        description="Data access scopes (e.g., 'contacts:read', 'calendar:write')",
    )
    custom: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Custom capability declarations (namespace with x-prefix)",
    )

    @field_validator("actions")
    @classmethod
    def validate_actions(cls, v: List[str]) -> List[str]:
        """Validate action identifiers."""
        for action in v:
            # Allow "*" as wildcard for "all actions"
            if action != "*" and not re.match(r"^[a-zA-Z0-9_\-:]+$", action):
                raise ValueError(f"Invalid action identifier: {action}")
        return v

    @field_validator("data_access")
    @classmethod
    def validate_data_access(cls, v: List[str]) -> List[str]:
        """Validate data access scopes."""
        for scope in v:
            # Format: resource:permission or just resource, or "*" for all
            if scope != "*" and not re.match(r"^[a-zA-Z0-9_\-]+(:[a-zA-Z0-9_\-\*]+)?$", scope):
                raise ValueError(f"Invalid data access scope: {scope}")
        return v

    def is_empty(self) -> bool:
        """Check if capabilities are empty (no declarations)."""
        return (
            self.filesystem is None
            and self.network is None
            and not self.actions
            and not self.data_access
            and not self.custom
        )

    def requires_filesystem(self) -> bool:
        """Check if any filesystem access is declared."""
        if self.filesystem is None:
            return False
        return bool(self.filesystem.read or self.filesystem.write)

    def requires_network(self) -> bool:
        """Check if any network access is declared."""
        if self.network is None:
            return False
        return bool(self.network.domains or self.network.protocols)


def capabilities_from_dict(data: Optional[Dict[str, Any]]) -> Optional[Capabilities]:
    """
    Create Capabilities from a dict (for parsing envelopes).
    
    Args:
        data: Dict with capability declarations
        
    Returns:
        Capabilities object or None if data is None
    """
    if data is None:
        return None
    return Capabilities(**data)


def check_capability_allowed(
    declared: Capabilities,
    allowed: Capabilities,
) -> tuple[bool, List[str]]:
    """
    Check if declared capabilities are allowed by a policy.
    
    Args:
        declared: Capabilities declared by sender
        allowed: Capabilities allowed by recipient's policy
        
    Returns:
        Tuple of (is_allowed, list of denied capabilities)
    """
    denied = []
    
    # Check actions
    if declared.actions:
        allowed_actions = set(allowed.actions) if allowed.actions else set()
        for action in declared.actions:
            if action not in allowed_actions and "*" not in allowed_actions:
                denied.append(f"action:{action}")
    
    # Check data access
    if declared.data_access:
        allowed_data = set(allowed.data_access) if allowed.data_access else set()
        for scope in declared.data_access:
            if scope not in allowed_data and "*" not in allowed_data:
                # Check for wildcard patterns like "contacts:*"
                resource = scope.split(":")[0]
                if f"{resource}:*" not in allowed_data:
                    denied.append(f"data:{scope}")
    
    # Check network domains
    if declared.network and declared.network.domains:
        allowed_domains = set(allowed.network.domains) if allowed.network else set()
        for domain in declared.network.domains:
            if not _domain_allowed(domain, allowed_domains):
                denied.append(f"network:{domain}")
    
    # Check filesystem (more complex - would need path matching)
    if declared.filesystem:
        if declared.filesystem.read and (not allowed.filesystem or not allowed.filesystem.read):
            denied.append("filesystem:read")
        if declared.filesystem.write and (not allowed.filesystem or not allowed.filesystem.write):
            denied.append("filesystem:write")
    
    return (len(denied) == 0, denied)


def _domain_allowed(domain: str, allowed: set[str]) -> bool:
    """Check if a domain matches allowed patterns."""
    if domain in allowed or "*" in allowed:
        return True
    
    # Check wildcard patterns
    for pattern in allowed:
        if pattern.startswith("*."):
            suffix = pattern[1:]  # .example.com
            if domain.endswith(suffix) or domain == pattern[2:]:
                return True
    
    return False
