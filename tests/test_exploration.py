from dtest import list_tests


required = [
    'tests.explore.a_test',
    'tests.explore.test_discovered',
    'tests.explore.test_pkg.a_test',
    'tests.explore.test_pkg.test_discovered',
    'tests.explore.pkg_impl.a_test',
    'tests.explore.pkg_impl.test_discovered',
    'tests.explore.pkg_impl.test_impl.a_test',
    'tests.explore.pkg_impl.test_impl.test_discovered',
    ]

prohibited = [
    'tests.explore.test_not',
    'tests.explore.pkg.a_test',
    'tests.explore.pkg.test_not',
    'tests.explore.pkg.test_discovered',
    'tests.explore.pkg.nottest.a_test',
    'tests.explore.pkg.nottest.test_not',
    'tests.explore.pkg.nottest.test_discovered',
    'tests.explore.notpkg.a_test',
    'tests.explore.notpkg.test_not',
    'tests.explore.notpkg.test_discovered',
    'tests.explore.test_pkg.test_not',
    'tests.explore.test_notpkg.a_test',
    'tests.explore.test_notpkg.test_not',
    'tests.explore.test_notpkg.test_discovered',
    'tests.explore.pkg_impl.test_not',
    'tests.explore.pkg_impl.test_impl.test_not',
    ]


def test_discovery():
    # Get the list of test names
    tests = set([str(t) for t in list_tests()])

    # Now go through the required list and make sure all those tests
    # are present
    for t in required:
        assert t in tests, "Required test %r not discovered" % t

    # And similarly for the prohibited list
    for t in prohibited:
        assert t not in tests, "Prohibited test %r discovered" % t