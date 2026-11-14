"""Where each node may sit in an organisation's structure, checked before a change is saved.

The rules:

- one `ORG` at the top, with no parent;
- an `ORG_ENTITY` sits under the `ORG` or under a `DEPARTMENT`, never inside another
  `ORG_ENTITY`: at most one on any line from the top down;
- a `DEPARTMENT` sits under the `ORG`, an `ORG_ENTITY` or another `DEPARTMENT`, to any depth;
- a `JOB` sits under a `DEPARTMENT` only, never under the `ORG` or an `ORG_ENTITY`.

People are not nodes: a person holding a job for a time is an `OrgOccupancy` on the job.

Apps keep the structure in their own tables. They load it into an `OrgStructure` (every node's
id, type and parent; a few hundred rows at most) and ask it before they save a new node or a move.
"""

from dataclasses import dataclass
from typing import Iterable, Optional, Protocol

from wiltech_labs_organization.nodes.nodes import OrgNodeType

ALLOWED_PARENTS: dict[OrgNodeType, frozenset[OrgNodeType]] = {
    OrgNodeType.ORG: frozenset(),
    OrgNodeType.ORG_ENTITY: frozenset({OrgNodeType.ORG, OrgNodeType.DEPARTMENT}),
    OrgNodeType.DEPARTMENT: frozenset({OrgNodeType.ORG, OrgNodeType.ORG_ENTITY, OrgNodeType.DEPARTMENT}),
    OrgNodeType.JOB: frozenset({OrgNodeType.DEPARTMENT}),
}


class OrgStructureError(ValueError):
    """A change that would break the structure rules. `code` tells the cases apart, so an app can
    answer in its own words; the message is plain English."""

    code = "ORG_STRUCTURE"


class UnknownOrgNodeError(OrgStructureError):
    code = "UNKNOWN_ORG_NODE"


class OrgRootError(OrgStructureError):
    """A second `ORG`, an `ORG` with a parent, or a structure without one."""

    code = "ORG_ROOT"


class InvalidParentError(OrgStructureError):
    """A node under a type it may not sit under: a job under the org or an entity, say."""

    code = "INVALID_PARENT"


class NestedEntityError(OrgStructureError):
    """An `ORG_ENTITY` inside another `ORG_ENTITY`, directly or further down."""

    code = "NESTED_ORG_ENTITY"


class OrgCycleError(OrgStructureError):
    """A node moved under itself or under something below it."""

    code = "ORG_CYCLE"


_PLACES: dict[OrgNodeType, str] = {
    OrgNodeType.ORG_ENTITY: "An org entity can only sit under the organisation or a department",
    OrgNodeType.DEPARTMENT: "A department can only sit under the organisation, an org entity or another department",
    OrgNodeType.JOB: "A job can only sit under a department",
}


class OrgNodeLike(Protocol):
    """What `OrgStructure` reads from a node: an `OrgNode`, an `OrgNodeRef` or an app's own row."""

    @property
    def id(self) -> str: ...

    @property
    def type(self) -> str: ...

    @property
    def parent_id(self) -> Optional[str]: ...


@dataclass(frozen=True)
class OrgNodeRef:
    """A node as the rules see it: its id, type and parent."""

    id: str
    type: OrgNodeType
    parent_id: Optional[str] = None


