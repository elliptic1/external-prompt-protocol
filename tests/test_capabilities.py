"""Tests for capability declarations."""

import pytest

from epp.capabilities import (
    Capabilities,
    FilesystemCapabilities,
    NetworkCapabilities,
    capabilities_from_dict,
    check_capability_allowed,
)


class TestFilesystemCapabilities:
    """Tests for FilesystemCapabilities model."""

    def test_create_empty(self):
        """Test creating empty filesystem capabilities."""
        caps = FilesystemCapabilities()
        assert caps.read == []
        assert caps.write == []

    def test_create_with_paths(self):
        """Test creating filesystem capabilities with paths."""
        caps = FilesystemCapabilities(
            read=["~/.config/myapp/*", "/tmp/data.json"],
            write=["~/.cache/myapp/*"],
        )
        assert len(caps.read) == 2
        assert len(caps.write) == 1


class TestNetworkCapabilities:
    """Tests for NetworkCapabilities model."""

    def test_create_empty(self):
        """Test creating empty network capabilities."""
        caps = NetworkCapabilities()
        assert caps.domains == []
        assert caps.protocols == []

    def test_create_with_domains(self):
        """Test creating network capabilities with domains."""
        caps = NetworkCapabilities(
            domains=["api.example.com", "*.trusted.org"],
            protocols=["https", "wss"],
        )
        assert len(caps.domains) == 2
        assert caps.protocols == ["https", "wss"]

    def test_invalid_domain_rejected(self):
        """Test that invalid domains are rejected."""
        with pytest.raises(ValueError, match="Invalid domain pattern"):
            NetworkCapabilities(domains=["invalid domain with spaces"])

    def test_invalid_protocol_rejected(self):
        """Test that invalid protocols are rejected."""
        with pytest.raises(ValueError, match="Unknown protocol"):
            NetworkCapabilities(protocols=["ftp"])


class TestCapabilities:
    """Tests for Capabilities model."""

    def test_create_empty(self):
        """Test creating empty capabilities."""
        caps = Capabilities()
        assert caps.is_empty()

    def test_create_with_actions(self):
        """Test creating capabilities with actions."""
        caps = Capabilities(
            actions=["send_notification", "query_calendar"],
            data_access=["contacts:read", "calendar:write"],
        )
        assert len(caps.actions) == 2
        assert len(caps.data_access) == 2
        assert not caps.is_empty()

    def test_create_with_all_fields(self):
        """Test creating capabilities with all fields."""
        caps = Capabilities(
            filesystem=FilesystemCapabilities(read=["~/.config/*"]),
            network=NetworkCapabilities(domains=["api.example.com"]),
            actions=["send_notification"],
            data_access=["contacts:read"],
            custom={"x-myapp-feature": True},
        )
        assert caps.requires_filesystem()
        assert caps.requires_network()

    def test_invalid_action_rejected(self):
        """Test that invalid action identifiers are rejected."""
        with pytest.raises(ValueError, match="Invalid action identifier"):
            Capabilities(actions=["invalid action with spaces"])

    def test_invalid_data_access_rejected(self):
        """Test that invalid data access scopes are rejected."""
        with pytest.raises(ValueError, match="Invalid data access scope"):
            Capabilities(data_access=["invalid scope!"])


class TestCapabilitiesFromDict:
    """Tests for capabilities_from_dict function."""

    def test_from_none(self):
        """Test creating from None."""
        assert capabilities_from_dict(None) is None

    def test_from_dict(self):
        """Test creating from dict."""
        data = {
            "actions": ["send_notification"],
            "data_access": ["contacts:read"],
        }
        caps = capabilities_from_dict(data)
        assert caps is not None
        assert caps.actions == ["send_notification"]

    def test_from_nested_dict(self):
        """Test creating from dict with nested objects."""
        data = {
            "filesystem": {"read": ["~/.config/*"], "write": []},
            "network": {"domains": ["api.example.com"], "protocols": ["https"]},
            "actions": ["send_notification"],
        }
        caps = capabilities_from_dict(data)
        assert caps is not None
        assert caps.filesystem is not None
        assert caps.filesystem.read == ["~/.config/*"]


class TestCheckCapabilityAllowed:
    """Tests for check_capability_allowed function."""

    def test_empty_capabilities_allowed(self):
        """Test that empty capabilities are allowed."""
        declared = Capabilities()
        allowed = Capabilities()
        
        is_allowed, denied = check_capability_allowed(declared, allowed)
        assert is_allowed
        assert denied == []

    def test_action_allowed(self):
        """Test that declared action is allowed when in allowed list."""
        declared = Capabilities(actions=["send_notification"])
        allowed = Capabilities(actions=["send_notification", "query_calendar"])
        
        is_allowed, denied = check_capability_allowed(declared, allowed)
        assert is_allowed
        assert denied == []

    def test_action_denied(self):
        """Test that declared action is denied when not in allowed list."""
        declared = Capabilities(actions=["delete_everything"])
        allowed = Capabilities(actions=["send_notification"])
        
        is_allowed, denied = check_capability_allowed(declared, allowed)
        assert not is_allowed
        assert "action:delete_everything" in denied

    def test_wildcard_allows_all_actions(self):
        """Test that wildcard allows all actions."""
        declared = Capabilities(actions=["any_action"])
        allowed = Capabilities(actions=["*"])
        
        is_allowed, denied = check_capability_allowed(declared, allowed)
        assert is_allowed

    def test_data_access_allowed(self):
        """Test that declared data access is allowed."""
        declared = Capabilities(data_access=["contacts:read"])
        allowed = Capabilities(data_access=["contacts:read", "contacts:write"])
        
        is_allowed, denied = check_capability_allowed(declared, allowed)
        assert is_allowed

    def test_data_access_denied(self):
        """Test that undeclared data access is denied."""
        declared = Capabilities(data_access=["admin:full"])
        allowed = Capabilities(data_access=["contacts:read"])
        
        is_allowed, denied = check_capability_allowed(declared, allowed)
        assert not is_allowed
        assert "data:admin:full" in denied

    def test_network_domain_allowed(self):
        """Test that declared domain is allowed."""
        declared = Capabilities(
            network=NetworkCapabilities(domains=["api.example.com"])
        )
        allowed = Capabilities(
            network=NetworkCapabilities(domains=["api.example.com", "api.trusted.com"])
        )
        
        is_allowed, denied = check_capability_allowed(declared, allowed)
        assert is_allowed

    def test_network_domain_denied(self):
        """Test that undeclared domain is denied."""
        declared = Capabilities(
            network=NetworkCapabilities(domains=["evil.com"])
        )
        allowed = Capabilities(
            network=NetworkCapabilities(domains=["api.example.com"])
        )
        
        is_allowed, denied = check_capability_allowed(declared, allowed)
        assert not is_allowed
        assert "network:evil.com" in denied

    def test_wildcard_domain_allowed(self):
        """Test that wildcard domain patterns work."""
        declared = Capabilities(
            network=NetworkCapabilities(domains=["sub.example.com"])
        )
        allowed = Capabilities(
            network=NetworkCapabilities(domains=["*.example.com"])
        )
        
        is_allowed, denied = check_capability_allowed(declared, allowed)
        assert is_allowed
