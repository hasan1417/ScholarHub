import pytest

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


def test_collision_keys_match_allowed_scope_and_bibliography() -> None:
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch
    from uuid import uuid4

    from app.services.citation_filter import build_allowed_citation_keys, reference_citation_keys
    from app.services.discussion_ai.mixins.library_tools_mixin import LibraryToolsMixin

    project = SimpleNamespace(id=uuid4())
    refs = [
        SimpleNamespace(
            id=uuid4(), title=f"Communication efficient learning {ending}",
            authors=["Jane Smith"], year=2024, doi=None, url=None, journal=None,
        )
        for ending in ("beta", "alpha")
    ]
    keys = reference_citation_keys(refs)
    assert set(keys.values()) == {"smith2024communicatio", "smith2024communicatioa"}
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.all.return_value = refs
    with patch("app.services.citation_filter._resolve_project", return_value=project):
        allowed = build_allowed_citation_keys(db, project_id=project.id)
    # Exactly the canonical keys: an alias here would let the model cite a key no exporter emits.
    assert allowed == set(keys.values())

    class Library(LibraryToolsMixin):
        def _get_recent_papers(self, ctx: dict) -> list[dict]:
            # The recent-search copy must not consume a second suffix.
            return [{"title": refs[0].title, "authors": "Jane Smith", "year": 2024}]

    library = Library()
    library.db = db
    content = r"\cite{" + keys[refs[0].id] + "}"
    entries = library._generate_bibliography_entries({"project": project}, content)
    assert len(entries) == 1
    assert refs[0].title in entries[0]
    assert "\\bibitem{" + keys[refs[0].id] + "}" in entries[0]
    assert filter_response(content, allowed) == (content, [])


def test_collision_mapping_explicit_ordering_preserves_assigned_keys() -> None:
    from app.services.citation_filter import build_citation_key_map, citation_identity

    papers = [
        {"title": title, "authors": ["Jane Smith"], "year": 2024}
        for title in ("a!", "a?", "aa")
    ]
    mapping = build_citation_key_map(papers, ordering_key=citation_identity)
    assert mapping == build_citation_key_map(reversed(papers), ordering_key=citation_identity)
    assert mapping["smith2024aa"]["title"] == "a?"
    assert mapping["smith2024aaa"]["title"] == "aa"
    assert set(mapping) == {"smith2024a", "smith2024aa", "smith2024aaa"}


def test_collision_key_allocator_handles_more_than_26_suffixes() -> None:
    from app.services.citation_filter import generate_citation_key

    paper = {"title": "Same title", "authors": ["Jane Smith"], "year": 2024}
    used: set[str] = set()
    keys = [generate_citation_key(paper, used) for _ in range(29)]
    assert len(set(keys)) == 29
    assert keys[1].endswith("a")
    assert keys[26].endswith("z")
    assert keys[27].endswith("2")
    assert keys[28].endswith("3")


def test_citation_export_subset_keeps_full_library_collision_key() -> None:
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.services.citation_filter import reference_citation_keys
    from app.services.discussion_ai.mixins.library_tools_mixin import LibraryToolsMixin

    refs = [
        SimpleNamespace(
            id=uuid4(), title=f"Communication efficient learning {ending}",
            authors=["Jane Smith"], year=2024, doi=None, url=None, journal=None,
        )
        for ending in ("alpha", "beta")
    ]
    library = LibraryToolsMixin()
    library.db = MagicMock()
    query = library.db.query.return_value.join.return_value.filter.return_value
    query.first.return_value = refs[1]
    query.all.return_value = refs
    result = library._tool_export_citations(
        {"project": SimpleNamespace(id=uuid4())}, format="bibtex", scope="selected",
        reference_ids=[str(refs[1].id)],
    )
    expected_key = reference_citation_keys(refs)[refs[1].id]
    assert "@article{" + expected_key + "," in result["citations"]


def test_distinct_reference_records_with_identical_metadata_keep_unique_keys() -> None:
    from types import SimpleNamespace
    from app.services.citation_filter import reference_citation_keys

    refs = [
        SimpleNamespace(id=index, title="Same title", authors=["Jane Smith"], year=2024)
        for index in (1, 2)
    ]
    mapping = reference_citation_keys(refs)
    assert len(set(mapping.values())) == 2
    assert reference_citation_keys(reversed(refs)) == mapping


