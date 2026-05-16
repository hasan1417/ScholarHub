from app.services.citation_filter import extract_cite_keys, filter_response, make_bib_key


def test_single_valid_cite_passes_through() -> None:
    text = r"Prior work shows this \cite{validkey}."

    filtered, invalid = filter_response(text, {"validkey"})

    assert filtered == text
    assert invalid == []


def test_single_invalid_cite_gets_missing_marker() -> None:
    filtered, invalid = filter_response(r"Prior work shows this \cite{badkey}.", {"validkey"})

    assert filtered == r"Prior work shows this \cite{?MISSING:badkey?}."
    assert invalid == [
        {
            "original_key": "badkey",
            "span_start": 28,
            "span_end": 34,
            "command": r"\cite",
            "reason": "not_in_allowed_keys",
        }
    ]


def test_multi_key_cite_mixed_validity() -> None:
    filtered, invalid = filter_response(r"Several papers agree \cite{a,b,c}.", {"a", "c"})

    assert filtered == r"Several papers agree \cite{a,?MISSING:b?,c}."
    assert [item["original_key"] for item in invalid] == ["b"]


def test_supported_cite_commands_are_handled() -> None:
    text = r"\citet{bad1} \citep{bad2} \cite*{bad3} \citet*{bad4} \citep*{bad5}"

    filtered, invalid = filter_response(text, set())

    assert filtered == (
        r"\citet{?MISSING:bad1?} \citep{?MISSING:bad2?} "
        r"\cite*{?MISSING:bad3?} \citet*{?MISSING:bad4?} \citep*{?MISSING:bad5?}"
    )
    assert [item["command"] for item in invalid] == [
        r"\citet",
        r"\citep",
        r"\cite*",
        r"\citet*",
        r"\citep*",
    ]


def test_whitespace_tolerance_for_multi_key_cites() -> None:
    text = r"Whitespace \cite{ key1 , key2 }."

    extracted = extract_cite_keys(text)
    filtered, invalid = filter_response(text, {"key1"})

    assert [(key, command) for key, _, _, command in extracted] == [
        ("key1", r"\cite"),
        ("key2", r"\cite"),
    ]
    assert filtered == r"Whitespace \cite{key1,?MISSING:key2?}."
    assert [item["original_key"] for item in invalid] == ["key2"]


def test_make_bib_key_matches_frontend_algorithm_samples() -> None:
    refs = [
        (
            {
                "authors": ["John McMahan"],
                "year": 2017,
                "title": "Communication-Efficient Learning of Deep Networks from Decentralized Data",
            },
            "mcmahan2017communicatio",
        ),
        (
            {"authors": ["Yann LeCun"], "year": 2015, "title": "Deep learning"},
            "lecun2015deeplearning",
        ),
        (
            {"authors": ["Doe, Jane"], "year": 2024, "title": "A/B Testing: Lessons & Pitfalls!"},
            "jane2024abtesting",
        ),
        (
            {"authors": [], "year": 0, "title": "No Author Title"},
            "noauthortitl",
        ),
        ({}, "ref"),
    ]

    for ref, expected in refs:
        assert make_bib_key(ref) == expected


def test_empty_allowed_keys_marks_everything_invalid() -> None:
    filtered, invalid = filter_response(r"\cite{a,b}", set())

    assert filtered == r"\cite{?MISSING:a?,?MISSING:b?}"
    assert [item["original_key"] for item in invalid] == ["a", "b"]
