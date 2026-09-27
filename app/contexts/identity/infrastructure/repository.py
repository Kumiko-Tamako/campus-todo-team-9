from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.identity.domain.errors import IdentityAlreadyExistsError
from app.contexts.identity.domain.user import Role, User
from app.contexts.identity.domain.value_objects import Email, PasswordHash, StaffId, StudentId
from app.contexts.identity.infrastructure.models import (
    RoleModel,
    StudentModel,
    TeacherModel,
    UserModel,
    UserRoleModel,
)


class SqlAlchemyUserRepository:
    """UserRepository 端口的 SQLAlchemy 实现。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(UserModel).where(UserModel.email == email)
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else await self._to_domain(model)

    async def get_by_student_id(self, student_id: str) -> User | None:
        stmt = (
            select(UserModel)
            .join(StudentModel, StudentModel.user_id == UserModel.id)
            .where(StudentModel.student_id == student_id)
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else await self._to_domain(model)

    async def get_by_staff_id(self, staff_id: str) -> User | None:
        stmt = (
            select(UserModel)
            .join(TeacherModel, TeacherModel.user_id == UserModel.id)
            .where(TeacherModel.staff_id == staff_id)
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else await self._to_domain(model)

    async def get_by_id(self, user_id: UUID) -> User | None:
        stmt = select(UserModel).where(UserModel.id == user_id)
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else await self._to_domain(model)

    async def add(self, user: User) -> None:
        self._session.add(
            UserModel(
                id=user.id,
                email=user.email.value,
                password_hash=user.password_hash.value,
                created_at=user.created_at,
                updated_at=user.created_at,
            )
        )

        try:
            # 注意：本块内任何查询都可能触发 autoflush 提前执行 INSERT（唯一冲突随之处抛出），
            # 故查询与 flush 必须全部纳入 try，否则竞态 IntegrityError 会绕过 409 兜底
            # （第五路 K-01：并发同 email 注册曾漏成 400）。
            role_stmt = select(RoleModel).where(RoleModel.name == user.role)
            role = (await self._session.execute(role_stmt)).scalar_one()
            self._session.add(UserRoleModel(user_id=user.id, role_id=role.id))

            if user.student_id is not None:
                self._session.add(
                    StudentModel(user_id=user.id, student_id=user.student_id.value)
                )
            if user.staff_id is not None:
                self._session.add(
                    TeacherModel(user_id=user.id, staff_id=user.staff_id.value)
                )

            await self._session.flush()
        except IntegrityError as exc:
            # 不回显 exc.orig（含约束名/DB 细节）；详情随异常链入服务端日志
            raise IdentityAlreadyExistsError("注册信息唯一性冲突（并发兜底）") from exc

    async def _to_domain(self, model: UserModel) -> User:
        student = (
            await self._session.execute(
                select(StudentModel).where(StudentModel.user_id == model.id)
            )
        ).scalar_one_or_none()
        teacher = (
            await self._session.execute(
                select(TeacherModel).where(TeacherModel.user_id == model.id)
            )
        ).scalar_one_or_none()
        role_row = (
            await self._session.execute(
                select(RoleModel)
                .join(UserRoleModel, UserRoleModel.role_id == RoleModel.id)
                .where(UserRoleModel.user_id == model.id)
            )
        ).scalar_one_or_none()

        return User(
            id=model.id,
            role=cast(Role, role_row.name if role_row is not None else "student"),
            email=Email(model.email),
            password_hash=PasswordHash(model.password_hash),
            student_id=StudentId(student.student_id) if student is not None else None,
            staff_id=StaffId(teacher.staff_id) if teacher is not None else None,
            created_at=model.created_at,
        )