def test_allowed_keys_are_exactly_the_canonical_keys() -> None:
    """The filter's allowed set must equal what the allocator assigns: no aliases."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch
    from uuid import uuid4

    from app.services.citation_filter import build_allowed_citation_keys, reference_citation_keys

    project = SimpleNamespace(id=uuid4())
    refs = [
        SimpleNamespace(
            id=uuid4(), title=f"Communication efficient learning {ending}",
            authors=["Jane Smith"], year=2024, created_at=None,
        )
        for ending in ("alpha", "beta")
    ]
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.all.return_value = refs
    with patch("app.services.citation_filter._resolve_project", return_value=project), patch(
        "app.services.citation_filter.project_reference_entry_times", return_value={}
    ):
        allowed = build_allowed_citation_keys(db, project_id=project.id)

    canonical = set(reference_citation_keys(refs).values())
    assert allowed == canonical == {"smith2024communicatio", "smith2024communicatioa"}
    filtered, invalid = filter_response(r"\cite{smith2024communicatiob}", allowed)
    assert filtered == r"\cite{?MISSING:smith2024communicatiob?}"
    assert [item["original_key"] for item in invalid] == ["smith2024communicatiob"]


def test_existing_key_survives_earlier_created_reference_linked_later() -> None:
    """Collision order follows entry into the scope, so a later link never renames an existing key."""
    from datetime import datetime, timedelta
    from types import SimpleNamespace
    from uuid import UUID

    from app.services.citation_filter import reference_citation_keys

    t0 = datetime(2026, 1, 1)
    a = SimpleNamespace(
        id=UUID("ffffffff-0000-0000-0000-000000000001"), title="Deep learning for X",
        authors=["Jane Smith"], year=2020, created_at=t0,
    )
    c = SimpleNamespace(  # created before A, sorts before A by id and title, linked after A
        id=UUID("00000000-0000-0000-0000-000000000003"), title="Deep learning for B",
        authors=["Jane Smith"], year=2020, created_at=t0 - timedelta(days=4),
    )
    before = reference_citation_keys([a], entered_at={a.id: t0})
    after = reference_citation_keys([c, a], entered_at={a.id: t0, c.id: t0 + timedelta(days=2)})

    assert before[a.id] == after[a.id] == "smith2020deeplearning"
    assert after[c.id] == "smith2020deeplearninga"


@pytest.mark.parametrize(
    "text, command",
    [
        (r"\footnote{see \cite{fake}}", r"\cite"),
        (r"\caption{Results from \citep{fake}}", r"\citep"),
        (r"\textbf{\cite{fake}}", r"\cite"),
        (r"\emph{as in \citet{fake}}", r"\citet"),
        (r"\citep[see \citet{fake}]{real}", r"\citet"),
        (r"\item{\cite{fake}}", r"\cite"),
    ],
    ids=["footnote", "caption", "textbf", "emph", "citation_inside_opts", "item"],
)
def test_nested_citation_is_filtered(text: str, command: str) -> None:
    filtered, invalid = filter_response(text, {"real"})

    assert filtered == text.replace("{fake}", "{?MISSING:fake?}")
    start = text.index("fake")
    assert invalid == [{
        "original_key": "fake",
        "span_start": start,
        "span_end": start + len("fake"),
        "command": command,
        "reason": "not_in_allowed_keys",
    }]
    extracted = extract_cite_keys(text)
    assert ("fake", start, start + len("fake"), command) in extracted
    assert [key for key, _, _, _ in extracted] == (
        ["fake", "real"] if "{real}" in text else ["fake"]
    )


def test_nested_and_outer_invalid_citations_preserve_absolute_spans() -> None:
    text = r"\citep*[see \citet{inner}][p.~5]{outer} and \cite{last}"

    filtered, invalid = filter_response(text, set())

    assert filtered == (
        r"\citep*[see \citet{?MISSING:inner?}][p.~5]{?MISSING:outer?} "
        r"and \cite{?MISSING:last?}"
    )
    assert [item["original_key"] for item in invalid] == ["inner", "outer", "last"]
    assert [item["command"] for item in invalid] == [r"\citet", r"\citep*", r"\cite"]
    assert extract_cite_keys(text) == [
        (item["original_key"], item["span_start"], item["span_end"], item["command"])
        for item in invalid
    ]
    for item in invalid:
        assert text[item["span_start"]:item["span_end"]] == item["original_key"]


def test_nested_citation_in_multi_group_continuation_options() -> None:
    text = r"\cites{first}[see \citet{inner}]{last}"

    filtered, invalid = filter_response(text, set())

    assert filtered == (
        r"\cites{?MISSING:first?}[see \citet{?MISSING:inner?}]{?MISSING:last?}"
    )
    assert [item["original_key"] for item in invalid] == ["first", "inner", "last"]
    assert [key for key, _, _, _ in extract_cite_keys(text)] == ["first", "inner", "last"]
    for item in invalid:
        assert text[item["span_start"]:item["span_end"]] == item["original_key"]


def test_section_label_and_bare_groups_are_untouched() -> None:
    text = r"\section{Introduction} \label{x} {fake}"

    assert filter_response(text, set()) == (text, [])
    assert extract_cite_keys(text) == []


@pytest.mark.parametrize("group", [" fake", "fake,", " fake , ", " real , fake, "])
def test_multi_group_cites_accept_key_whitespace_and_trailing_comma(group: str) -> None:
    text = r"\cites{real}{" + group + "}"

    filtered, invalid = filter_response(text, {"real"})

    expected_keys = "real,?MISSING:fake?" if "real" in group else "?MISSING:fake?"
    assert filtered == r"\cites{real}{" + expected_keys + "}"
    assert [item["original_key"] for item in invalid] == ["fake"]
    start = text.index("fake")
    assert (invalid[0]["span_start"], invalid[0]["span_end"]) == (start, start + 4)
    assert ("fake", start, start + 4, r"\cites") in extract_cite_keys(text)


@pytest.mark.parametrize("command", ["footfullcite", "footcitetext", "citeurl", "citedate"])
def test_additional_biblatex_citation_commands(command: str) -> None:
    text = f"\\{command}{{real,fake}}"

    filtered, invalid = filter_response(text, {"real"})

    assert filtered == f"\\{command}{{real,?MISSING:fake?}}"
    assert [item["original_key"] for item in invalid] == ["fake"]
    assert [item["command"] for item in invalid] == [f"\\{command}"]
    assert [key for key, _, _, _ in extract_cite_keys(text)] == ["real", "fake"]


@pytest.mark.parametrize(
    "command", ["volcite", "pvolcite", "fvolcite", "ftvolcite", "svolcite", "tvolcite", "avolcite"]
)
@pytest.mark.parametrize("notes", [False, True], ids=["plain", "notes"])
def test_volume_citation_commands_validate_only_key_group(command: str, notes: bool) -> None:
    prefix = f"\\{command}" + ("[see]{42}[p.~5]" if notes else "{42}")
    text = prefix + "{real,fake}"

    filtered, invalid = filter_response(text, {"real"})

    assert filtered == prefix + "{real,?MISSING:fake?}"
    assert [item["original_key"] for item in invalid] == ["fake"]
    assert [item["command"] for item in invalid] == [f"\\{command}"]
    assert extract_cite_keys(text) == [
        (key, text.index(key), text.index(key) + len(key), f"\\{command}")
        for key in ("real", "fake")
    ]
    assert filter_response(prefix + "{real}", {"real"}) == (prefix + "{real}", [])


def test_volume_citation_preserves_nested_citation_in_postnote() -> None:
    text = r"\Volcite[see]{42}[as in \citet{fake}]{real}"

    filtered, invalid = filter_response(text, {"real"})

    assert filtered == r"\Volcite[see]{42}[as in \citet{?MISSING:fake?}]{real}"
    assert [item["original_key"] for item in invalid] == ["fake"]
    assert [key for key, _, _, _ in extract_cite_keys(text)] == ["fake", "real"]


@pytest.mark.parametrize("text", [r"\cite{\cite{fake}}", r"\cites{real}{\cite{fake}}"])
def test_nested_command_in_malformed_key_group_does_not_overlap_spans(text: str) -> None:
    filtered, invalid = filter_response(text, {"real"})

    assert filtered == text.replace("{fake}", "{?MISSING:fake?}")
    assert [item["original_key"] for item in invalid] == ["fake"]
    start = text.index("fake")
    assert (invalid[0]["span_start"], invalid[0]["span_end"]) == (start, start + 4)
    assert [key for key, _, _, _ in extract_cite_keys(text)] == (
        ["real", "fake"] if "{real}" in text else ["fake"]
    )


def test_adding_earlier_identity_collision_preserves_existing_key() -> None:
    from app.services.citation_filter import build_citation_key_map

    first = {"title": "Communication efficient learning zebra", "authors": ["Jane Smith"], "year": 2024}
    later = {**first, "title": "Communication efficient learning alpha"}
    original_key = next(iter(build_citation_key_map([first])))

    assert build_citation_key_map([first, later])[original_key] == first


def test_adding_native_base_collision_preserves_existing_suffix() -> None:
    from app.services.citation_filter import build_citation_key_map

    papers = [
        {"title": title, "authors": ["Jane Smith"], "year": 2024}
        for title in ("a!", "a?", "aa")
    ]
    previous = build_citation_key_map(papers[:2])
    extended = build_citation_key_map(papers)

    assert all(extended[key] == paper for key, paper in previous.items())


def test_reference_collision_keys_follow_creation_order_then_id() -> None:
    from datetime import datetime, timedelta
    from types import SimpleNamespace
    from app.services.citation_filter import reference_citation_keys

    created = datetime(2026, 1, 1)
    first = SimpleNamespace(id=30, title="Communication efficient learning zebra", authors=["Jane Smith"], year=2024, created_at=created)
    later = SimpleNamespace(id=10, title="Communication efficient learning alpha", authors=first.authors, year=2024, created_at=created + timedelta(days=1))
    original_key = reference_citation_keys([first])[first.id]

    assert reference_citation_keys([later, first])[first.id] == original_key


@pytest.mark.parametrize("created_at", [None, "2026-01-01"])
def test_reference_collision_keys_break_creation_ties_by_id(created_at: str | None) -> None:
    from types import SimpleNamespace
    from app.services.citation_filter import reference_citation_keys

    refs = [
        SimpleNamespace(
            id=index, title=f"Communication efficient learning {ending}",
            authors=["Jane Smith"], year=2024, created_at=created_at,
        )
        for index, ending in [(20, "alpha"), (10, "zebra")]
    ]

    assert reference_citation_keys(refs)[10] == "smith2024communicatio"


def test_citation_lookup_uses_reference_creation_order() -> None:
    from datetime import datetime, timedelta
    from types import SimpleNamespace
    from app.services.citation_filter import build_citation_lookup, reference_citation_keys

    created = datetime(2026, 1, 1)
    refs = [
        SimpleNamespace(
            id=index, title=title, authors=["Jane Smith"], year=2024,
            created_at=created + timedelta(days=age),
        )
        for index, title, age in [(10, "aa", 2), (20, "a?", 1), (30, "a!", 0)]
    ]
    lookup = build_citation_lookup([
        {**vars(ref), "_reference_id": ref.id} for ref in refs
    ])

    for reference_id, key in reference_citation_keys(refs).items():
        assert lookup[key]["_reference_id"] == reference_id


def test_citation_lookup_preserves_insertion_order_without_reference_ids() -> None:
    from app.services.citation_filter import build_citation_lookup

    papers = [
        {"title": title, "authors": ["Jane Smith"], "year": 2024}
        for title in ("a?", "a!")
    ]

    assert build_citation_lookup(papers)["smith2024a"] == papers[0]


@pytest.mark.parametrize(
    "text",
    [
        r"\volcites[see]{42}[p.~5]{fake}{43}{real}",
        r"\citetalias{fake}",
        r"\citeA{fake}",
        r"\shortcite{fake}",
        r"\citefield{fake}{title}",
        r"\citename{fake}{author}",
        r"\cites(see)(p.~5){fake}",
        r"\autocites(see)[p.~1]{fake}",
        r"\cite<see>{fake}",
    ],
)
def test_remaining_citation_forms_validate_keys(text: str) -> None:
    filtered, invalid = filter_response(text, {"real"})

    assert filtered == text.replace("{fake}", "{?MISSING:fake?}")
    assert [item["original_key"] for item in invalid] == ["fake"]
    assert [key for key, _, _, _ in extract_cite_keys(text)] == (
        ["fake", "real"] if "{real}" in text else ["fake"]
    )


def test_volcites_validates_continuation_keys_and_preserves_volumes() -> None:
    text = r"\volcites(see){42}{real}[also]{43}[p.~5]{fake}"

    assert filter_response(text, {"real"})[0] == text.replace("{fake}", "{?MISSING:fake?}")
    assert [key for key, _, _, _ in extract_cite_keys(text)] == ["real", "fake"]
