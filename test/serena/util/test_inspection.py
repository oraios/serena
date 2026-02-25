import abc

from serena.util.inspection import iter_subclasses


class _Base(abc.ABC):
    pass


class _ConcreteA(_Base):
    pass


class _ConcreteB(_Base):
    pass


class _AbstractChild(_Base, abc.ABC):
    @abc.abstractmethod
    def do_something(self) -> None: ...


class _ConcreteFromAbstract(_AbstractChild):
    def do_something(self) -> None:
        pass


class _DeepConcrete(_ConcreteA):
    pass


class TestIterSubclasses:
    def test_returns_all_concrete_subclasses_recursively(self) -> None:
        result = set(iter_subclasses(_Base))
        assert result == {_ConcreteA, _ConcreteB, _ConcreteFromAbstract, _DeepConcrete}

    def test_non_recursive(self) -> None:
        result = set(iter_subclasses(_Base, recursive=False))
        # _AbstractChild is excluded (abstract), only direct concrete children
        assert result == {_ConcreteA, _ConcreteB}

    def test_include_abstract(self) -> None:
        result = set(iter_subclasses(_Base, include_abstract=True))
        assert _AbstractChild in result
        assert _ConcreteA in result
        assert _ConcreteFromAbstract in result

    def test_include_abstract_non_recursive(self) -> None:
        result = set(iter_subclasses(_Base, recursive=False, include_abstract=True))
        assert result == {_ConcreteA, _ConcreteB, _AbstractChild}

    def test_abstract_excluded_but_its_concrete_children_included(self) -> None:
        """Even when abstract classes are excluded, their concrete subclasses are still found via recursion."""
        result = set(iter_subclasses(_Base, include_abstract=False))
        assert _AbstractChild not in result
        assert _ConcreteFromAbstract in result

    def test_no_subclasses(self) -> None:
        result = list(iter_subclasses(_DeepConcrete))
        assert result == []

    def test_default_is_recursive_and_excludes_abstract(self) -> None:
        """Verify default parameter values: recursive=True, include_abstract=False."""
        result = set(iter_subclasses(_Base))
        assert _AbstractChild not in result
        assert _DeepConcrete in result
