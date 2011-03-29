from dtest import result
from dtest import stream


# Test states
RUNNING = 'RUNNING'    # test running
FAILED = 'FAILED'      # test failed
DEPFAIL = 'DEPFAIL'    # dependency failed
COMPLETE = 'COMPLETE'  # test completed


class DTestBase(object):
    _tests = {}

    def __new__(cls, test):
        # If func is a DTestBase subclass, then return it directly
        if isinstance(test, DTestBase):
            return test

        # Require it to be a callable...
        if not callable(test):
            raise TestException("%r must be a callable" % test)

        # Make sure we haven't already created one
        if test in DTestBase._tests:
            return DTestBase._tests[test]

        # OK, construct a new one
        dt = super(DTestBase, cls).__new__(cls)
        dt._test = test
        dt._exp_pass = True
        dt._skip = False
        dt._state = None
        dt._pre = None
        dt._post = None
        dt._deps = set()
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
        # Transition to the running state
        self._state = RUNNING

        # Perform preliminary call
        if self._pre is not None:
            with self._result.accumulate(result.PRE):
                self._pre()

        # Execute the test
        with self._result.accumulate(result.TEST):
            self._test(*args, **kwargs)

        # Invoke any clean-up that's necessary (regardless of
        # exceptions)
        if self._post is not None:
            with self._result.accumulate(result.POST):
                self._post()

        # Transition to the appropriate ending state
        self._state = COMPLETE if self._result else FAILED

    def __int__(self):
        # In an integer context, we're 0; this is how we can count the
        # number of tests
        return 0

    def __hash__(self):
        # Return the hash of the backing test
        return hash(self.test)

    def __eq__(self, other):
        # Compare test objects
        return self.test is other.test

    def __ne__(self, other):
        # Compare test objects
        return self.test is not other.test

    def __repr__(self):
        # Generate a representation of the test
        return ('<%s.%s object at %#x wrapping %r>' %
                (self.__class__.__module__, self.__class__.__name__,
                 id(self), self.test))

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

    def setUp(self, pre):
        # Save the pre-test fixture
        self._pre = pre

    def tearDown(self, post):
        # Save the post-test fixture
        self._post = post

    def add_dep(self, dep):
        # First, we need to find the requisite DTest (fixtures can be
        # passed in as DTestFixture instances to override)
        dt = DTest(dep)

        # Now simply add it to the list of dependencies
        self._deps.add(dt)


class DTest(DTestBase):
    def __int__(self):
        # This is a single test, so return 1 so we contribute to the
        # count
        return 1


class DTestFixture(DTestBase):
    pass


def test(func):
    # Wrap func in a test
    return DTest(func)


def skip(func):
    # Get the DTest object for the test
    dt = DTest(func)

    # Set up to skip it
    dt._skip = True

    # Return the test
    return dt


def failing(func):
    # Get the DTest object for the test
    dt = DTest(func)

    # Set up to expect it to fail
    dt._exp_pass = False

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

        # Return the test
        return dt

    # Return the actual decorator
    return wrapper