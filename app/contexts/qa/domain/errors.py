"""qa 领域错误：用例抛出业务语义异常，路由层映射 HTTP 状态码（对齐 identity 模式）。"""


class QADomainError(Exception):
    """qa 领域错误基类。"""


class QuestionNotFoundError(QADomainError):
    """目标问题不存在（路由层转 404，不泄露内部信息）。"""


class AnswerNotFoundError(QADomainError):
    """目标回答不存在（路由层转 404）。"""


class AlreadyVotedError(QADomainError):
    """同一用户对同一目标已有票：一人一票不变式（v3 裁定 #5：不可改票，路由层转 409）。"""


class NotQuestionAuthorError(QADomainError):
    """非提问者尝试采纳：仅提问者可采纳其问题的回答（US-V03，路由层转 403）。"""


class AnswerAlreadyAcceptedError(QADomainError):
    """问题已有采纳答案：一题仅一个最佳答案，重复采纳一律 409（US-V03 幂等）。

    亦作关闭守卫：已采纳答案的问题不可关闭（不变式 5，Q08 × V03，路由层转 409）。
    """


class QuestionAlreadyClosedError(QADomainError):
    """重复关闭：问题已是关闭态（US-Q08，路由层转 409）。"""


class QuestionClosedError(QADomainError):
    """对已关闭问题的受禁操作：编辑/新增回答/投票/评论/采纳（US-Q08/V02，路由层转 409）。

    关闭为终态（2026-09-29 裁定全冻结）；消息按调用点语义具体化。
    """
