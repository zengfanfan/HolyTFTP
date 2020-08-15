import sys
from datetime import datetime


class Logger(object):

    ForeColor = 30
    BackColor = 40

    Black = 0
    Red = 1
    Green = 2
    Yellow = 3
    Blue = 4
    Purple = 5
    Cyan = 6
    White = 7

    Default = 0
    Highlight = 1
    Underline = 4
    Blink = 5
    Reverse = 7

    FATAL = 1
    ERROR = 2
    WARN = 3
    DEBUG = 4
    INFO = 5

    def __init__(self, level=INFO):
        self.style = Logger.Default
        self.back_color = Logger.ForeColor + Logger.Black
        self.fore_color = Logger.BackColor + Logger.White
        self.level = level

    def set_fore_color(self, color):
        self.fore_color = Logger.ForeColor + color
        print("\033[%dm" % self.fore_color, end="")

    def set_back_color(self, color):
        self.back_color = Logger.BackColor + color
        print("\033[%dm" % self.back_color, end="")

    def set_style(self, style):
        self.style = style
        print("\033[%dm" % self.style, end="")

    def restore_all_styles(self):
        self.set_style(Logger.Default)

    def info(self, *args):
        if self.level < Logger.INFO:
            return
        self.restore_all_styles()
        print(datetime.now().strftime("%m-%d %H:%M:%S"), "[I]", end=" ")
        self.set_fore_color(Logger.White)
        print(*args)
        self.restore_all_styles()
        sys.stdout.flush()

    def debug(self, *args):
        if self.level < Logger.DEBUG:
            return
        self.restore_all_styles()
        print(datetime.now().strftime("%m-%d %H:%M:%S"), "[D]", end=" ")
        self.set_fore_color(Logger.Cyan)
        print(*args)
        self.restore_all_styles()
        sys.stdout.flush()

    def warn(self, *args):
        if self.level < Logger.WARN:
            return
        self.restore_all_styles()
        print(datetime.now().strftime("%m-%d %H:%M:%S"), "[W]", end=" ")
        self.set_fore_color(Logger.Yellow)
        print(*args)
        self.restore_all_styles()
        sys.stdout.flush()

    def error(self, *args):
        if self.level < Logger.ERROR:
            return
        self.restore_all_styles()
        print(datetime.now().strftime("%m-%d %H:%M:%S"), "[E]", end=" ")
        self.set_fore_color(Logger.Red)
        print(*args)
        self.restore_all_styles()
        sys.stdout.flush()

    def fatal(self, *args):
        self.restore_all_styles()
        print(datetime.now().strftime("%m-%d %H:%M:%S"), "[F]", end=" ")
        self.set_fore_color(Logger.Red)
        self.set_style(Logger.Highlight)
        print(*args)
        self.restore_all_styles()
        sys.stdout.flush()

    def trace(self, *args):
        self.restore_all_styles()
        print(datetime.now().strftime("%m-%d %H:%M:%S"), "[T]", end=" ")
        self.set_fore_color(Logger.Purple)
        self.set_style(Logger.Reverse)
        print(">>>>", *args, "<<<<")
        self.restore_all_styles()
        sys.stdout.flush()


log = Logger(level=Logger.DEBUG)
