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


"""This module contains classes and constants related to outputting test results."""
__testify = 1

import datetime
import operator
import sys
import traceback
import logging
from IPython import ultraTB

# from test_case import TestCase

# Beyond the nicely formatted test output provided by the test logger classes, we
# also want to make basic test running /result info available via standard python logger
_log = logging.getLogger('testify')

VERBOSITY_SILENT    = 0  # Don't say anything, just exit with a status code
VERBOSITY_NORMAL    = 1  # Output dots for each test method run
VERBOSITY_VERBOSE   = 2  # Output method names and timing information

class TestLoggerBase(object):
    traceback_formater = staticmethod(traceback.format_exception)

    def __init__(self, verbosity, stream=sys.stdout):
        self.verbosity = verbosity
        self.stream = stream

    # These methods should be implemented by a TestLoggerBase subclass
    def report_test_name(self, test_name): raise NotImplementedError
    def report_test_result(self, result): raise NotImplementedError
    def report_failures(self, failed_results):
        if failed_results:
            self.heading('FAILURES', 'The following tests are expected to pass.')
            for result in failed_results:
                self.failure(result)
        else:
            self.heading('FAILURES', 'None!')
        
    def report_failure(self, result): raise NotImplementedError
    def report_stats(self, test_case_count, all_results, failed_results, unknown_results): raise NotImplementedError

    def _format_test_method_name(self, test_method):
        """Take a test method as input and return a string for output"""
        out = []
        if test_method.im_class.__module__ != "__main__":
            out.append("%s " % test_method.im_class.__module__)
        out.append("%s.%s" % (test_method.im_class.__name__, test_method.__name__))

        return''.join(out)

    # Helper methods for extracting relevant entries from a stack trace
    def _format_exception_info(self, exception_info_tuple):
        exctype, value, tb = exception_info_tuple
        # Skip test runner traceback levels
        while tb and self.__is_relevant_tb_level(tb):
            tb = tb.tb_next
        if exctype is AssertionError:
            # Skip testify.assertions traceback levels
            length = self.__count_relevant_tb_levels(tb)
            return self.traceback_formater(exctype, value, tb, length)

        if not tb:
            return "Exception: %r (%r)" % (exctype, value)

        return self.traceback_formater(exctype, value, tb)

    def __is_relevant_tb_level(self, tb):
        return tb.tb_frame.f_globals.has_key('__testify')

    def __count_relevant_tb_levels(self, tb):
        length = 0
        while tb and not self.__is_relevant_tb_level(tb):
            length += 1
            tb = tb.tb_next
        return length
        
class TextTestLogger(TestLoggerBase):
    traceback_formater = staticmethod(ultraTB.ColorTB().text)

    def write(self, message):
        """Write a message to the output stream, no trailing newline"""
        self.stream.write(message)
        self.stream.flush()

    def writeln(self, message):
        """Write a message and append a newline"""
        self.stream.write("%s\n" % message)
        self.stream.flush()

    BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(30, 38)

    def _colorize(self, message, color = CYAN):
        if not color:
            return message
        else:
            start_color = chr(0033) + '[1;%sm' % color
            end_color = chr(0033) + '[m'
            return start_color + message + end_color

    def report_test_name(self, test_method):
        _log.info("running: %s", self._format_test_method_name(test_method))
        if self.verbosity >= VERBOSITY_VERBOSE:
            self.write("%s ... " % self._format_test_method_name(test_method))

    def report_test_result(self, result):
        if self.verbosity > VERBOSITY_SILENT:

            if result.success:
				_log.info("success: %s", self._format_test_method_name(result.test_method))
				if self.verbosity == VERBOSITY_NORMAL:
					self.write(self._colorize('.', self.GREEN))
				else:
					self.writeln("%s in %s" % (self._colorize('ok', self.GREEN), result.normalized_run_time()))

            elif result.failure:
				_log.error("fail: %s", self._format_test_method_name(result.test_method), exc_info=result.exception_info)
				if self.verbosity == VERBOSITY_NORMAL:
					self.write(self._colorize('F', self.RED))
				else:
					self.writeln("%s in %s" % (self._colorize("FAIL", self.RED), result.normalized_run_time()))

            elif result.error:
				_log.error("error: %s", self._format_test_method_name(result.test_method), exc_info=result.exception_info)
				if self.verbosity == VERBOSITY_NORMAL:
					self.write(self._colorize('E', self.RED))
				else:
					self.writeln("%s in %s" % (self._colorize("ERROR", self.RED), result.normalized_run_time()))

            elif result.incomplete:
                _log.info("incomplete: %s", self._format_test_method_name(result.test_method))
                if self.verbosity == VERBOSITY_NORMAL:
                    self.write(self._colorize('-', self.YELLOW))
                else:
                    self.writeln(self._colorize('INCOMPLETE', self.YELLOW))

            else:
                _log.info("unknown: %s", self._format_test_method_name(result.test_method))
                if self.verbosity == VERBOSITY_NORMAL:
                    self.write('?')
                else:
                    self.writeln('UNKNOWN')

    def heading(self, *messages):
        self.writeln("")
        self.writeln("=" * 72)
        for line in messages:
            self.writeln(line)

    def failure(self, result):
        self.writeln("")
        self.writeln("=" * 72)
        # self.write("%s: " % self._colorize(('FAIL' if result.failure else 'ERROR'), self.RED))
        self.writeln(self._format_test_method_name(result.test_method))
        self.writeln(''.join(self._format_exception_info(result.exception_info)))
        self.writeln('=' * 72)
        self.writeln("")

    def report_stats(self, test_case_count, **results):
        successful = results.get('successful', [])
        failed = results.get('failed', [])
        incomplete = results.get('incomplete', [])
        unknown = results.get('unknown', [])

        test_method_count = sum(len(bucket) for bucket in results.values())
        test_word = "test" if test_method_count == 1 else "tests"
        case_word = "case" if test_case_count == 1 else "cases"
        overall_success = not failed and not unknown and not incomplete

        self.writeln('')
        status_string = self._colorize("PASSED", self.GREEN) if overall_success else self._colorize("FAILED", self.RED)
        self.write("%s.  " % status_string)
        self.write("%d %s / %d %s: " % (test_method_count, test_word, test_case_count, case_word))

        passed_string = self._colorize("%d passed" % len(successful), (self.GREEN if len(successful) else None))
        failed_string = self._colorize("%d failed" % len(failed), (self.RED if len(failed) else None))

        self.write("%s, %s.  " % (passed_string, failed_string))

        total_test_time = reduce(
            operator.add, 
            (result.run_time for result in (successful+failed+incomplete)), 
            datetime.timedelta())
        self.writeln("(Total test time %.2fs)" % (total_test_time.seconds + total_test_time.microseconds / 1000000.0))

class HTMLTestLogger(TextTestLogger):
    traceback_formater = staticmethod(traceback.format_exception)

    def writeln(self, message):
        """Write a message and append a newline"""
        self.stream.write("%s<br />" % message)
        self.stream.flush()

    BLACK   = "#000"
    BLUE    = "#00F"
    GREEN   = "#0F0"
    CYAN    = "#0FF"
    RED     = "#F00"
    MAGENTA = "#F0F"
    YELLOW  = "#FF0"
    WHITE   = "#FFF"

    def _colorize(self, message, color = CYAN):
        if not color:
            return message
        else:
            start_color = "<span style='color:%s'>" % color
            end_color = "</span>"
            return start_color + message + end_color

class ColorlessTextTestLogger(TextTestLogger):
    traceback_formater = staticmethod(traceback.format_exception)

    def _colorize(self, message, color=None):
        return message