class OrgStructure:
    """An organisation's structure, to check a change before saving it (`check_add`,
    `check_move`) or to check the whole of it (`problems`, `check`)."""

    def __init__(self, nodes: Iterable[OrgNodeLike]):
        self._nodes: dict[str, OrgNodeRef] = {}
        for node in nodes:
            self._nodes[node.id] = OrgNodeRef(node.id, OrgNodeType(node.type), node.parent_id)
        self._children: dict[str, list[str]] = {}
        for ref in self._nodes.values():
            if ref.parent_id is not None:
                self._children.setdefault(ref.parent_id, []).append(ref.id)

    def __contains__(self, node_id: object) -> bool:
        return node_id in self._nodes

    def __len__(self) -> int:
        return len(self._nodes)

    def get(self, node_id: Optional[str]) -> Optional[OrgNodeRef]:
        return self._nodes.get(node_id) if node_id is not None else None

    @property
    def root(self) -> Optional[OrgNodeRef]:
        """The `ORG`, if there is exactly one."""
        roots = [ref for ref in self._nodes.values() if ref.type == OrgNodeType.ORG]
        return roots[0] if len(roots) == 1 else None

    def ancestors(self, node_id: str) -> list[OrgNodeRef]:
        """The node's parent, its parent's parent and so on up to the top, nearest first. Stops at
        an unknown parent or a loop."""
        result: list[OrgNodeRef] = []
        seen = {node_id}
        current = self._nodes.get(node_id)
        while current is not None and current.parent_id is not None and current.parent_id not in seen:
            parent = self._nodes.get(current.parent_id)
            if parent is None:
                break
            result.append(parent)
            seen.add(parent.id)
            current = parent
        return result

    def descendants(self, node_id: str) -> list[OrgNodeRef]:
        """Everything below the node, at any depth."""
        result: list[OrgNodeRef] = []
        seen = {node_id}
        pending = list(self._children.get(node_id, ()))
        while pending:
            child_id = pending.pop()
            if child_id in seen:
                continue
            seen.add(child_id)
            result.append(self._nodes[child_id])
            pending.extend(self._children.get(child_id, ()))
        return result

    def _loops(self, node_id: str) -> bool:
        """Whether walking up from the node comes back round instead of reaching the top."""
        seen = {node_id}
        current = self._nodes.get(node_id)
        while current is not None and current.parent_id is not None:
            if current.parent_id in seen:
                return True
            seen.add(current.parent_id)
            current = self._nodes.get(current.parent_id)
        return False

    def _entity_at_or_above(self, node_id: str) -> bool:
        node = self._nodes[node_id]
        return node.type == OrgNodeType.ORG_ENTITY or any(
            ref.type == OrgNodeType.ORG_ENTITY for ref in self.ancestors(node_id)
        )

    def _entity_at_or_below(self, node_id: str) -> bool:
        node = self._nodes[node_id]
        return node.type == OrgNodeType.ORG_ENTITY or any(
            ref.type == OrgNodeType.ORG_ENTITY for ref in self.descendants(node_id)
        )

    def _parent(self, parent_id: Optional[str]) -> OrgNodeRef:
        parent = self.get(parent_id)
        if parent is None:
            raise UnknownOrgNodeError("The parent isn't part of this organisation")
        return parent

    def check_add(self, node_type: OrgNodeType | str, parent_id: Optional[str]) -> None:
        """Raises an `OrgStructureError` if a new node of `node_type` may not sit under
        `parent_id` (None only for the `ORG`)."""
        node_type = OrgNodeType(node_type)
        if node_type == OrgNodeType.ORG:
            if parent_id is not None:
                raise OrgRootError("The organisation sits at the top, under nothing")
            if any(ref.type == OrgNodeType.ORG for ref in self._nodes.values()):
                raise OrgRootError("There is already an organisation at the top")
            return
        parent = self._parent(parent_id)
        if node_type == OrgNodeType.ORG_ENTITY and self._entity_at_or_above(parent.id):
            raise NestedEntityError("An org entity can't sit inside another org entity")
        if parent.type not in ALLOWED_PARENTS[node_type]:
            raise InvalidParentError(_PLACES[node_type])

    def check_move(self, node_id: str, parent_id: Optional[str]) -> None:
        """Raises an `OrgStructureError` if the node may not move under `parent_id`. Moving keeps
        everything below the node with it, so an entity inside the moved branch counts too."""
        node = self.get(node_id)
        if node is None:
            raise UnknownOrgNodeError("That isn't part of this organisation")
        if node.type == OrgNodeType.ORG:
            if parent_id is not None:
                raise OrgRootError("The organisation sits at the top, under nothing")
            return
        parent = self._parent(parent_id)
        if parent.id == node.id or parent.id in {ref.id for ref in self.descendants(node.id)}:
            raise OrgCycleError("Nothing can sit under itself or under something below it")
        if self._entity_at_or_below(node.id) and self._entity_at_or_above(parent.id):
            raise NestedEntityError("An org entity can't sit inside another org entity")
        if parent.type not in ALLOWED_PARENTS[node.type]:
            raise InvalidParentError(_PLACES[node.type])

    def problems(self) -> list[OrgStructureError]:
        """Every way the structure as a whole breaks the rules, for tests and integrity checks."""
        found: list[OrgStructureError] = []
        roots = [ref for ref in self._nodes.values() if ref.type == OrgNodeType.ORG]
        if len(roots) != 1:
            found.append(OrgRootError(f"Expected one organisation at the top, found {len(roots)}"))
        for ref in self._nodes.values():
            if ref.type == OrgNodeType.ORG:
                if ref.parent_id is not None:
                    found.append(OrgRootError(f"The organisation {ref.id} has a parent"))
                continue
            parent = self.get(ref.parent_id)
            if parent is None:
                found.append(UnknownOrgNodeError(f"{ref.id}'s parent {ref.parent_id} isn't in the structure"))
                continue
            if self._loops(ref.id):
                found.append(OrgCycleError(f"{ref.id} sits in a loop instead of under the organisation"))
                continue
            ancestors = self.ancestors(ref.id)
            if ref.type == OrgNodeType.ORG_ENTITY and any(a.type == OrgNodeType.ORG_ENTITY for a in ancestors):
                found.append(NestedEntityError(f"The org entity {ref.id} sits inside another org entity"))
            if parent.type not in ALLOWED_PARENTS[ref.type]:
                found.append(InvalidParentError(f"{ref.id}: {_PLACES[ref.type]}"))
        return found

    def check(self) -> None:
        """Raises the first of `problems()`, if any."""
        found = self.problems()
        if found:
            raise found[0]
