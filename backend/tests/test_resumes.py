def _upload(client, headers, docx_bytes, filename="resume.docx", name=None):
    return client.post(
        "/api/v1/resumes",
        headers=headers,
        files={
            "file": (
                filename,
                docx_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data={"name": name} if name else {},
    )


def test_upload_extracts_text_including_tables(client, auth_headers, docx_bytes):
    r = _upload(client, auth_headers, docx_bytes)
    assert r.status_code == 201, r.text
    body = r.json()
    assert "Senior Data Analyst" in body["parsed_text"]
    # Table content must survive extraction, not just paragraphs.
    assert "dbt" in body["parsed_text"]


def test_first_upload_becomes_default_second_does_not(
    client, auth_headers, docx_bytes
):
    first = _upload(client, auth_headers, docx_bytes, name="First").json()
    second = _upload(client, auth_headers, docx_bytes, name="Second").json()
    assert first["is_default"] is True
    assert second["is_default"] is False


def test_setting_a_new_default_clears_the_previous_one(
    client, auth_headers, docx_bytes
):
    first = _upload(client, auth_headers, docx_bytes, name="First").json()
    second = _upload(client, auth_headers, docx_bytes, name="Second").json()

    r = client.patch(
        f"/api/v1/resumes/{second['id']}",
        headers=auth_headers,
        json={"is_default": True},
    )
    assert r.status_code == 200
    assert r.json()["is_default"] is True

    again = client.get(f"/api/v1/resumes/{first['id']}", headers=auth_headers)
    assert again.json()["is_default"] is False


def test_list_omits_parsed_text(client, auth_headers, docx_bytes):
    _upload(client, auth_headers, docx_bytes)
    r = client.get("/api/v1/resumes", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert "parsed_text" not in r.json()[0]


def test_unsupported_file_type_is_415(client, auth_headers):
    r = client.post(
        "/api/v1/resumes",
        headers=auth_headers,
        files={"file": ("resume.exe", b"MZ\x00\x00", "application/octet-stream")},
    )
    assert r.status_code == 415


def test_empty_upload_is_400(client, auth_headers):
    r = client.post(
        "/api/v1/resumes",
        headers=auth_headers,
        files={"file": ("resume.docx", b"", "application/octet-stream")},
    )
    assert r.status_code == 400


def test_download_returns_the_original_bytes(client, auth_headers, docx_bytes):
    uploaded = _upload(client, auth_headers, docx_bytes).json()
    r = client.get(f"/api/v1/resumes/{uploaded['id']}/download", headers=auth_headers)
    assert r.status_code == 200
    assert r.content == docx_bytes


def test_delete_promotes_another_resume_to_default(client, auth_headers, docx_bytes):
    first = _upload(client, auth_headers, docx_bytes, name="First").json()
    second = _upload(client, auth_headers, docx_bytes, name="Second").json()

    assert client.delete(
        f"/api/v1/resumes/{first['id']}", headers=auth_headers
    ).status_code == 204

    # The user must never be left with resumes but no default.
    remaining = client.get(f"/api/v1/resumes/{second['id']}", headers=auth_headers)
    assert remaining.json()["is_default"] is True


def test_resumes_are_not_visible_across_tenants(client, make_user, docx_bytes):
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")

    resume = _upload(client, alice, docx_bytes).json()

    assert client.get("/api/v1/resumes", headers=bob).json() == []
    assert client.get(
        f"/api/v1/resumes/{resume['id']}", headers=bob
    ).status_code == 404
    assert client.delete(
        f"/api/v1/resumes/{resume['id']}", headers=bob
    ).status_code == 404
    assert client.get(
        f"/api/v1/resumes/{resume['id']}/download", headers=bob
    ).status_code == 404


def test_upload_requires_authentication(client, docx_bytes):
    r = client.post(
        "/api/v1/resumes",
        files={"file": ("resume.docx", docx_bytes, "application/octet-stream")},
    )
    assert r.status_code == 401
