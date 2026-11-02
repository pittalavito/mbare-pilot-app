"""Jira (ADF) and Confluence (storage XHTML) rich text as Markdown: tables,
code blocks with their language, lists, panels, links and marks."""
import pytest

from domain.client.atlassian.confluence import storage_to_markdown
from domain.client.atlassian.jira import adf_to_markdown
from domain.client.atlassian.markdown import fenced, inline_code, prefix_lines, table, tidy


def _text(text, *marks, **attrs):
    node = {"type": "text", "text": text}
    if marks:
        node["marks"] = [{"type": mark, **({"attrs": attrs} if mark == "link" else {})} for mark in marks]
    return node


def _p(*content):
    return {"type": "paragraph", "content": list(content)}


def _doc(*content):
    return {"type": "doc", "content": list(content)}


# ------------------------------------------------------------------ helpers

def test_fenced_uses_a_longer_fence_than_the_code_and_keeps_the_language():
    assert fenced('{"a": 1}\n', " json ") == '```json\n{"a": 1}\n```'
    assert fenced("usa ``` qui") == "````\nusa ``` qui\n````"


def test_inline_code_handles_backticks_and_empty_text():
    assert inline_code("x") == "`x`"
    assert inline_code("a`b") == "`` a`b ``"
    assert inline_code("") == ""


def test_table_pads_short_rows_escapes_pipes_and_flattens_cells():
    assert table([["A", "B"], ["1 | 2"], ["riga\nsu due", "x"]]) == (
        "| A | B |\n| --- | --- |\n| 1 \\| 2 |  |\n| riga su due | x |"
    )
    assert table([]) == "" and table([[]]) == ""


def test_prefix_lines_indents_the_following_lines_but_not_the_blank_ones():
    assert prefix_lines("uno\n\ndue", "- ", "  ") == "- uno\n\n  due"
    assert prefix_lines("a\n\nb", "> ", "> ") == "> a\n>\n> b"


def test_tidy_collapses_blank_lines_but_leaves_code_blocks_alone():
    text = "\n\ntesto   \n\n\n\naltro\n```\nriga   \n\n\n\nfine\n```\n\n\nultima\n\n"
    assert tidy(text) == "testo\n\naltro\n```\nriga   \n\n\n\nfine\n```\n\nultima"


# --------------------------------------------------------------------- Jira

def test_adf_tables_become_markdown_tables():
    def cell(kind, text):
        return {"type": kind, "content": [_p(_text(text))]}

    doc = _doc({"type": "table", "content": [
        {"type": "tableRow", "content": [cell("tableHeader", "Nome"), cell("tableHeader", "Valore")]},
        {"type": "tableRow", "content": [cell("tableCell", "a | b"), {"type": "tableCell", "content": [
            _p(_text("1")), _p(_text("riga"), {"type": "hardBreak"}, _text("due")),
        ]}]},
    ]})

    assert adf_to_markdown(doc) == "| Nome | Valore |\n| --- | --- |\n| a \\| b | 1 riga due |"


def test_adf_code_blocks_keep_their_json_and_language():
    doc = _doc(
        {"type": "codeBlock", "attrs": {"language": "json"}, "content": [_text('{\n  "id": 1\n}')]},
        {"type": "codeBlock", "content": [_text("senza linguaggio")]},
    )

    assert adf_to_markdown(doc) == '```json\n{\n  "id": 1\n}\n```\n\n```\nsenza linguaggio\n```'


def test_adf_headings_lists_quotes_and_rules():
    doc = _doc(
        {"type": "heading", "attrs": {"level": 3}, "content": [_text("Passi")]},
        {"type": "orderedList", "attrs": {"order": 3}, "content": [
            {"type": "listItem", "content": [_p(_text("apri")), {"type": "bulletList", "content": [
                {"type": "listItem", "content": [_p(_text("sotto"))]},
            ]}]},
            {"type": "listItem", "content": [_p(_text("chiudi"))]},
        ]},
        {"type": "blockquote", "content": [_p(_text("citazione"))]},
        {"type": "panel", "attrs": {"panelType": "info"}, "content": [_p(_text("nota"))]},
        {"type": "rule"},
        {"type": "heading", "attrs": {"level": 9}, "content": [_text("troppo profondo")]},
    )

    assert adf_to_markdown(doc) == (
        "### Passi\n\n3. apri\n\n   - sotto\n4. chiudi\n\n> citazione\n\n> nota\n\n---\n\n###### troppo profondo"
    )


