import traceback
import gevent
from PyQt5.QtWidgets import QMessageBox
from .log import log
from .config import cfg


class Globals(object):
    app = None
    server = None
    main = None
    glist = []

    def spawn(self, func, *args, **kwargs):
        ge = gevent.spawn(self.gevent_wrapper, func, args, **kwargs)
        self.glist.append(ge)
        return ge

    def spawn_later(self, seconds, func, *args, **kwargs):
        ge = gevent.spawn_later(seconds, self.gevent_wrapper, func, args, **kwargs)
        self.glist.append(ge)
        return ge

    def goin(self):
        self.glist[0].join()
        gevent.joinall(self.glist[1:])

    @classmethod
    def gevent_wrapper(cls, func, args):
        try:
            func(*args)
        except SystemExit as e:
            log.warn("Exit", e.code)
            cfg.save()
            exit(e.code)
        except Exception as e:
            log.error(e)
            traceback.print_exc()
            cfg.save()
            exit(1)

    def warn(self, string):
        QMessageBox.warning(self.main, "Warning", string, QMessageBox.Ok, QMessageBox.Ok)

    def error(self, string):
        QMessageBox.critical(self.main, "Error", string, QMessageBox.Close, QMessageBox.Close)

    def info(self, string):
        QMessageBox.information(self.main, "Information", string, QMessageBox.Ok, QMessageBox.Ok)

    def ask(self, title, string):
        ret = QMessageBox.question(self.main,
                                   title,
                                   string)
        return ret == QMessageBox.Yes


g = Globals()

