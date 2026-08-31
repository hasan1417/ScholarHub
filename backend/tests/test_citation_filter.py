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


def test_optional_arguments_are_filtered_and_preserved() -> None:
    text = r"\cite[p. 5]{bad1} \citep[see][p.~5]{bad2}"

    filtered, invalid = filter_response(text, set())

    assert filtered == r"\cite[p. 5]{?MISSING:bad1?} \citep[see][p.~5]{?MISSING:bad2?}"
    assert [item["original_key"] for item in invalid] == ["bad1", "bad2"]
    assert [item["command"] for item in invalid] == [r"\cite", r"\citep"]
    for item in invalid:
        assert text[item["span_start"] : item["span_end"]] == item["original_key"]


def test_natbib_extra_and_capitalized_commands_are_filtered() -> None:
    commands = (
        "citealt",
        "citealp",
        "citeauthor",
        "citeyear",
        "citeyearpar",
        "citenum",
        "Citet",
        "Citep",
        "Citealt",
        "Citealp",
        "Citeauthor",
    )
    text = " ".join(f"\\{command}{{bad{index}}}" for index, command in enumerate(commands))

    filtered, invalid = filter_response(text, set())

    expected = " ".join(
        f"\\{command}{{?MISSING:bad{index}?}}" for index, command in enumerate(commands)
    )
    assert filtered == expected
    assert [item["command"] for item in invalid] == [f"\\{command}" for command in commands]


def test_biblatex_and_capitalized_commands_are_filtered() -> None:
    commands = (
        "parencite",
        "textcite",
        "autocite",
        "footcite",
        "smartcite",
        "supercite",
        "citetitle",
        "fullcite",
        "Parencite",
        "Textcite",
        "Autocite",
        "Smartcite",
        "Citetitle",
    )
    text = " ".join(f"\\{command}{{bad{index}}}" for index, command in enumerate(commands))

    filtered, invalid = filter_response(text, set())

    expected = " ".join(
        f"\\{command}{{?MISSING:bad{index}?}}" for index, command in enumerate(commands)
    )
    assert filtered == expected
    assert [item["original_key"] for item in invalid] == [
        f"bad{index}" for index in range(len(commands))
    ]


def test_multi_group_cites_validate_every_group() -> None:
    text = r"\cites{a}{b}"

    extracted = extract_cite_keys(text)
    filtered, invalid = filter_response(text, {"a"})

    assert [(key, command) for key, _, _, command in extracted] == [("a", r"\cites"), ("b", r"\cites")]
    assert filtered == r"\cites{a}{?MISSING:b?}"
    assert [item["original_key"] for item in invalid] == ["b"]
    assert text[invalid[0]["span_start"] : invalid[0]["span_end"]] == "b"


def test_multi_group_cites_leave_non_bibkey_group_untouched() -> None:
    filtered, invalid = filter_response(r"\cites{a} {unrelated group}", set())

    assert filtered == r"\cites{?MISSING:a?} {unrelated group}"
    assert [item["original_key"] for item in invalid] == ["a"]


def test_multi_group_cites_allow_space_before_another_bibkey_group() -> None:
    filtered, invalid = filter_response(r"\cites{a} {b}", set())

    assert filtered == r"\cites{?MISSING:a?} {?MISSING:b?}"
    assert [item["original_key"] for item in invalid] == ["a", "b"]


def test_all_multi_group_biblatex_commands_preserve_per_group_options() -> None:
    commands = ("parencites", "autocites", "textcites", "footcites")
    text = " ".join(f"\\{command}[see]{{good}}[p.~5]{{bad}}" for command in commands)

    filtered, invalid = filter_response(text, {"good"})

    expected = " ".join(
        f"\\{command}[see]{{good}}[p.~5]{{?MISSING:bad?}}" for command in commands
    )
    assert filtered == expected
    assert [item["command"] for item in invalid] == [f"\\{command}" for command in commands]


def test_nocite_wildcard_is_not_a_missing_key() -> None:
    text = r"\nocite{*} \nocite{bad}"

    extracted = extract_cite_keys(text)
    filtered, invalid = filter_response(text, set())

    assert [(key, command) for key, _, _, command in extracted] == [("bad", r"\nocite")]
    assert filtered == r"\nocite{*} \nocite{?MISSING:bad?}"
    assert [item["original_key"] for item in invalid] == ["bad"]


def test_non_citation_commands_are_left_untouched() -> None:
    text = r"\section{Introduction} \label{bad} \ref{bad} \citeunknown{bad}"

    filtered, invalid = filter_response(text, set())

    assert filtered == text
    assert invalid == []
    assert extract_cite_keys(text) == []


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
