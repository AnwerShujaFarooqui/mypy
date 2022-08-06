"""Track current scope to easily calculate the corresponding fine-grained target.

TODO: Use everywhere where we track targets, including in mypy.errors.
"""

from contextlib import contextmanager, nullcontext
from typing import Iterator, List, Optional, Tuple

from typing_extensions import TypeAlias as _TypeAlias

from mypy.nodes import FuncBase, TypeInfo

SavedScope: _TypeAlias = Tuple[str, Optional[TypeInfo], Optional[FuncBase]]


class Scope:
    """Track which target we are processing at any given time."""

    def __init__(self) -> None:
        self.module: Optional[str] = None
        self.classes: List[TypeInfo] = []
        self.function: Optional[FuncBase] = None
        # Number of nested scopes ignored (that don't get their own separate targets)
        self.ignored = 0

    def current_module_id(self) -> str:
        assert self.module
        return self.module

    def current_target(self) -> str:
        """Return the current target (non-class; for a class return enclosing module)."""
        assert self.module
        if self.function:
            fullname = self.function.fullname
            return fullname or ""
        return self.module

    def current_full_target(self) -> str:
        """Return the current target (may be a class)."""
        assert self.module
        if self.function:
            return self.function.fullname
        if self.classes:
            return self.classes[-1].fullname
        return self.module

    def current_type_name(self) -> Optional[str]:
        """Return the current type's short name if it exists"""
        return self.classes[-1].name if self.classes else None

    def current_function_name(self) -> Optional[str]:
        """Return the current function's short name if it exists"""
        return self.function.name if self.function else None

    @contextmanager
    def module_scope(self, prefix: str) -> Iterator[None]:
        self.module = prefix
        self.classes = []
        self.function = None
        self.ignored = 0
        yield
        assert self.module
        self.module = None

    @contextmanager
    def function_scope(self, fdef: FuncBase) -> Iterator[None]:
        if not self.function:
            self.function = fdef
        else:
            # Nested functions are part of the topmost function target.
            self.ignored += 1
        yield
        if self.ignored:
            # Leave a scope that's included in the enclosing target.
            self.ignored -= 1
        else:
            assert self.function
            self.function = None

    def enter_class(self, info: TypeInfo) -> None:
        """Enter a class target scope."""
        if not self.function:
            self.classes.append(info)
        else:
            # Classes within functions are part of the enclosing function target.
            self.ignored += 1

    def leave_class(self) -> None:
        """Leave a class target scope."""
        if self.ignored:
            # Leave a scope that's included in the enclosing target.
            self.ignored -= 1
        else:
            assert self.classes
            # Leave the innermost class.
            self.classes.pop()

    @contextmanager
    def class_scope(self, info: TypeInfo) -> Iterator[None]:
        self.enter_class(info)
        yield
        self.leave_class()

    def save(self) -> SavedScope:
        """Produce a saved scope that can be entered with saved_scope()"""
        assert self.module
        # We only save the innermost class, which is sufficient since
        # the rest are only needed for when classes are left.
        cls = self.classes[-1] if self.classes else None
        return self.module, cls, self.function

    @contextmanager
    def saved_scope(self, saved: SavedScope) -> Iterator[None]:
        module, info, function = saved
        with self.module_scope(module):
            with self.class_scope(info) if info else nullcontext():
                with self.function_scope(function) if function else nullcontext():
                    yield
