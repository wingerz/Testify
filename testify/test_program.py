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


from collections import defaultdict
from optparse import OptionParser
import os
import pwd
import sys
import logging

import testify
from testify import test_logger
from testify import json_reporter
from testify.test_runner import TestRunner
from testify import test_discovery
from testify.utils import class_logger

ACTION_RUN_TESTS = 0
ACTION_LIST_SUITES = 1
ACTION_LIST_TESTS = 2

log = logging.getLogger('testify')

def get_bucket_overrides(filename):
    """Returns a map from test class name to test bucket.

    test class name: {test module}.{classname}
    test bucket: int
    """
    ofile = open(filename)
    overrides = {}
    for line in ofile.readlines():
        if line.startswith('#'):
            continue
        if line.strip() == '':
            continue
        test_module_and_class, bucket = line.strip().split(',')
        overrides[test_module_and_class] = int(bucket)
    ofile.close()
    return overrides

def parse_test_runner_command_line_args(args):
    """Parse command line args for the TestRunner to determine verbosity and other stuff"""
    parser = OptionParser(usage="%prog <test path> [options]", version="%%prog %s" % testify.__version__)

    parser.set_defaults(verbosity=test_logger.VERBOSITY_NORMAL)
    parser.add_option("-s", "--silent", action="store_const", const=test_logger.VERBOSITY_SILENT, dest="verbosity")
    parser.add_option("-v", "--verbose", action="store_const", const=test_logger.VERBOSITY_VERBOSE, dest="verbosity")

    parser.add_option("-c", "--coverage", action="store_true", dest="coverage")
    parser.add_option("-p", "--profile", action="store_true", dest="profile")
    parser.add_option("--json-results", action="store", dest="json_results", type="string", default=None, help="Store test results in json format")
    parser.add_option("--json-results-logging", action="store_true", dest="json_results_logging", default=False, help="Store log output for failed test results in json")

    parser.add_option("-i", "--include-suite", action="append", dest="suites_include", type="string", default=[])
    parser.add_option("-x", "--exclude-suite", action="append", dest="suites_exclude", type="string", default=[])

    parser.add_option("--list-suites", action="store_true", dest="list_suites")
    parser.add_option("--list-tests", action="store_true", dest="list_tests")

    parser.add_option("--label", action="store", dest="label", type="string", help="label for this test run")
    parser.add_option("--extra-json-info", action="store", dest="extra_json_info", type="string", help="json containing some extra info to be stored")
    parser.add_option("--bucket", action="store", dest="bucket", type="int")
    parser.add_option("--bucket-count", action="store", dest="bucket_count", type="int")
    parser.add_option("--bucket-overrides-file", action="store", dest="bucket_overrides_file", default=None)

    parser.add_option("--summary", action="store_true", dest="summary_mode")
    parser.add_option("--no-color", action="store_true", dest="disable_color")
    
    parser.add_option("--log-file", action="store", dest="log_file", type="string", default=None)
    parser.add_option("--log-level", action="store", dest="log_level", type="string", default="INFO")

    (options, args) = parser.parse_args(args)
    if len(args) < 1:
        parser.error("Test path required")

    test_path, module_method_overrides = _parse_test_runner_command_line_module_method_overrides(args)

    if pwd.getpwuid(os.getuid()).pw_name == 'buildbot':
        options.disable_color = True

    if options.list_suites:
        runner_action = ACTION_LIST_SUITES
    elif options.list_tests:
        runner_action = ACTION_LIST_TESTS
    else:
        runner_action = ACTION_RUN_TESTS
    
    reporters = []
    if options.disable_color:
        reporters.append(test_logger.ColorlessTextTestLogger(options))
    else:
        reporters.append(test_logger.TextTestLogger(options))
    
    if options.json_results:
        reporters.append(json_reporter.JSONReporter(options))
    
    test_runner_args = {
        'suites_include': options.suites_include,
        'suites_exclude': options.suites_exclude,
        'coverage': options.coverage,
        'profile': options.profile,
        'module_method_overrides': module_method_overrides,
        'summary_mode': options.summary_mode,
        'test_reporters': reporters
        }

    return runner_action, test_path, test_runner_args, options

def _parse_test_runner_command_line_module_method_overrides(args):
    """Parse a set of positional args (returned from an OptionParser probably) for specific modules or test methods.
    eg/ > python some_module_test.py SomeTestClass.some_test_method
    """

    test_path = args[0]

    module_method_overrides = defaultdict(set)
    for arg in args[1:]:
        module_path_components = arg.split('.')
        module_name = module_path_components[0]
        method_name = module_path_components[1] if len(module_path_components) > 1 else None
        if method_name:
            module_method_overrides[module_name].add(method_name)
        else:
            module_method_overrides[module_name] = None
    
    return test_path, module_method_overrides

class TestProgram(object):
    def __init__(self, command_line_args=None):
        """Initialize and run the test with the given command_line_args
            command_line_args will be passed to parser.parse_args
        """
        command_line_args = command_line_args or sys.argv[1:]

        runner_action, test_path, test_runner_args, other_opts = parse_test_runner_command_line_args(command_line_args)
        
        self.setup_logging(other_opts)
        
        runner = TestRunner(**test_runner_args)

        bucket_overrides = {}
        if other_opts.bucket_overrides_file:
            bucket_overrides = get_bucket_overrides(other_opts.bucket_overrides_file)

        try:
            runner.discover(test_path, bucket=other_opts.bucket, bucket_count=other_opts.bucket_count, bucket_overrides=bucket_overrides)
        except test_discovery.DiscoveryError, e:
            log.error("Failure loading tests: %s", e)
            sys.exit(1)

        if runner_action == ACTION_LIST_SUITES:
            runner.list_suites()
            sys.exit(0)
        elif runner_action == ACTION_LIST_TESTS:
            runner.list_tests()
            sys.exit(0)
        elif runner_action == ACTION_RUN_TESTS:
            label_text = ""
            bucket_text = ""
            if other_opts.label:
                label_text = " " + other_opts.label
            if other_opts.bucket_count:
                bucket_text = " (bucket %d of %d)" % (other_opts.bucket, other_opts.bucket_count)
            log.info("starting test run%s%s", label_text, bucket_text)
            result = runner.run()
            sys.exit(not result)

    def setup_logging(self, options):
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(levelname)-8s %(message)s"))
        console.setLevel(logging.WARNING)
        root_logger.addHandler(console)

        if options.log_file:
            handler = logging.FileHandler(options.log_file, "a")
            handler.setFormatter(logging.Formatter('%(asctime)s\t%(name)-12s: %(levelname)-8s %(message)s'))
        
            log_level = getattr(logging, options.log_level)
            handler.setLevel(log_level)
        
            root_logger.addHandler(handler)

        
if __name__ == "__main__":
    TestProgram()
