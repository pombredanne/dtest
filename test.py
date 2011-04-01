import re
import sys

from dtest.constants import *
from dtest import exceptions
from dtest import result
from dtest import stream


class DTestBase(object):
    _tests = {}

    def __new__(cls, test):
        # If test is None, return None
        if test is None:
            return None

        # If test is a DTestBase subclass, then return it directly
        if isinstance(test, DTestBase):
            return test

        # Require it to be a callable...
        if (not callable(test) and not isinstance(test, classmethod) and
            not isinstance(test, staticmethod)):
            raise exceptions.DTestException("%r must be a callable" % test)

        # Make sure we haven't already created one
        if test in DTestBase._tests:
            return DTestBase._tests[test]

        # OK, construct a new one
        dt = super(DTestBase, cls).__new__(cls)
        dt._test = test
        dt._class = None
        dt._skip = False
        dt._state = None
        dt._pre = None
        dt._post = None
        dt._deps = set()
        dt._revdeps = set()
        dt._partner = None
        dt._attrs = {}
        dt._result = result.DTestResult(dt)

        # Save it in the cache
        DTestBase._tests[test] = dt

        # And return it
        return dt

    def __getattr__(self, key):
        # Get the attribute out of the _attrs map
        return dt._attrs[key]

    def __setattr__(self, key, value):
        # Is it an internal attribute?
        if key[0] == '_':
            return super(DTestBase, self).__setattr__(key, value)

        # Store that in the _attrs map
        self._attrs[key] = value

    def __delattr__(self, key):
        # Is it an internal attribute?
        if key[0] == '_':
            return super(DTestBase, self).__delattr__(key)

        # Delete from the _attrs map
        del self._attrs[key]

    def __call__(self, *args, **kwargs):
        # Need a helper to unwrap and call class methods and static
        # methods
        def do_call(method, args, kwargs):
            if not callable(method):
                # Have to unwrap it
                method = method.__get__(args[0], args[0].__class__)

                # The first argument is now taken care of
                args = args[1:]

            # Now call it
            return method(*args, **kwargs)

        # Extract the notification
        notify = kwargs.get('_notify')
        if '_notify' in kwargs:
            del kwargs['_notify']

        # Transition to the running state
        self._transition(RUNNING)

        # Perform preliminary call
        if self._pre is not None:
            with self._result.accumulate(PRE):
                do_call(self._pre, args, kwargs)

        # Execute the test
        with self._result.accumulate(TEST):
            do_call(self._test, args, kwargs)

        # Invoke any clean-up that's necessary (regardless of
        # exceptions)
        if self._post is not None:
            with self._result.accumulate(POST):
                do_call(self._post, args, kwargs)

        # Transition to the appropriate ending state
        self._transition(self._result._state(), notify)

        # Return the result
        return self._result

    def __int__(self):
        # In an integer context, we're 0; this is how we can count the
        # number of tests
        return 0

    def __hash__(self):
        # Return the hash of the backing test
        return hash(self._test)

    def __eq__(self, other):
        # Compare test objects
        return self._test is other._test

    def __ne__(self, other):
        # Compare test objects
        return self._test is not other._test

    def __str__(self):
        # Generate a string name for the test
        test = self._test if callable(self._test) else self._test.__func__

        # Include the class name if applicable
        if self._class is None:
            return '.'.join([test.__module__, test.__name__])
        else:
            return '.'.join([test.__module__, self._class.__name__,
                             test.__name__])

    def __repr__(self):
        # Generate a representation of the test
        return ('<%s.%s object at %#x wrapping %r>' %
                (self.__class__.__module__, self.__class__.__name__,
                 id(self), self._test))

    @property
    def result(self):
        # We want the result to be read-only, but to be accessed like
        # an attribute
        return self._result

    @property
    def state(self):
        # We want the state to be read-only, but to be accessed like
        # an attribute
        return self._state

    @property
    def test(self):
        # We want the test to be read-only, but to be accessed like an
        # attribute
        return self._test

    @property
    def class_(self):
        # We want the test's class to be read-only, but to be accessed
        # like an attribute
        return self._class

    @property
    def skip(self):
        # We want the test's skip setting to be read-only, but to be
        # accessed like an attribute
        return self._skip

    @property
    def dependents(self):
        # We want the depedenents to be read-only, but to be accessed
        # like an attribute
        return frozenset(self._revdeps)

    def setUp(self, pre):
        # Save the pre-test fixture.  This method can be used as a
        # decorator.
        self._pre = pre
        return pre

    def tearDown(self, post):
        # Save the post-test fixture.  This method can be used as a
        # decorator.
        self._post = post
        return post

    @classmethod
    def tests(cls):
        # Return the list of all tests
        return cls._tests.values()

    def _depcheck(self, notify):
        # Abstract method; subclasses must define!
        raise Exception("Subclasses must implement _depcheck()")

    def _skipped(self, notify):
        # Mark that this test has been skipped by transitioning the
        # state
        if self._state is None:
            self._transition(SKIPPED, notify)

            # Propagate up to tests dependent on us
            for dt in self._revdeps:
                dt._skipped(notify)

            # Also notify tests we're dependent on
            for dt in self._deps:
                dt._notify_skipped(notify)

    def _notify_skipped(self, notify):
        # Regular tests don't care that some test dependent on them
        # has been skipped
        pass

    def _transition(self, state, notify=None):
        # Issue a notification
        if notify is not None and isinstance(self, DTest) and state != RUNNING:
            notify(self, state)

        # Transition to the new state
        self._state = state


