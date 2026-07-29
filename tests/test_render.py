'''render.py 单元测试 — latex_to_unicode / remove_tables / render_markdown / execute'''

import pytest

from tools.render import (
    latex_to_unicode, remove_tables,
    render_markdown, execute,
)


class TestLatexToUnicode:
    '''latex_to_unicode — LaTeX 符号→Unicode 转换'''

    def test_greek_letters(self):
        assert 'π' in latex_to_unicode(r'\pi is 3.14')
        assert 'α' in latex_to_unicode(r'\alpha particle')
        assert 'β' in latex_to_unicode(r'\beta decay')
        assert 'γ' in latex_to_unicode(r'\gamma ray')

    def test_math_symbols(self):
        assert '∑' in latex_to_unicode(r'\sum x_i')
        assert '∫' in latex_to_unicode(r'\int f(x)')
        assert '∞' in latex_to_unicode(r'\infty')
        assert '≈' in latex_to_unicode(r'a \approx b')

    def test_arrows(self):
        assert '→' in latex_to_unicode(r'x \rightarrow y')
        assert '←' in latex_to_unicode(r'x \leftarrow y')

    def test_neq(self):
        assert '≠' in latex_to_unicode(r'a \neq b')

    def test_superscript_braces(self):
        result = latex_to_unicode(r'x^{2} + y^{3}')
        assert '²' in result
        assert '³' in result

    def test_superscript_single_char(self):
        result = latex_to_unicode(r'x^2')
        assert '²' in result

    def test_superscript_multi_char_no_braces(self):
        result = latex_to_unicode(r'x^i')
        assert 'ⁱ' in result

    def test_math_dollar_stripped(self):
        result = latex_to_unicode(r'$\pi$ is $3.14$')
        assert 'π' in result
        assert '$' not in result

    def test_no_latex_returns_unchanged(self):
        result = latex_to_unicode('hello world')
        assert result == 'hello world'

    def test_empty_string(self):
        assert latex_to_unicode('') == ''


class TestRemoveTables:
    '''remove_tables — Markdown 表格移除'''

    def test_simple_table_removed(self):
        text = 'before\n| header1 | header2 |\n|--------|--------|\n| cell1 | cell2 |\nafter'
        result = remove_tables(text)
        assert 'before' in result
        # "after" 在表格行之后且无空行分隔，被视作表格一部分
        assert 'after' not in result

    def test_table_without_trailing_blank(self):
        text = 'text\n| a | b |'
        result = remove_tables(text)
        assert ' a ' not in result
        assert 'text' in result

    def test_no_table_unchanged(self):
        text = 'just\nplain\ntext'
        assert remove_tables(text) == text

    def test_multiple_tables(self):
        text = 'start\n| t1 |\n|---|\n| x |\n\nmiddle\n| t2 |\n|---|\n| y |\nend'
        result = remove_tables(text)
        assert 'start' in result
        assert 'middle' in result
        # "end" 在第二个表格行之后且无空行分隔，被跳过
        assert 'end' not in result

    def test_empty_string(self):
        assert remove_tables('') == ''


class TestRenderMarkdown:
    '''render_markdown — 先移除表格再渲染'''

    def test_table_removed_first(self):
        content = 'text\n| h |\n|---|\n| c |\nmore'
        result = render_markdown(content)
        assert 'h' not in result
        assert 'text' in result

    def test_bold_markers_ansi(self):
        result = render_markdown('**bold** text')
        assert '\x1b[1m' in result  # bold ansi
        assert '\x1b[0m' in result  # reset

    def test_italic_markers_ansi(self):
        result = render_markdown('*italic* text')
        assert '\x1b[3m' in result

    def test_inline_code_ansi(self):
        result = render_markdown('use `code` here')
        assert '\x1b[36m' in result

    def test_latex_conversion_before_markdown(self):
        result = render_markdown(r'$\pi$ *italic*')
        assert 'π' in result
        assert '\x1b[3m' in result

    def test_empty_string(self):
        assert render_markdown('') == ''


class TestRenderExecute:
    '''execute() — 调度入口'''

    def test_text_type(self):
        result = execute({"content": "hello", "type": "text"})
        assert result == "hello"

    def test_markdown_type(self):
        result = execute({"content": "**bold**", "type": "markdown"})
        assert '\x1b[1m' in result
        assert '\x1b[0m' in result

    def test_error_type(self):
        result = execute({"content": "something wrong", "type": "error"})
        assert '\x1b[91m' in result
        assert '❌' in result

    def test_default_type_is_text(self):
        result = execute({"content": "just text"})
        assert result == "just text"

    def test_missing_content(self):
        result = execute({})
        assert result == ""

    def test_register_schema(self):
        registry = {}
        from tools import render
        render.register(lambda n, f, s: registry.update({n: (f, s)}))
        assert "render" in registry
        schema = registry["render"][1]
        assert schema["function"]["name"] == "render"
