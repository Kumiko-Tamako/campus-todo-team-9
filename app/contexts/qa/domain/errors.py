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
    """问题已有采纳答案：一题仅一个最佳答案，重复采纳一律 409（US-V03 幂等）。"""