class DTest(DTestBase):
    def __int__(self):
        # This is a single test, so return 1 so we contribute to the
        # count
        return 1

    def _depcheck(self, notify):
        # All dependencies must be OK
        for dep in self._deps:
            if (dep._state == FAIL or dep._state == ERROR or
                dep._state == DEPFAIL):
                # Set our own state to DEPFAIL
                self._transition(DEPFAIL, notify)
                return False
            elif dep._state == SKIPPED:
                # Set our own state to SKIPPED
                self._transition(SKIPPED, notify)
                return False
            elif dep._state != OK:
                # Dependencies haven't finished up, yet
                return False

        # All dependencies satisfied!
        return True


class DTestFixture(DTestBase):
    def _set_partner(self, setUp):
        # Sanity-check setUp
        if setUp is None:
            return

        # First, set a dependency
        depends(setUp)(self)

        # Now, save our pair partner
        self._partner = setUp

    def _depcheck(self, notify):
        # Make sure our partner succeeded
        if self._partner is not None:
            if (self._partner._state == FAIL or
                self._partner._state == ERROR or
                self._partner._state == DEPFAIL):
                # Set our own state to DEPFAIL
                self._transition(DEPFAIL, notify)
                return False
            elif self._partner._state == SKIPPED:
                # Set our own state to SKIPPED
                self._transition(SKIPPED, notify)
                return False

        # Other dependencies must not be un-run or in the RUNNING
        # state
        for dep in self._deps:
            if dep._state is None or dep._state == RUNNING:
                return False

        # Dependencies can have failed, failed due to dependencies,
        # been skipped, or have completed--they just have to be in
        # that state before running the fixture
        return True

    def _skipped(self, notify):
        # Only bother if all our dependencies are also skipped--tear
        # down fixtures need to run any time the corresponding set up
        # fixtures have run
        for dep in self._deps:
            if dep != self._partner and dep._state != SKIPPED:
                return

        # Call the superclass method
        super(DTestFixture, self)._skipped(notify)

    def _notify_skipped(self, notify):
        # If all tests dependent on us have been skipped, we don't
        # need to run
        for dep in self._revdeps:
            if dep._state != SKIPPED:
                return

        # Call the superclass's _skipped() method
        super(DTestFixture, self)._skipped(notify)


def istest(func):
    # Wrap func in a test
    return DTest(func)


def nottest(func):
    # Mark that a function should not be considered a test
    func._dt_nottest = True
    return func


def skip(func):
    # Get the DTest object for the test
    dt = DTest(func)

    # Set up to skip it
    dt._skip = True

    # Return the test
    return dt


def attr(**kwargs):
    # Need a wrapper to perform the actual decoration
    def wrapper(func):
        # Get the DTest object for the test
        dt = DTest(func)

        # Update the attributes
        dt._attrs.update(kwargs)

        # Return the test
        return dt

    # Return the actual decorator
    return wrapper


def depends(*deps):
    # Need a wrapper to perform the actual decoration
    def wrapper(func):
        # Get the DTest object for the test
        dt = DTest(func)

        # Add the dependencies
        dt._deps |= set(deps)

        # Add the reverse dependencies
        for dep in deps:
            dep._revdeps.add(dt)

        # Return the test
        return dt

    # Return the actual decorator
    return wrapper


def _mod_fixtures(modname):
    # Split up the module name
    mods = modname.split('.')

    # Now, walk up the tree
    setUps = []
    tearDowns = []
    for i in range(len(mods)):
        module = sys.modules['.'.join(mods[:i + 1])]

        # Make sure the module's been visited...
        _visit_mod(module)

        # Does the module have the fixture?
        setUp = None
        if hasattr(module, 'setUp'):
            module.setUp = DTestFixture(module.setUp)
            setUps.append(module.setUp)
            setUp = module.setUp
        if hasattr(module, 'tearDown'):
            module.tearDown = DTestFixture(module.tearDown)
            tearDowns.append(module.tearDown)

            # Set the partner
            module.tearDown._set_partner(setUp)

    # Next, set up dependencies; each setUp() is dependent on all the
    # ones before it...
    for i in range(1, len(setUps)):
        depends(*setUps[:i])(setUps[i])

    # While each tearDown() is dependent on all the ones after it...
    for i in range(len(tearDowns) - 1):
        depends(*tearDowns[i + 1:])(tearDowns[i])

    # Return the setUps and tearDowns
    return (setUps, tearDowns)


_testRE = re.compile(r'(?:^|[\b_\.-])[Tt]est')


