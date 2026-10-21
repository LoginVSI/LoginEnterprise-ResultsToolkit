import json
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_connector_build_retains_exports_and_resources(tmp_path):
    package = tmp_path / "ResultsToolkit.mez"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/build_connector.py"), "--out", str(package)],
        check=True,
    )
    with ZipFile(package) as archive:
        assert set(archive.namelist()) == {"ResultsToolkit.pq", "icon16.png", "icon32.png"}
        assert (
            archive.read("ResultsToolkit.pq")
            == (ROOT / "adapters/powerbi/ResultsToolkit.pq").read_bytes()
        )


@pytest.mark.skipif(sys.platform != "win32", reason="Windows user-scoped installer")
def test_user_connector_install_preserves_other_connector_and_backs_up(tmp_path):
    package = tmp_path / "current.mez"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/build_connector.py"), "--out", str(package)],
        check=True,
    )
    docs = tmp_path / "Documents"
    old = docs / "Microsoft Power BI Desktop/Custom Connectors/ResultsToolkit.mez"
    other = docs / "Power BI Desktop/Custom Connectors/LE-PBI-Connector.mez"
    old.parent.mkdir(parents=True)
    other.parent.mkdir(parents=True)
    shutil.copy2(package, old)
    other.write_bytes(b"separate connector must remain intact")
    backup = tmp_path / "backup"
    command = [
        "powershell.exe",
        "-NoProfile",
        "-File",
        str(ROOT / "scripts/Install-LEResultsConnector.ps1"),
        "-Package",
        str(package),
        "-DocumentsDirectory",
        str(docs),
        "-BackupDirectory",
        str(backup),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    target = docs / "Power BI Desktop/Custom Connectors/ResultsToolkit.mez"
    assert target.read_bytes() == package.read_bytes()
    assert not old.exists()
    assert other.read_bytes() == b"separate connector must remain intact"
    assert Path(receipt["Backups"][0]["Backup"]).read_bytes() == package.read_bytes()
    assert receipt["HostLoaded"] == "unverified" and not receipt["SecuritySettingsChanged"]
    # Backups cannot be registrations in either watched directory.
    result = subprocess.run(
        command[:-1] + [str(target.parent / "backups")], capture_output=True, text=True
    )
    assert result.returncode == 2 and target.read_bytes() == package.read_bytes()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows user-scoped installer")
def test_connector_rejects_wrong_package_before_touching_documents(tmp_path):
    package = tmp_path / "bad.mez"
    with ZipFile(package, "w") as archive:
        archive.writestr("ResultsToolkit.pq", "section Wrong;")
    docs = tmp_path / "Documents"
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-File",
            str(ROOT / "scripts/Install-LEResultsConnector.ps1"),
            "-Package",
            str(package),
            "-DocumentsDirectory",
            str(docs),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2 and not docs.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows user-scoped installer")
@pytest.mark.parametrize("failure_stage", ["move", "receipt", "locked_cleanup", "receipt_same_folder"])
def test_connector_failure_rolls_back_and_removes_only_its_staged_file(tmp_path, failure_stage):
    package = tmp_path / "current.mez"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/build_connector.py"), "--out", str(package)],
        check=True,
    )
    docs = tmp_path / "Documents"
    old_folder = "Power BI Desktop" if failure_stage == "receipt_same_folder" else "Microsoft Power BI Desktop"
    original = docs / old_folder / "Custom Connectors/ResultsToolkit.mez"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"previous toolkit preserved")

    def quote(path):
        return "'" + str(path).replace("'", "''") + "'"

    if failure_stage == "move":
        fault = "function Move-Item { param($LiteralPath,$Destination) if($LiteralPath.EndsWith('.tmp')){throw 'synthetic final move failure'} Microsoft.PowerShell.Management\\Move-Item -LiteralPath $LiteralPath -Destination $Destination }; "
    elif failure_stage == "locked_cleanup":
        fault = "function ConvertTo-Json { param([Parameter(ValueFromPipeline=$true)]$InputObject, [int]$Depth) process { $global:heldFile = [IO.File]::Open($InputObject.Target, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None); throw 'synthetic receipt failure with locked target' } }; "
    else:
        fault = "function ConvertTo-Json { throw 'synthetic receipt failure' }; "
    command = (
        fault
        + " & "
        + quote(ROOT / "scripts/Install-LEResultsConnector.ps1")
        + " -Package "
        + quote(package)
        + " -DocumentsDirectory "
        + quote(docs)
        + " -BackupDirectory "
        + quote(tmp_path / "backup")
        + "; exit $LASTEXITCODE"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command], capture_output=True, text=True
    )
    assert result.returncode == 2 and original.read_bytes() == b"previous toolkit preserved"
    assert not list(original.parent.glob("*.tmp"))
    target = docs / "Power BI Desktop/Custom Connectors/ResultsToolkit.mez"
    if failure_stage == "locked_cleanup":
        assert target.read_bytes() == package.read_bytes()
        assert "could not be inspected or removed; retained backups:" in result.stderr
    elif failure_stage == "receipt_same_folder":
        assert target.read_bytes() == b"previous toolkit preserved"
    else:
        assert not target.exists()
    assert "Connector installation failed:" in result.stderr
    assert (tmp_path / "backup/0-ResultsToolkit.mez").read_bytes() == original.read_bytes()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows user-scoped installer")
def test_connector_relative_paths_diagnosis_and_hash_refusal(tmp_path):
    package = tmp_path / "current.mez"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/build_connector.py"), "--out", str(package)],
        check=True,
    )
    sub = tmp_path / "sub"
    sub.mkdir()
    script = str(ROOT / "scripts/Install-LEResultsConnector.ps1").replace("'", "''")
    prefix = (
        "Set-Location -LiteralPath '"
        + str(sub).replace("'", "''")
        + "'; & '"
        + script
        + "' -Package ../current.mez -DocumentsDirectory Documents -BackupDirectory Backups"
    )

    def run(suffix):
        return subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", prefix + suffix + "; exit $LASTEXITCODE"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )

    bad = run(" -ExpectedSha256 " + "0" * 64)
    assert bad.returncode == 2 and not (sub / "Documents").exists()
    diagnosis = run(" -DiagnoseOnly")
    assert diagnosis.returncode == 0, diagnosis.stderr
    assert json.loads(diagnosis.stdout)["HostLoaded"] == "unverified"
    assert not (sub / "Documents").exists()
    installed = run("")
    assert installed.returncode == 0, installed.stderr
    assert (
        sub / "Documents/Power BI Desktop/Custom Connectors/ResultsToolkit.mez"
    ).read_bytes() == package.read_bytes()
    assert not (tmp_path / "Documents").exists()