def test_adf_task_lists():
    doc = _doc({"type": "taskList", "content": [
        {"type": "taskItem", "attrs": {"state": "DONE"}, "content": [_text("fatto")]},
        {"type": "taskItem", "attrs": {"state": "TODO"}, "content": [_text("da fare")]},
        {"type": "taskList", "content": [{"type": "taskItem", "content": [_text("annidato")]}]},
    ]})

    assert adf_to_markdown(doc) == "- [x] fatto\n- [ ] da fare\n- [ ] - [ ] annidato"


def test_adf_inline_marks_links_and_nodes():
    doc = _doc(_p(
        _text("grassetto", "strong"), _text(" "), _text("corsivo", "em"), _text(" "), _text("via", "strike"), _text(" "),
        _text("cmd", "code"), _text(" "), _text("sito", "link", href="https://x.io"), _text(" "), _text("vuoto", "link"),
        _text(" "), {"type": "emoji", "attrs": {"shortName": ":ok:"}}, {"type": "emoji", "attrs": {"text": "😀", "shortName": ":s:"}},
        _text(" "), {"type": "inlineCard", "attrs": {"url": "https://y.io"}}, {"type": "inlineCard", "attrs": {}},
        _text(" "), {"type": "status", "attrs": {"text": "IN CORSO"}},
        _text(" "), {"type": "date", "attrs": {"timestamp": "1767225600000"}}, {"type": "date", "attrs": {}},
        _text(" "), {"type": "mention", "attrs": {"text": "@Ada"}},
        {"type": "inlineExtension", "content": [_text(" ext")]},
    ))

    assert adf_to_markdown(doc) == (
        "**grassetto** *corsivo* ~~via~~ `cmd` [sito](https://x.io) vuoto :ok:😀 <https://y.io> [IN CORSO] 2026-01-01 @Ada ext"
    )


def test_adf_media_is_dropped_and_unknown_nodes_keep_their_text():
    doc = _doc(
        {"type": "mediaSingle", "content": [{"type": "media", "attrs": {"id": "x"}}]},
        {"type": "expand", "content": [_p(_text("dentro"))]},
        _text("testo sciolto"),
    )

    assert adf_to_markdown(doc) == "dentro\n\ntesto sciolto"
    assert adf_to_markdown("già testo") == "già testo"
    assert adf_to_markdown(_p(_text("solo"))) == "solo"
    assert adf_to_markdown(_text("nodo", "strong")) == "**nodo**"
    assert adf_to_markdown({"type": "expand", "content": [_text("sciolto"), _p(_text("poi blocco"))]}) == "sciolto\n\npoi blocco"


# --------------------------------------------------------------- Confluence

def test_storage_tables_become_markdown_tables():
    html = (
        "<table><thead><tr><th>Nome</th><th>Valore</th></tr></thead>"
        "<tbody><tr><td><p>a | b</p><p>seconda</p></td><td>1<br/>2</td></tr></tbody>"
        "<tfoot><tr><td>tot</td></tr></tfoot><colgroup><col/></colgroup></table>"
        "<table><tr><td>senza</td><td>tbody</td></tr></table>"
    )

    assert storage_to_markdown(html) == (
        "| Nome | Valore |\n| --- | --- |\n| a \\| b seconda | 1 2 |\n| tot |  |\n\n| senza | tbody |\n| --- | --- |"
    )


def test_storage_code_macros_keep_their_cdata_body_and_language():
    html = (
        '<ac:structured-macro ac:name="code"><ac:parameter ac:name="language">json</ac:parameter>'
        '<ac:plain-text-body><![CDATA[{\n  "id": 1,\n  "tag": "<b>&amp;"\n}]]></ac:plain-text-body></ac:structured-macro>'
        '<ac:structured-macro ac:name="noformat"><ac:plain-text-body><![CDATA[a   b]]></ac:plain-text-body></ac:structured-macro>'
        '<ac:structured-macro ac:name="code"></ac:structured-macro>'
        "<pre>  indentato\n    di più</pre>"
    )

    assert storage_to_markdown(html) == (
        '```json\n{\n  "id": 1,\n  "tag": "<b>&amp;"\n}\n```\n\n```\na   b\n```\n\n```\n\n```\n\n```\n  indentato\n    di più\n```'
    )


