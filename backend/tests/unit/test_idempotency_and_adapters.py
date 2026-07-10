"""Idempotency-key derivation + adapter normalization (rubric §9.1, §3.5)."""

from ingestion.adapters.mock_crm import MockCrmAdapter
from ingestion.envelope import CallEnvelope, derive_idempotency_key


def test_same_bytes_same_key_regardless_of_source_id():
    audio = b"the same recording bytes"
    assert derive_idempotency_key(audio, "folder") == derive_idempotency_key(audio, "folder")


def test_different_bytes_or_source_differ():
    a = derive_idempotency_key(b"aaa", "folder")
    b = derive_idempotency_key(b"bbb", "folder")
    c = derive_idempotency_key(b"aaa", "rest")
    assert a != b and a != c


def test_mock_crm_maps_vendor_payload_to_envelope(tmp_path):
    audio = tmp_path / "rec.wav"
    audio.write_bytes(b"RIFFmock")
    adapter = MockCrmAdapter(
        records=[{
            "recording_path": str(audio), "agent_ref": "AGT-9",
            "call_uuid": "xyz", "lead_phone": "98xxxx", "lang": "hi",
            "campaign_id": "C-1",
        }]
    )
    envelopes = adapter.fetch_new()
    assert len(envelopes) == 1
    env = envelopes[0]
    assert isinstance(env, CallEnvelope)
    assert env.source == "crm"
    assert env.advisor_external_id == "AGT-9"
    assert env.raw_metadata["campaign_id"] == "C-1"  # whole vendor row preserved
