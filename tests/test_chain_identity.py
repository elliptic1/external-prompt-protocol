"""Tests for the v1.1 chain_identity module."""

import pytest

from epp.chain_identity import (
    SUPPORTED_STANDARDS,
    SUPPORTED_VERIFICATION_METHODS,
    ChainIdentity,
    chain_identity_from_dict,
)


class TestStandardEnum:
    @pytest.mark.parametrize("std", list(SUPPORTED_STANDARDS))
    def test_each_supported_standard(self, std: str):
        ci = ChainIdentity(standard=std, chain="ethereum")
        assert ci.standard == std

    def test_uppercase_standard_normalized(self):
        ci = ChainIdentity(standard="ERC-8004", chain="base")
        assert ci.standard == "erc-8004"

    def test_unsupported_standard_rejected(self):
        with pytest.raises(ValueError, match="Unsupported chain_identity standard"):
            ChainIdentity(standard="bogus", chain="base")


class TestChain:
    def test_known_chain_lowercased(self):
        ci = ChainIdentity(standard="ens", chain="ETHEREUM")
        assert ci.chain == "ethereum"

    def test_unknown_chain_accepted_with_valid_shape(self):
        ci = ChainIdentity(standard="custom", chain="newchain-2")
        assert ci.chain == "newchain-2"

    def test_invalid_chain_shape_rejected(self):
        with pytest.raises(ValueError, match="Invalid chain identifier"):
            ChainIdentity(standard="custom", chain="bad chain!")


class TestContract:
    def test_evm_contract_lowercased(self):
        ci = ChainIdentity(standard="erc-8004", chain="base", contract="0x" + "AB" * 20)
        assert ci.contract == "0x" + "ab" * 20

    def test_evm_contract_wrong_length_rejected(self):
        with pytest.raises(ValueError, match="Invalid EVM contract address"):
            ChainIdentity(standard="erc-8004", chain="base", contract="0xabc")

    def test_solana_contract_accepted(self):
        ci = ChainIdentity(
            standard="custom",
            chain="solana",
            contract="So11111111111111111111111111111111111111112",
        )
        assert ci.contract is not None

    def test_garbage_contract_rejected(self):
        with pytest.raises(ValueError, match="Invalid contract address"):
            ChainIdentity(standard="custom", chain="solana", contract="!!!")

    def test_no_contract_ok(self):
        ci = ChainIdentity(standard="ens", chain="ethereum", identifier="alice.eth")
        assert ci.contract is None


class TestTokenId:
    def test_decimal_accepted(self):
        ci = ChainIdentity(
            standard="erc-8004",
            chain="base",
            contract="0x" + "a" * 40,
            token_id="42",
        )
        assert ci.token_id == "42"

    def test_hex_accepted(self):
        ci = ChainIdentity(
            standard="erc-8004",
            chain="base",
            contract="0x" + "a" * 40,
            token_id="0xdeadbeef",
        )
        assert ci.token_id == "0xdeadbeef"

    def test_invalid_token_id_rejected(self):
        with pytest.raises(ValueError, match="Invalid token_id"):
            ChainIdentity(
                standard="erc-8004",
                chain="base",
                contract="0x" + "a" * 40,
                token_id="not a number",
            )


class TestIdentifier:
    def test_ens_name_accepted(self):
        ci = ChainIdentity(standard="ens", chain="ethereum", identifier="alice.eth")
        assert ci.identifier == "alice.eth"

    def test_did_accepted(self):
        ci = ChainIdentity(
            standard="did",
            chain="ethereum",
            identifier="did:web:example.com",
        )
        assert ci.identifier == "did:web:example.com"

    def test_invalid_identifier_rejected(self):
        with pytest.raises(ValueError, match="Invalid identifier"):
            ChainIdentity(standard="ens", chain="ethereum", identifier="bad space!")


class TestVerificationMethod:
    @pytest.mark.parametrize("method", list(SUPPORTED_VERIFICATION_METHODS))
    def test_each_supported_method(self, method: str):
        ci = ChainIdentity(standard="custom", chain="base", verification_method=method)
        assert ci.verification_method == method

    def test_unsupported_method_rejected(self):
        with pytest.raises(ValueError, match="Unsupported verification_method"):
            ChainIdentity(standard="custom", chain="base", verification_method="bogus")

    def test_default_verification_method(self):
        ci = ChainIdentity(standard="custom", chain="base")
        assert ci.verification_method == "on-chain-lookup"


class TestRoundTrip:
    def test_dict_round_trip(self):
        ci = ChainIdentity(
            standard="erc-8004",
            chain="base",
            contract="0x" + "a" * 40,
            token_id="1",
            verification_method="oracle",
        )
        rebuilt = chain_identity_from_dict(ci.model_dump(exclude_none=True))
        assert rebuilt is not None
        assert rebuilt.standard == "erc-8004"
        assert rebuilt.token_id == "1"

    def test_from_dict_none(self):
        assert chain_identity_from_dict(None) is None