def test_storage_panels_become_quotes_and_other_macros_keep_their_body():
    html = (
        '<ac:structured-macro ac:name="warning"><ac:parameter ac:name="title">Attenzione</ac:parameter>'
        "<ac:rich-text-body><p>non toccare</p></ac:rich-text-body></ac:structured-macro>"
        '<ac:structured-macro ac:name="info"><ac:rich-text-body><p>info</p></ac:rich-text-body></ac:structured-macro>'
        '<ac:structured-macro ac:name="details"><ac:rich-text-body><p>dettagli</p></ac:rich-text-body></ac:structured-macro>'
        '<ac:structured-macro ac:name="toc"><ac:parameter ac:name="maxLevel">2</ac:parameter></ac:structured-macro>'
        "<blockquote><p>citata</p></blockquote><hr/>"
    )

    assert storage_to_markdown(html) == "> **Attenzione**\n>\n> non toccare\n\n> info\n\ndettagli\n\n> citata\n\n---"


def test_storage_headings_lists_and_task_lists():
    html = (
        "<h1>Titolo</h1><h3>  Sotto  </h3>"
        "<ol><li>uno<ul><li>annidato</li></ul></li><li><p>due</p></li></ol>"
        "<ac:task-list><ac:task><ac:task-status>complete</ac:task-status><ac:task-body>fatto</ac:task-body></ac:task>"
        "<ac:task><ac:task-status>incomplete</ac:task-status><ac:task-body>da fare</ac:task-body></ac:task>"
        "<ac:task><ac:task-id>3</ac:task-id></ac:task></ac:task-list>"
    )

    assert storage_to_markdown(html) == (
        "# Titolo\n\n### Sotto\n\n1. uno\n\n   - annidato\n2. due\n\n- [x] fatto\n- [ ] da fare\n- [ ] "
    ).rstrip()


def test_storage_inline_marks_links_and_whitespace():
    html = (
        "<p>  Testo\n  su   righe, <strong>grassetto </strong><b>b</b> <em>corsivo</em> <i>i</i> <s>via</s> "
        "<code>a  b</code> <a href='https://x.io'>sito</a> <a href='https://y.io'></a> <a>senza href</a><strong> </strong></p>"
        '<p><ac:link><ri:page ri:content-title="Altra pagina"/></ac:link> '
        "<ac:link><ri:attachment ri:filename=\"schema.png\"/></ac:link> "
        "<ac:link><ri:page ri:content-title=\"X\"/><ac:plain-text-link-body><![CDATA[etichetta]]></ac:plain-text-link-body></ac:link> "
        "<ac:link></ac:link><ac:emoticon ac:name=\"tick\" ac:emoji-fallback=\"✅\"/>"
        '<ac:image><ri:url ri:value="https://img"/></ac:image><img src="x.png"/></p>'
    )

    assert storage_to_markdown(html) == (
        "Testo su righe, **grassetto** **b** *corsivo* *i* ~~via~~ `a b` [sito](https://x.io) "
        "[https://y.io](https://y.io) senza href\n\nAltra pagina schema.png etichetta ✅"
    )


def test_storage_layouts_divs_and_stray_tags():
    html = (
        "<ac:layout><ac:layout-section><ac:layout-cell><p>colonna</p></ac:layout-cell></ac:layout-section></ac:layout>"
        "<div>blocco</div></span><p>dopo<span>uno</span></p>testo finale"
    )

    assert storage_to_markdown(html) == "colonna\n\nblocco\n\ndopouno\n\ntesto finale"


def test_storage_a_block_inside_a_paragraph_stays_on_its_line():
    assert storage_to_markdown("<p>prima <ul><li>x</li></ul> dopo</p>") == "prima - x dopo"


@pytest.mark.parametrize("html", ["", None])
def test_storage_empty(html):
    assert storage_to_markdown(html) == ""
