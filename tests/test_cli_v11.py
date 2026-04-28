"""End-to-end tests for v1.1 CLI flags and subcommands."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def keys(runner: CliRunner, tmp_path: Path) -> dict:
    """Generate alice / bob / auditor keypairs in tmp_path."""
    out: dict = {}
    for name in ("alice", "bob", "auditor"):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            res = runner.invoke(cli, ["keys", "generate", "-o", name])
            assert res.exit_code == 0, res.output
            # The generate command writes alongside cwd; we want them in tmp_path
            for ext in ("key", "pub"):
                src = Path.cwd() / f"{name}.{ext}"
                dst = tmp_path / f"{name}.{ext}"
                dst.write_bytes(src.read_bytes())
            out[name] = {
                "key": str(tmp_path / f"{name}.key"),
                "pub": str(tmp_path / f"{name}.pub"),
            }
    # Read pubkey hex
    from epp.crypto.keys import PublicKey

    for name in ("alice", "bob", "auditor"):
        out[name]["hex"] = PublicKey.from_file(out[name]["pub"]).to_hex()
    return out


def _create_envelope_with_v11(runner: CliRunner, tmp_path: Path, keys: dict, **extra):
    """Helper that builds a basic envelope with v1.1 flags from extra."""
    env_path = tmp_path / "env.json"
    args = [
        "envelope",
        "create",
        "--private-key",
        keys["alice"]["key"],
        "--recipient",
        keys["bob"]["hex"],
        "--scope",
        "demo-echo",
        "--prompt",
        "hi",
        "--output",
        str(env_path),
    ]
    for k, v in extra.items():
        if isinstance(v, bool):
            if v:
                args.append(f"--{k.replace('_', '-')}")
        elif isinstance(v, (list, tuple)):
            for item in v:
                args.extend([f"--{k.replace('_', '-')}", str(item)])
        else:
            args.extend([f"--{k.replace('_', '-')}", str(v)])
    res = runner.invoke(cli, args)
    assert res.exit_code == 0, res.output
    return env_path, json.loads(env_path.read_text())


class TestCreateFlags:
    def test_hash_flag_adds_integrity(self, runner, tmp_path, keys):
        _, env = _create_envelope_with_v11(runner, tmp_path, keys, hash=True)
        assert "integrity" in env
        assert env["integrity"]["alg"] == "sha256"
        assert len(env["integrity"]["hash"]) == 64

    def test_payment_flags_add_payment(self, runner, tmp_path, keys):
        _, env = _create_envelope_with_v11(
            runner,
            tmp_path,
            keys,
            payment_required=True,
            payment_amount="0.01",
            payment_currency="USDC",
            payment_recipient="0x" + "a" * 40,
            payment_chain="base",
        )
        assert env["payment"]["amount"] == "0.01"
        assert env["payment"]["currency"] == "USDC"
        assert env["payment"]["chain"] == "base"

    def test_payment_partial_flags_error(self, runner, tmp_path, keys):
        env_path = tmp_path / "env.json"
        res = runner.invoke(
            cli,
            [
                "envelope",
                "create",
                "--private-key",
                keys["alice"]["key"],
                "--recipient",
                keys["bob"]["hex"],
                "--scope",
                "demo-echo",
                "--prompt",
                "hi",
                "--output",
                str(env_path),
                "--payment-amount",
                "0.01",  # missing other required
            ],
        )
        assert res.exit_code != 0
        assert "Payment requires" in res.output

    def test_capability_flags_add_capabilities(self, runner, tmp_path, keys):
        _, env = _create_envelope_with_v11(
            runner,
            tmp_path,
            keys,
            capability_action=["send_notification"],
            capability_data_access=["calendar:read", "contacts:read"],
            capability_net_domain=["api.example.com"],
        )
        assert env["capabilities"]["actions"] == ["send_notification"]
        assert env["capabilities"]["data_access"] == ["calendar:read", "contacts:read"]
        assert "api.example.com" in env["capabilities"]["network"]["domains"]

    def test_chain_identity_flags(self, runner, tmp_path, keys):
        _, env = _create_envelope_with_v11(
            runner,
            tmp_path,
            keys,
            chain_identity_standard="erc-8004",
            chain_identity_chain="base",
            chain_identity_contract="0x" + "b" * 40,
            chain_identity_token_id="42",
        )
        assert env["chain_identity"]["standard"] == "erc-8004"
        assert env["chain_identity"]["token_id"] == "42"

    def test_chain_identity_partial_errors(self, runner, tmp_path, keys):
        env_path = tmp_path / "env.json"
        res = runner.invoke(
            cli,
            [
                "envelope",
                "create",
                "--private-key",
                keys["alice"]["key"],
                "--recipient",
                keys["bob"]["hex"],
                "--scope",
                "demo-echo",
                "--prompt",
                "hi",
                "--output",
                str(env_path),
                "--chain-identity-standard",
                "ens",
            ],
        )
        assert res.exit_code != 0
        assert "ChainIdentity requires" in res.output

    def test_revocation_flags(self, runner, tmp_path, keys):
        _, env = _create_envelope_with_v11(
            runner,
            tmp_path,
            keys,
            revocation_registry="https://revoke.example/api",
        )
        assert env["revocation_check"]["registry"] == "https://revoke.example/api"
        assert env["revocation_check"]["required"] is True

    def test_revocation_optional_flag(self, runner, tmp_path, keys):
        env_path = tmp_path / "env.json"
        res = runner.invoke(
            cli,
            [
                "envelope",
                "create",
                "--private-key",
                keys["alice"]["key"],
                "--recipient",
                keys["bob"]["hex"],
                "--scope",
                "demo-echo",
                "--prompt",
                "hi",
                "--output",
                str(env_path),
                "--revocation-registry",
                "https://revoke",
                "--revocation-optional",
            ],
        )
        assert res.exit_code == 0, res.output
        env = json.loads(env_path.read_text())
        assert env["revocation_check"]["required"] is False


class TestProvenanceCommands:
    def test_add_then_verify(self, runner, tmp_path, keys):
        env_path, _ = _create_envelope_with_v11(runner, tmp_path, keys)
        res = runner.invoke(
            cli,
            [
                "provenance",
                "add",
                "--envelope",
                str(env_path),
                "--private-key",
                keys["alice"]["key"],
                "--role",
                "author",
                "--statement",
                "I wrote this",
            ],
        )
        assert res.exit_code == 0, res.output
        res = runner.invoke(
            cli,
            [
                "provenance",
                "add",
                "--envelope",
                str(env_path),
                "--private-key",
                keys["auditor"]["key"],
                "--role",
                "auditor",
            ],
        )
        assert res.exit_code == 0, res.output
        res = runner.invoke(cli, ["provenance", "verify", "--envelope", str(env_path)])
        assert res.exit_code == 0, res.output
        assert "Provenance chain valid" in res.output

    def test_verify_no_chain(self, runner, tmp_path, keys):
        env_path, _ = _create_envelope_with_v11(runner, tmp_path, keys)
        res = runner.invoke(cli, ["provenance", "verify", "--envelope", str(env_path)])
        assert res.exit_code == 0
        assert "No provenance chain present" in res.output


class TestAttestationCommands:
    def test_add_then_verify(self, runner, tmp_path, keys):
        env_path, _ = _create_envelope_with_v11(runner, tmp_path, keys)
        res = runner.invoke(
            cli,
            [
                "attestation",
                "add",
                "--envelope",
                str(env_path),
                "--private-key",
                keys["auditor"]["key"],
                "--role",
                "auditor",
                "--threshold",
                "1",
                "--required-role",
                "auditor",
            ],
        )
        assert res.exit_code == 0, res.output
        res = runner.invoke(cli, ["attestation", "verify", "--envelope", str(env_path)])
        assert res.exit_code == 0, res.output
        assert "Attestations valid" in res.output

    def test_verify_no_attestations(self, runner, tmp_path, keys):
        env_path, _ = _create_envelope_with_v11(runner, tmp_path, keys)
        res = runner.invoke(cli, ["attestation", "verify", "--envelope", str(env_path)])
        assert res.exit_code == 0
        assert "No attestations present" in res.output


class TestTrustAddRevocation:
    def test_trust_add_with_revocation_url(self, runner, tmp_path, keys):
        registry_path = tmp_path / "trust.json"
        res = runner.invoke(
            cli,
            [
                "trust",
                "add",
                "--registry",
                str(registry_path),
                "--public-key",
                keys["alice"]["hex"],
                "--name",
                "alice",
                "--revocation-check-url",
                "https://revoke.example/api",
                "--revocation-on-failure",
                "log-only",
            ],
        )
        assert res.exit_code == 0, res.output
        data = json.loads(registry_path.read_text())
        sender = data["senders"][0]
        assert sender["policy"]["revocation_check_url"] == "https://revoke.example/api"
        assert sender["policy"]["revocation_on_failure"] == "log-only"

    def test_trust_add_without_revocation_defaults(self, runner, tmp_path, keys):
        registry_path = tmp_path / "trust.json"
        res = runner.invoke(
            cli,
            [
                "trust",
                "add",
                "--registry",
                str(registry_path),
                "--public-key",
                keys["alice"]["hex"],
                "--name",
                "alice",
            ],
        )
        assert res.exit_code == 0, res.output
        data = json.loads(registry_path.read_text())
        sender = data["senders"][0]
        assert sender["policy"]["revocation_check_url"] is None
        assert sender["policy"]["revocation_on_failure"] == "deny"
