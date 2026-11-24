from base64 import b64encode
from hashlib import sha256
from io import BytesIO

import pytest
from alembic import command
from fastapi.testclient import TestClient
from openpyxl import Workbook

from margono_api import provision
from margono_api.main import app


def workbook_bytes(extra_column: bool = False) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.append(["Nama", "Unit"])
    sheet.append(["=1+1", "Fixture"])
    sheet.append(["Label, XLSX", None])
    sheet.append(["label, xlsx", "Fixture"])
    if extra_column:
        sheet.cell(2, 105, "Outside column limit")
    buffer = BytesIO()
    book.save(buffer)
    book.close()
    return buffer.getvalue()


@pytest.mark.postgres
def test_xlsx_and_manual_share_preview_and_preserve_evidence(
    isolated_database, monkeypatch
):
    config, _, _ = isolated_database
    command.upgrade(config, "head")
    monkeypatch.setattr("sys.argv", ["provision", "analyst", "osint_analyst"])
    monkeypatch.setattr(provision, "getpass", lambda _: "synthetic-fixture-test")
    provision.main()

    with TestClient(app) as client:
        login = client.post(
            "/api/v1/sessions",
            json={"username": "analyst", "password": "synthetic-fixture-test"},
        )
        auth = {"Authorization": f"Bearer {login.json()['token']}"}
        created = client.post(
            "/api/v1/cases",
            json={"fixture_id": "SYN-004", "purpose": "Fixture", "scope": "Uji XLSX"},
            headers={**auth, "Idempotency-Key": "xlsx-fixture"},
        )
        path = f"/api/v1/cases/{created.json()['id']}/imports"
        original = workbook_bytes()
        xlsx = {
            "content": b64encode(original).decode(),
            "format": "xlsx",
            "column": "Nama",
        }
        assert client.post(f"{path}/columns", json=xlsx, headers=auth).json() == {
            "columns": ["Nama", "Unit"]
        }
        preview = client.post(f"{path}/preview", headers=auth, json=xlsx)
        assert preview.status_code == 200, preview.text
        rows = preview.json()["rows"]
        assert [row["reference_label"] for row in rows] == [
            None,
            "Label, XLSX",
            "label, xlsx",
        ]
        assert [row["duplicate"] for row in rows] == [False, True, True]

        rejected = [
            {**xlsx, "content": "!!!"},
            {**xlsx, "content": b64encode(b"Not a workbook").decode()},
            {**xlsx, "content": b64encode(workbook_bytes(extra_column=True)).decode()},
        ]
        for payload in rejected:
            assert (
                client.post(f"{path}/preview", headers=auth, json=payload).status_code
                == 422
            )

        manual = {
            "content": 'Nama\n"Label, manual"\n"label, manual"\n',
            "format": "manual",
        }
        preview = client.post(f"{path}/preview", headers=auth, json=manual).json()
        assert [item["duplicate"] for item in preview["rows"]] == [True, True]
        for payload, evidence, format_name in [
            (xlsx, original, "xlsx"),
            (manual, manual["content"].encode(), "manual"),
        ]:
            headers = {**auth, "Idempotency-Key": format_name}
            response = client.post(path, headers=headers, json=payload)
            assert response.status_code == 201, response.text
            saved = response.json()
            assert saved["sha256"] == sha256(evidence).hexdigest()
            assert client.post(path, headers=headers, json=payload).json() == saved
            download = client.get(f"{path}/{saved['id']}/evidence", headers=auth)
            assert download.content == evidence
        history = client.get(path, headers=auth).json()["items"]
        assert {item["source_format"] for item in history} == {"manual", "xlsx"}
