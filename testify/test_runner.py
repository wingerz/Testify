# Copyright 2009 Yelp
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""This module contains the TestRunner class and other helper code"""
__author__ = "Oliver Nicholas <bigo@yelp.com>"
__testify = 1

from collections import defaultdict
import datetime
import logging
from optparse import OptionParser
import os
import pprint
import sys
import traceback
import types

import code_coverage
import cProfile
from test_case import MetaTestCase, TestCase
import test_discovery
from test_logger import _log, TextTestLogger, VERBOSITY_SILENT, VERBOSITY_NORMAL, VERBOSITY_VERBOSE

class TestRunner(object):
    """TestRunner is the controller class of the testify suite.  

    It is responsible for collecting a list of TestCase subclasses, instantiating and 
    running them, delegating the collection of results and printing of statistics.
    """

    def __init__(self,
                 suites_include=[],
                 suites_exclude=[],
                 coverage=False,
                 profile=False,
                 summary_mode=False,
                 test_reporters=None,
                 module_method_overrides={}):
        """After instantiating a TestRunner, call add_test_case() to add some tests, and run() to run them."""
        self.suites_include = set(suites_include)
        self.suites_exclude = set(suites_exclude)

        self.coverage = coverage
        self.profile = profile
        self.test_reporters = test_reporters
        self.summary_mode = summary_mode

        self.module_method_overrides = module_method_overrides
        self.test_case_classes = []

    @classmethod
    def get_test_method_name(cls, test_method):
        return '%s %s.%s' % (test_method.__module__, test_method.im_class.__name__, test_method.__name__)

    def discover(self, test_path, bucket=None, bucket_count=None, bucket_overrides={}):
        for test_case_class in test_discovery.discover(test_path):
            override_bucket = bucket_overrides.get(MetaTestCase._cmp_str(test_case_class))
            if (bucket is None
                or (override_bucket is None and test_case_class.bucket(bucket_count) == bucket)
                or (override_bucket is not None and override_bucket == bucket)):
                if not self.module_method_overrides or test_case_class.__name__ in self.module_method_overrides:
                    self.add_test_case(test_case_class)

    def add_test_case(self, module):
        self.test_case_classes.append(module)

    def run(self):
        """Instantiate our found test case classes and run their test methods.

        We use this opportunity to apply any test method name overrides that were parsed
        from the command line (or rather, passed in on initialization).
        
        Logging of individual results is accomplished by registering callbacks for 
        the TestCase instances to call when they begin and finish running each test.
        
        At its conclusion, we pass our collected results and to our TestLogger to get
        testing exceptions and summaries printed out.
        """

        results = []
        try:
            for test_case_class in self.test_case_classes:
                name_overrides = self.module_method_overrides.setdefault(test_case_class.__name__, None)
                test_case = test_case_class(
                    suites_include=self.suites_include,
                    suites_exclude=self.suites_exclude,
                    name_overrides=name_overrides)

                if not any(test_case.runnable_test_methods()):
                    continue

                for reporter in self.test_reporters:
                    test_case.register_callback(test_case.EVENT_ON_RUN_TEST_METHOD, reporter.test_start)
                    test_case.register_callback(test_case.EVENT_ON_COMPLETE_TEST_METHOD, reporter.test_complete)

                # Now that we are going to run the actually test case, start tracking coverage if requested.
                if self.coverage:
                    code_coverage.start(test_case.__class__.__module__ + "." + test_case.__class__.__name__)
                    
                # callbacks registered, this will actually run the TestCase's fixture and test methods
                if self.profile:
                    cprofile_filename = test_case.__class__.__module__ + "." + test_case.__class__.__name__ + '.cprofile'
                    cProfile.runctx('test_case.run()', globals(), locals(), cprofile_filename)
                else:
                    test_case.run()
                
                # Stop tracking and save the coverage info
                if self.coverage:
                    code_coverage.stop()

        except (KeyboardInterrupt, SystemExit), e:
            # we'll catch and pass a keyboard interrupt so we can cancel in the middle of a run
            # but still get a testing summary.
            pass

        report = [reporter.report() for reporter in self.test_reporters]
        return all(report)

    def list_suites(self):
        """List the suites represented by this TestRunner's tests."""
        suites = defaultdict(list)
        for test_case_class in self.test_case_classes:
            test_instance = test_case_class(
                suites_include=self.suites_include,
                suites_exclude=self.suites_exclude)
            for test_method in test_instance.runnable_test_methods():
                for suite_name in test_method._suites:
                    suites[suite_name].append(test_method)
        suite_counts = dict((suite_name, "%d tests" % len(suite_members)) for suite_name, suite_members in suites.iteritems())

        pp = pprint.PrettyPrinter(indent=2)
        print(pp.pformat(dict(suite_counts)))

    def list_tests(self, selected_suite_name=None):
        """Lists all tests, optionally scoped to a single suite."""
        test_list = []
        for test_case_class in self.test_case_classes:
            test_instance = test_case_class(
                suites_include=self.suites_include,
                suites_exclude=self.suites_exclude)
            for test_method in test_instance.runnable_test_methods():
                if not selected_suite_name or TestCase.in_suite(test_method, selected_suite_name):
                    test_list.append(test_method)

        pp = pprint.PrettyPrinter(indent=2)
        print(pp.pformat([self.get_test_method_name(test) for test in test_list]))
