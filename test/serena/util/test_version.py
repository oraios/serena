from serena.util.version import Version


def test_components_ignore_suffixes():
    assert Version("1.2.3").components == [1, 2, 3]
    assert Version("1.6.2.dev0").components == [1, 6, 2]
    assert Version("1.2.3rc1").components == [1, 2, 3]
    # a string with no leading numeric component yields no components at all
    assert Version("test-version").components == []


def test_comparison_treats_missing_components_as_zero():
    """Externally sourced version strings may have fewer components than the one compared against."""
    assert Version("1.6").is_at_least(1, 6, 0)
    assert not Version("1.6").is_at_least(1, 6, 1)
    assert Version("1.6").is_at_most(1, 6, 1)
    assert not Version("1.7").is_at_most(1, 6, 1)


def test_comparison_with_unparseable_version_does_not_raise():
    """A version string with no numeric components must compare as lowest, not raise IndexError."""
    unparseable = Version("test-version")
    assert not unparseable.is_at_least(1, 6, 1)
    assert unparseable.is_at_most(1, 6, 1)
    assert not unparseable.is_equal(1, 6, 1)


def test_is_at_least_ordinary_cases():
    assert Version("1.6.2").is_at_least(1, 6, 2)
    assert Version("1.7.0").is_at_least(1, 6, 2)
    assert not Version("1.6.1").is_at_least(1, 6, 2)
    assert not Version("0.9.9").is_at_least(1, 0, 0)