def _visit_mod(mod):
    # Have we visited the module before?
    if hasattr(mod, '_dt_visited') and mod._dt_visited:
        return

    # Mark that we're visiting the module
    mod._dt_visited = True

    # Check for package- and module-level fixtures
    setUps, tearDowns = _mod_fixtures(mod.__name__)

    # Search the module for tests
    updates = {}
    for k in dir(mod):
        # Skip internal functions
        if k[0] == '_':
            continue

        v = getattr(mod, k)

        # Skip non-callables
        if not callable(v):
            continue

        # If it has the _dt_nottest attribute set to True, skip it
        if hasattr(v, '_dt_nottest') and v._dt_nottest:
            continue

        # If it's one of the test fixtures, skip it
        if k in ('setUp', 'tearDown'):
            continue

        # Does it match the test RE?
        if not isinstance(v, DTestBase) and not _testRE.match(k):
            continue

        # Is it already a test?
        if not isinstance(v, DTestBase):
            # Convert it
            v = DTest(v)

            # Store an update for it
            updates[k] = v

        # Attach fixtures as appropriate...
        depends(*setUps)(v)
        for td in tearDowns:
            depends(v)(td)

    # Update the module
    for k, v in updates.items():
        setattr(mod, k, v)


class DTestCaseMeta(type):
    def __new__(mcs, name, bases, dict_):
        # Look up any test fixtures for the individual tests...
        setUp = dict_.get('setUp', None)
        tearDown = dict_.get('tearDown', None)

        # Check for package- and module-level fixtures
        setUps, tearDowns = _mod_fixtures(dict_['__module__'])

        # Updates to the dict_ to apply later
        updates = {}

        # Check for class-level set up
        setUpClass = None
        if 'setUpClass' in dict_:
            setUpClass = DTestFixture(dict_['setUpClass'])
            updates['setUpClass'] = setUpClass

            # Set up dependencies
            depends(*setUps)(setUpClass)
            setUps.append(setUpClass)

        # Check for class-level tear down
        tearDownClass = None
        if 'tearDownClass' in dict_:
            tearDownClass = DTestFixture(dict_['tearDownClass'])
            updates['tearDownClass'] = tearDownClass

            # Set up dependencies
            for td in tearDowns:
                depends(tearDownClass)(td)
            tearDownClass._set_partner(setUpClass)
            tearDowns.append(tearDownClass)

        # Now, we want to walk through dict_ and replace values that
        # match the test RE with instances of DTest
        tests = []
        for k, v in dict_.items():
            # If it has the _dt_nottest attribute set to True, skip it
            if k[0] == '_' or (hasattr(v, '_dt_nottest') and v._dt_nottest):
                continue

            # If it's one of the test fixtures, skip it
            if k in ('setUp', 'tearDown', 'setUpClass', 'tearDownClass'):
                continue

            # Does it match the test RE?
            if not isinstance(v, DTestBase) and not _testRE.match(k):
                continue

            # Is it already a test?
            if not isinstance(v, DTestBase):
                # Convert it
                v = DTest(v)

                # Store an update for it
                updates[k] = v

            # Remember test for attaching class later
            tests.append(v)

            # Attach fixtures as appropriate...
            if v._pre is None and setUp is not None:
                v.setUp(setUp)
            if v._post is None and tearDown is not None:
                v.tearDown(tearDown)

            # Do package-, module-, and class-level fixtures as well
            depends(*setUps)(v)
            for td in tearDowns:
                depends(v)(td)

        # Update the dict_
        dict_.update(updates)

        # Now that we've done the set-up, create the class
        cls = super(DTestCaseMeta, mcs).__new__(mcs, name, bases, dict_)

        # Attach cls to all the tests
        for t in tests:
            t._class = cls

        # Attach cls to in-class fixtures
        if setUpClass is not None:
            setUpClass._class = cls
        if tearDownClass is not None:
            tearDownClass._class = cls

        # Return the constructed class
        return cls


class DTestCase(object):
    __metaclass__ = DTestCaseMeta


def dot(grname='testdeps'):
    # Helper to generate node and edge options
    def mkopts(opts):
        # If there are no options, return an empty string
        if not opts:
            return ''

        # OK, let's do this...
        return ' [' + ','.join(['%s="%s"' % (k, opts[k])
                                for k in opts]) + ']'

    # Now, create the graph
    nodes = []
    edges = []
    for dt in DTestBase._tests.values():
        # If it's not a callable, must be class or static method;
        # get the real test
        test = dt._test if callable(dt._test) else dt._test.__func__

        # Make the node
        opts = dict(label=r'%s\n%r' % (dt, test))
        if isinstance(dt, DTestFixture):
            opts['color'] = 'red'
        if dt._state == SKIPPED:
            opts['style'] = 'dotted'
        nodes.append('"%s"%s;' % (dt, mkopts(opts)))

        # Make all the edges
        for dep in dt._deps:
            opts = {}
            if (isinstance(dt, DTestFixture) or
                isinstance(dep, DTestFixture)):
                opts.update(dict(color='red', style='dashed'))

            edges.append('"%s" -> "%s"%s;' % (dt, dep, mkopts(opts)))

    # Return a graph
    return (('strict digraph "%s" {\n\t' % grname) +
            '\n\t'.join(nodes) + '\n\n\t' + '\n\t'.join(edges) + '\n}')
