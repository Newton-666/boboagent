'''make_inline_diff 单元测试'''

from core.diff_utils import make_inline_diff


class TestMakeInlineDiff:

    def test_no_diff_returns_empty(self):
        text = "line1\nline2\n"
        result = make_inline_diff(text, text)
        assert result == ""

    def test_added_lines(self):
        old = "line1\n"
        new = "line1\nline2\nline3\n"
        result = make_inline_diff(old, new)
        assert "<<<INLINE_DIFF>>>" in result
        assert "<<<END_INLINE_DIFF>>>" in result
        assert "+1" in result or "line2" in result or "line3" in result

    def test_removed_lines(self):
        old = "line1\nline2\nline3\n"
        new = "line1\n"
        result = make_inline_diff(old, new)
        assert "<<<INLINE_DIFF>>>" in result
        assert "-line2" in result or "-line3" in result

    def test_add_and_remove(self):
        old = "keep\nremove\n"
        new = "keep\nadd\n"
        result = make_inline_diff(old, new)
        assert "<<<INLINE_DIFF>>>" in result
        assert "+add" in result or "-remove" in result

    def test_new_file_from_empty(self):
        result = make_inline_diff("", "new content\n")
        assert "<<<INLINE_DIFF>>>" in result
        assert "+new" in result or "new content" in result

    def test_path_hint_appears(self):
        result = make_inline_diff("a", "b", path_hint="myfile.py")
        assert "<<<INLINE_DIFF>>>" in result

    def test_append_mode_shows_only_additions(self):
        old = "existing1\nexisting2\n"
        new = "existing1\nexisting2\nadded1\nadded2\n"
        result = make_inline_diff(old, new, append_mode=True)
        assert "+added1" in result or "+added2" in result

    def test_append_mode_no_old(self):
        '''append_mode=True with empty old should be equivalent to new file'''
        result = make_inline_diff("", "fresh\n", append_mode=True)
        assert "<<<INLINE_DIFF>>>" in result

    def test_truncation_for_large_diff(self):
        '''>40 lines should be truncated'''
        old_lines = "\n".join([f"line{i}" for i in range(50)])
        new_lines = "\n".join([f"line{i}mod" for i in range(50)])
        result = make_inline_diff(old_lines, new_lines)
        assert "省略" in result or "(截断)" in result

    def test_identical_again_returns_empty(self):
        assert make_inline_diff("same\n", "same\n") == ""

    def test_multiline_additions(self):
        old = "start\n"
        new = "start\nmid1\nmid2\nmid3\nend\n"
        result = make_inline_diff(old, new)
        assert "<<<INLINE_DIFF>>>" in result
