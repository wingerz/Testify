import simplejson

from testify import test_reporter
from testify.utils import exception

class JSONReporter(test_reporter.TestReporter):
    def __init__(self, *args, **kwargs):
        super(JSONReporter, self).__init__(*args, **kwargs)
        
        # Time to open a log file
        self.log_file = open(self.options.json_results, "a")
    
    def test_complete(self, test_case, result):
        """Called when a test case is complete"""
        out_result = {}

        if self.options.label:
            out_result['label'] = self.options.label
        if self.options.bucket is not None:
            out_result['bucket'] = self.options.bucket
        if self.options.bucket_count is not None:
            out_result['bucket_count'] = self.options.bucket_count

        out_result['name'] = "%s.%s" % (result.test_method.im_class.__name__, result.test_method.__name__)
        out_result['start_time'] = str(result.start_time)
        out_result['end_time'] = str(result.end_time)
        out_result['run_time'] = str(result.run_time)

        # Classify the test
        if test_case.is_fixture_method(result.test_method):
            out_result['type'] = 'fixture'
        elif test_case.method_excluded(result.test_method):
            out_result['type'] = 'excluded'
        else:
            out_result['type'] = 'test'
        
        out_result['success'] = bool(result.success)
        if not result.success:
            out_result['tb'] = exception.format_exception_info(result.exception_info)
            out_result['error'] = str(out_result['tb'][-1]).strip()

        self.log_file.write(simplejson.dumps(out_result, indent=1))
        self.log_file.write("\n")
    
    def test_report(self):
        self.log_file.close()

