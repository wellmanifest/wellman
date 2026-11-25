import hashlib
import json
from importlib import resources

import pytest

from wellman.deployment_check import inspect_deployment, main


def examples():
    raw = resources.files("wellman.schemas").joinpath("deployment.schema.json").read_bytes()
    # wellmanifest/deployment 8f19c0c, schemas/deployment.schema.json
    assert hashlib.sha256(raw).hexdigest() == "8f2a555b9465057df83c0e58a0bb611e4bc6593010966fb0b4cf28460105c136"
    return json.loads(raw)["examples"]


def test_missing_consumer_contract_even_with_dockerfile(tmp_path, capsys):
    (tmp_path / "Dockerfile").touch()
    assert main(["--root", str(tmp_path)]) == 1
    assert json.loads(capsys.readouterr().out)["findings"][0]["code"] == "GOV-DEPLOYMENT-CONTRACT-MISSING"
    (tmp_path / "deployment.json").write_text('{"target":{},"target":{}}')
    assert inspect_deployment(tmp_path)["findings"][0]["code"] == "GOV-DEPLOYMENT-CONTRACT-INVALID"


@pytest.mark.parametrize("index", [0, 1])
def test_canonical_examples_and_independently_resolved_binding(tmp_path, index):
    pytest.importorskip("jsonschema")
    definition = examples()[index]
    content = b"opaque independently resolved record"
    f = tmp_path / "resolved"
    f.write_bytes(content)
    ref = definition["target"]["bindingRef"]
    definition["target"]["bindingDigest"] = "sha256:" + hashlib.sha256(content).hexdigest()
    (tmp_path / "deployment.json").write_text(json.dumps(definition))
    assert inspect_deployment(tmp_path)["binding_status"] == "declared"
    good = inspect_deployment(tmp_path, ref, f)
    assert good["valid"] and good["binding_status"] == "digest_matches"
    assert good["deployment_authorized"] is False
    assert inspect_deployment(tmp_path, "other", f)["binding_status"] == "reference_mismatch"
    f.write_bytes(b"changed")
    assert inspect_deployment(tmp_path, ref, f)["binding_status"] == "digest_mismatch"
    f.unlink()
    assert not inspect_deployment(tmp_path, ref, f)["valid"]


def test_partial_binding_and_nonmonotonic_canary_are_reported(tmp_path):
    pytest.importorskip("jsonschema")
    path = tmp_path / "deployment.json"
    definition = examples()[0]
    del definition["target"]["bindingDigest"]
    path.write_text(json.dumps(definition))
    assert any("bindingDigest" in f["message"] for f in inspect_deployment(tmp_path)["findings"])
    definition = examples()[0]
    definition["strategy"].update(type="canary", stages=[40, 5, 100])
    path.write_text(json.dumps(definition))
    assert inspect_deployment(tmp_path)["findings"][0]["code"] == "GOV-DEPLOYMENT-CANARY-STAGES"
