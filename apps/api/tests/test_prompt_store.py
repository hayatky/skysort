from skysort_api.infra.prompt_store import load_prompt


def test_load_prompt_uses_repo_prompt_directory() -> None:
    body, prompt_hash = load_prompt("single_image_v1")

    assert "photo_id" in body
    assert len(prompt_hash) == 64
