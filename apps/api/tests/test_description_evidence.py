"""D4-01 deterministic description structure tests."""

from claimtrace_api.services.description_evidence import _Page, derive_description_segments


def test_description_segments_resolve_exactly_to_persisted_page_text() -> None:
    text = (
        "문서 표지\n"
        "【기술분야】\n"
        "본 발명은 센서 네트워크의 측정값을 안정적으로 수집하는 기술에 관한 것이다. "
        "수집기는 복수의 센서로부터 데이터를 수신하고 저장한다.\n"
        "【배경기술】\n"
        "기존 시스템은 통신 장애가 발생하면 측정값 일부를 유실할 수 있다. "
        "이를 줄이기 위한 재전송 절차가 필요하다.\n"
        "【특허청구의범위】\n"
        "청구항 1. 센서 데이터를 수집하는 장치.\n"
    )

    status, segments, warnings = derive_description_segments([_Page(page_number=1, text=text)])

    assert status == "completed"
    assert warnings == []
    assert len(segments) == 2
    assert {segment.section_heading for segment in segments} == {"기술분야", "배경기술"}
    for segment in segments:
        assert segment.page_number == 1
        assert segment.text == text[segment.start_char : segment.end_char]
        assert "청구항 1" not in segment.text


def test_description_derivation_ignores_claim_section_before_description() -> None:
    text = (
        "명 세 서\n"
        "청구범위\n"
        "청구항 1\n"
        "센서 데이터를 수집하는 장치.\n"
        "발명의 설명\n"
        "기 술 분 야\n"
        "본 발명은 저장된 원문에서 직접 파생되는 충분히 긴 기술 설명 문장이다. "
        "정확한 페이지 문자 범위를 유지한다.\n"
    )

    status, segments, warnings = derive_description_segments([_Page(page_number=1, text=text)])

    assert status == "completed"
    assert warnings == []
    assert segments
    assert all("청구항 1" not in segment.text for segment in segments)
    assert all(segment.text == text[segment.start_char : segment.end_char] for segment in segments)


def test_description_derivation_stops_before_claim_section() -> None:
    text = (
        "발명의 설명\n"
        "이 설명은 저장된 원문에서 직접 파생되는 충분히 긴 기술 설명 문장이다. "
        "정확한 페이지 문자 범위를 유지한다.\n"
        "청구범위\n"
        "청구항 1. 이 텍스트는 설명 evidence에 포함되면 안 된다.\n"
    )

    status, segments, warnings = derive_description_segments([_Page(page_number=3, text=text)])

    assert status == "completed"
    assert warnings == []
    assert segments
    assert all("청구항 1" not in segment.text for segment in segments)
    assert all(segment.page_number == 3 for segment in segments)


def test_ambiguous_structure_is_explicitly_unsupported() -> None:
    text = (
        "공개특허공보\n"
        "이 문장은 기술 내용처럼 보일 수 있지만 설명 섹션이라는 명시적 구조가 없다. "
        "따라서 시스템은 이를 임의로 설명 evidence로 승격해서는 안 된다.\n"
    )

    status, segments, warnings = derive_description_segments([_Page(page_number=1, text=text)])

    assert status == "unsupported"
    assert segments == []
    assert warnings == ["description_heading_not_found"]
