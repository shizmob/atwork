import sys
import time
import math
import collections
import itertools
import functools
from datetime import datetime


class Formatter:
    def message(self, msg, has_result=False):
        ...

    def success(self, msg):
        ...

    def fail(self, msg):
        ...

class PlainFormatter(Formatter):
    def __init__(self, date_format='%Y-%m-%d %H:%I:%S'):
        self.date_format = date_format
        self.indent = '  '

    def print(self, task, msg):
        print('[{}] {}{}'.format(datetime.now().strftime(self.date_format), self.indent * task.nest_level, msg))

    def begin(self, task, msg):
        self.print(task, '>> ' + msg)

    def message(self, task, msg):
        self.print(task, self.indent + msg)

    def success(self, task, msg=None):
        if msg:
            self.print(task, 'SUCCESS: ' + msg)
        else:
            self.print(task, 'SUCCESS')

    def fail(self, task, msg=None):
        if msg:
            self.print(task, 'FAIL: ' + msg)
        else:
            self.print(task, 'FAIL')


CursesMessageStyle = collections.namedtuple('CursesMessageStyle', ['prefix', 'suffix', 'contents'])
CursesStyle = collections.namedtuple('CursesStyle',
    ['message', 'success', 'failure', 'progress', 'bar']
)

DEFAULT_STYLES = [
    CursesStyle(
        message=CursesMessageStyle(prefix='\u001b[37;1m== ', suffix=' \u001b[37;1m==', contents=None),
        success=CursesMessageStyle(prefix=' \u001b[32;1m[✓] ', suffix='', contents=''),
        failure=CursesMessageStyle(prefix=' \u001b[31;1m[x] ', suffix='', contents=''),
        progress=CursesMessageStyle(prefix=' \u001b[37;0m(', suffix=')', contents='/'),
        bar=CursesMessageStyle(prefix='\u001b[37;1m[', suffix=']', contents='■')
    ),
    CursesStyle(
        message=CursesMessageStyle(prefix=' \u001b[37;1m[*] \u001b[0m', suffix='...', contents=None),
        success=CursesMessageStyle(prefix=' \u001b[32;1m[✓] ', suffix='', contents=''),
        failure=CursesMessageStyle(prefix=' \u001b[31;1m[x] ', suffix='', contents=''),
        progress=CursesMessageStyle(prefix=' \u001b[37;0m(', suffix=')', contents='/'),
        bar=CursesMessageStyle(prefix='\u001b[37;1m[', suffix=']', contents='■')
    ),
    CursesStyle(
        message=CursesMessageStyle(prefix=' \u001b[90;1m*\u001b[90;1m ', suffix='...', contents=None),
        success=CursesMessageStyle(prefix=' \u001b[32m[✓] ', suffix='', contents=''),
        failure=CursesMessageStyle(prefix=' \u001b[31m[x] ', suffix='', contents=''),
        progress=CursesMessageStyle(prefix=' \u001b[37;0m(', suffix=')', contents=None),
        bar=CursesMessageStyle(prefix='\u001b[37;0m[', suffix=']', contents='■')
    ),
]

class CursesTaskInfo:
    def __init__(self, task, max_messages=5):
        self.start = time.perf_counter()
        self.last_update = None
        self.last_printed = 0

        self.header = ''
        self.result = ''
        self.messages = collections.deque([''], maxlen=max_messages + 1)

        self.bar_width = 80
        self.rate = 0
        if task.total is not None:
            self.order = math.floor(math.log(task.total, 10)) + 1
        else:
            self.order = 0
        if task.unit:
            self.unit = ' ' + task.unit + '/s'
        else:
            self.unit = '/s'

