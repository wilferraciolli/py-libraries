from dataclasses import dataclass
from typing import Optional, Protocol

from fastapi import Depends, HTTPException, Request, status

from wiltech_labs_auth.clerk import AuthenticatedUser, get_authenticated_user
from wiltech_labs_auth.roles import UserRole, parse_role_ids
from wiltech_labs_core import Database, get_database


@dataclass(frozen=True)
class SavedUser:
    """What the app's database knows about a Clerk user: their `users.id` and saved roles."""

    id: str
    role_ids: list[str]


class CallerLookup(Protocol):
    async def find(self, external_id: str) -> Optional[SavedUser]: ...


class UserDetailViewLookup:
    """
    The default lookup: reads `user_detail_view` (id, external_user_id,
    role_ids as 'ADMIN,STANDARD') rather than a users repository, so this
    package never imports an app's users domain. Apps whose schema differs
    override `get_caller_lookup` instead.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    async def find(self, external_id: str) -> Optional[SavedUser]:
        row = await self.db.fetch_one(
            "SELECT id, role_ids FROM user_detail_view WHERE external_user_id = ?",
            (external_id,),
        )
        if not row:
            return None
        return SavedUser(id=row["id"], role_ids=parse_role_ids(row["role_ids"]))


def get_caller_lookup(request: Request) -> CallerLookup:
    """
    Where `get_caller` finds the saved user. Swap it per app:

        app.dependency_overrides[get_caller_lookup] = lambda request: MyLookup(...)
    """
    return UserDetailViewLookup(get_database(request))


@dataclass(frozen=True)
class Caller:
    """
    The signed-in caller as our database sees them.

    `user_id` is their `users.id`, or None if they have never called `/me`
    and so have no saved user yet. `role_ids` are their saved roles — the
    source of truth for permissions, not the Clerk token.
    """
    external_id: str
    user_id: Optional[str]
    role_ids: list[str]

    @property
    def is_admin(self) -> bool:
        return UserRole.ADMIN.value in self.role_ids


async def get_caller(
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
    lookup: CallerLookup = Depends(get_caller_lookup),
) -> Caller:
    """Route dependency: who is calling, with their saved roles."""
    saved = await lookup.find(current_user.id)

    if saved is None:
        return Caller(external_id=current_user.id, user_id=None, role_ids=[])

    return Caller(external_id=current_user.id, user_id=saved.id, role_ids=saved.role_ids)


async def require_admin(caller: Caller = Depends(get_caller)) -> Caller:
    """
    Route dependency: only callers whose saved roles include ADMIN get through.

    An admin granted through the API stays an admin even if Clerk stops
    sending the role. 401 if not signed in (raised by get_authenticated_user);
    403 if signed in but not an admin, including a caller with no saved user.
    """
    if not caller.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")

    return caller


async def require_owner(user_id: str, caller: Caller = Depends(get_caller)) -> str:
    """
    Route dependency for personal resources under `/users/{user_id}/...`:
    only that user may use them — not even an admin. Returns the path's
    `user_id`; 403 for anyone else, whether or not that user exists, so the
    API doesn't reveal which ids exist.
    """
    if caller.user_id is None or caller.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to access this user's resources",
        )

    return user_id
