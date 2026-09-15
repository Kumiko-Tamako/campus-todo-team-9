"""Question 聚合与 Title/Body 值对象单元测试（纯 Python，进 CI）。"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.contexts.qa.domain.question import Question, QuestionPublished
from app.contexts.qa.domain.value_objects import Body, Title


class TestTitle:
    def test_valid_title_is_stripped_and_stored(self) -> None:
        title = Title("  如何理解数据库第三范式？  ")
        assert title.value == "如何理解数据库第三范式？"

    @pytest.mark.parametrize("raw", ["", "   ", "\t", "\n  \t"])
    def test_blank_title_rejected(self, raw: str) -> None:
        with pytest.raises(ValueError):
            Title(raw)

    def test_single_char_title_allowed(self) -> None:
        assert Title("问").value == "问"

    def test_100_chars_allowed(self) -> None:
        assert Title("a" * 100).value == "a" * 100

    def test_101_chars_rejected(self) -> None:
        with pytest.raises(ValueError):
            Title("a" * 101)

    def test_unicode_counts_as_code_points(self) -> None:
        # 中文按码点计数：100 个汉字合法，101 个拒绝
        assert Title("数" * 100).value == "数" * 100
        with pytest.raises(ValueError):
            Title("数" * 101)

    def test_nul_rejected(self) -> None:
        with pytest.raises(ValueError, match="控制字符"):
            Title("a\x00b")

    def test_lone_surrogate_rejected(self) -> None:
        with pytest.raises(ValueError, match="代理字符"):
            Title("x\ud800y")

    def test_multiline_whitespace_allowed(self) -> None:
        # \t \n \r 是多行文本合法空白，不拦截
        assert Title("a\tb\nc").value == "a\tb\nc"


class TestBody:
    def test_valid_body_is_stripped_and_stored(self) -> None:
        assert Body("  正文内容……  ").value == "正文内容……"

    @pytest.mark.parametrize("raw", ["", " ", "\n\t "])
    def test_blank_body_rejected(self, raw: str) -> None:
        with pytest.raises(ValueError):
            Body(raw)

    def test_5000_chars_allowed(self) -> None:
        assert Body("x" * 5000).value == "x" * 5000

    def test_5001_chars_rejected(self) -> None:
        with pytest.raises(ValueError):
            Body("x" * 5001)

    def test_nul_rejected(self) -> None:
        with pytest.raises(ValueError, match="控制字符"):
            Body("x\x00y")

    def test_lone_surrogate_rejected(self) -> None:
        with pytest.raises(ValueError, match="代理字符"):
            Body("正文\ud800")


class TestQuestionAsk:
    def test_ask_creates_aggregate_and_publishes_event(self) -> None:
        author_id = uuid4()
        question = Question.ask(
            title_value="  什么是第三范式？  ",
            body_value=" 教材里讲得不太懂。 ",
            author_id=author_id,
        )

        assert isinstance(question.id, UUID)
        assert question.title.value == "什么是第三范式？"
        assert question.body.value == "教材里讲得不太懂。"
        assert question.author_id == author_id
        assert question.created_at.tzinfo is not None  # 带时区的 UTC 时间

        assert len(question.events) == 1
        event = question.events[0]
        assert isinstance(event, QuestionPublished)
        assert event.question_id == question.id
        assert event.author_id == author_id

    def test_ask_generates_distinct_ids(self) -> None:
        author_id = uuid4()
        q1 = Question.ask(title_value="问题一", body_value="正文", author_id=author_id)
        q2 = Question.ask(title_value="问题二", body_value="正文", author_id=author_id)
        assert q1.id != q2.id

    def test_ask_with_blank_title_raises(self) -> None:
        with pytest.raises(ValueError):
            Question.ask(title_value="   ", body_value="正文", author_id=uuid4())