class CursesFormatter(Formatter):
    def __init__(self):
        self.info = {}
        self.max_messages = 5
        self.last_task = None
        self.keep_steps = True
        self.styles = DEFAULT_STYLES
        self.update_threshold = 0.5

    def style_for(self, nest_level):
        return self.styles[-1] if nest_level >= len(self.styles) else self.styles[nest_level]

    def update_header(self, task, info, msg):
        style = self.style_for(task.nest_level)
        msg = style.message.prefix + msg + style.message.suffix
        info.header = msg

    def update_result(self, task, info, msg, success):
        style = self.style_for(task.nest_level)
        if success:
            info.result = style.success.prefix + msg + style.success.suffix
        else:
            info.result = style.failure.prefix + msg + style.success.suffix

    def update(self, task, info):
        msg = ''

        style = self.style_for(task.nest_level)
        indent = task.nest_level * '  '
        lines = 1
        if task == self.last_task or not info.last_printed:
            if info.last_printed:
                msg += '\u001b[' + str(info.last_printed) + 'A\r' + indent
            msg += info.header
            if task.total is not None:
                msg += style.progress.prefix + str(task.progress).zfill(info.order) + '/' + str(task.total)
                now = time.perf_counter()
                if (task.progress > 0 and not info.last_update) or (info.last_update and now - info.last_update >= self.update_threshold):
                    info.rate = round(task.progress / (now - info.start), 2)
                    info.last_update = now
                msg += ', ' + str(info.rate) + info.unit + style.progress.suffix
        else:
            msg += indent

        msg += info.result + '\u001b[K\n'

        if task == self.last_task:
            step_style = self.style_for(task.nest_level + 1)
            if (self.keep_steps or not task.done) and info.messages:
                for s in itertools.islice(info.messages, 1, None):
                    msg += indent + '  ' + step_style.message.prefix + s + step_style.message.suffix + '\u001b[K\n'
        if not task.done and task.total is not None:
            progress = math.floor(info.bar_width * task.progress / task.total)
            blank = info.bar_width - progress
            msg += indent + style.bar.prefix + style.bar.contents * progress + ' ' * blank + style.bar.suffix + '\u001b[K\n'
            lines += 1
        msg += '\u001b[J'
        info.last_printed = max(0, len(info.messages) - 1) + lines
        self.last_task = task

        print(msg, end='')

    def begin(self, task, msg):
        if task not in self.info:
            self.info[task] = CursesTaskInfo(task, self.max_messages)

        info = self.info[task]
        self.update_header(task, info, msg)
        self.last_task = task
        self.update(task, info)

    def message(self, task, msg):
        info = self.info[task]
        info.messages.append(msg)
        self.update(task, info)

    def success(self, task, msg=None):
        info = self.info[task]
        self.update_result(task, info, msg or 'DONE', True)
        self.update(task, info)

    def fail(self, task, msg=None):
        info = self.info[task]
        self.update_result(task, info, msg or 'FAIL', False)
        self.update(task, info)
        

def default_formatter():
    if True or sys.stdout.isatty():
        return CursesFormatter()
    else:
        return PlainFormatter()


class Task:
    def __init__(self, msg, total=None, unit=None, parent=None, formatter=None):
        self.msg = msg
        self.progress = 0
        self.total = total
        self.parent = parent
        self.unit = unit
        self.done = False
        self.formatter = formatter or getattr(parent, 'formatter', None) or default_formatter()
        self.nest_level = parent.nest_level + 1 if parent else 0
        self.root = parent.root if parent else self

    def begin(self):
        self.formatter.begin(self, self.msg)
    
    def message(self, msg):
        self.formatter.message(self, msg)

    def step(self, msg=None):
        if self.total is not None:
            self.progress += 1
        if msg is not None:
            self.message(msg)

    def success(self, result=None):
        if self.done:
            return
        self.done = True
        self.formatter.success(self, result)

    def fail(self, result=None):
        if self.done:
            return
        self.done = True
        self.formatter.fail(self, result)

    def __enter__(self):
        self.begin()
        return self

    def __exit__(self, type, value, traceback):
        if type:
            self.fail('Exception')
        else:
            self.success()

    def subtask(self, *args, **kwargs):
        return Task(*args, parent=self, **kwargs)
