#!/usr/bin/python3

import time
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from src.Ui_window import Ui_MainWindow
from src.tftp import *
from src.config import cfg

monkey.patch_all()


def bytes2human(n, precision=4):
    b = int(n % 1024)
    n /= 1024
    k = int(n % 1024)
    n /= 1024
    m = int(n % 1024)
    n /= 1024
    g = int(n % 1024)
    n /= 1024
    t = int(n % 1024)
    if t:
        s, u = "%.2f" % (t + g/1024), "TB"
    elif g:
        s, u = "%.2f" % (g + m/1024), "GB"
    elif m:
        s, u = "%.2f" % (m + k/1024), "MB"
    elif k:
        s, u = "%.2f" % (k + b/1024), "KB"
    else:
        s, u = "%d" % b, "B"
    return s[:int(precision)].strip(".") + " " + u


class Session(object):
    def __init__(self, peer, index, is_read, size, file, full_path, transferred=0):
        self.peer = peer
        self.index = index
        self.is_read = is_read
        self.size = size
        self.file = file
        self.full_path = full_path
        self.transferred = transferred


class TabBarWithCtxMenu(QTabBar):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.menu = QMenu()
        self.clicked_index = 0

        self.act_rename = self.menu.addAction("Re&name")
        self.act_rename.triggered.connect(self.on_rename)

        self.act_remove = self.menu.addAction("&Delete")
        self.act_remove.triggered.connect(self.on_remove)

        self.menu.addSeparator()

        self.act_real_folder = self.menu.addAction("&Real folder")
        self.act_real_folder.setCheckable(True)
        self.act_real_folder.triggered.connect(self.on_real_folder)

        self.act_virtual_folder = self.menu.addAction("&Virtual folder")
        self.act_virtual_folder.setCheckable(True)
        self.act_virtual_folder.triggered.connect(self.on_virtual_folder)

    def on_rename(self, checked: bool):
        dlg = QInputDialog(self)
        dlg.setInputMode(QInputDialog.TextInput)
        dlg.setWindowTitle("Rename %s to" % self.tabText(self.clicked_index))
        dlg.setLabelText("New name:")
        dlg.resize(500, 80)
        dlg.setTextValue(self.tabText(self.clicked_index))
        ok = dlg.exec_()
        text = dlg.textValue()
        if ok and text:
            self.setTabText(self.clicked_index, text)
            log.debug("rename tab", self.clicked_index, "to", text)
            cfg.tabs[self.clicked_index]["name"] = text
            cfg.save()

    def on_remove(self, checked: bool):
        ret = g.ask(
            "Delete Tab", "Sure to delete '%s'?" % self.tabText(self.clicked_index))
        if ret:
            count = self.count()
            log.debug("remove tab %d/%d" % (self.clicked_index, count))
            self.removeTab(self.clicked_index)
            if self.clicked_index == count - 2:
                self.setCurrentIndex(self.clicked_index - 1)
            cfg.tabs.pop(self.clicked_index)
            cfg.save()

    def on_real_folder(self, checked: bool):
        self.enable_virtual_folder(not checked)

    def on_virtual_folder(self, checked: bool):
        self.enable_virtual_folder(checked)

    def enable_virtual_folder(self, on):
        log.debug("%sable virtual folder on tab %d" % ("En" if on else "Dis", self.clicked_index))
        g.main.enable_virtual_folder(on, index=self.clicked_index)

    def mousePressEvent(self, event: QMouseEvent):
        super().mousePressEvent(event)

        if event.button() == Qt.RightButton:
            pos = event.pos()
            self.clicked_index = self.tabAt(pos)
            if 0 <= self.clicked_index < self.count() - 1:
                # reject to remove the last tab
                self.act_remove.setVisible((self.count() > 2))
                # set virtualized status
                v = cfg.get_tab_virtualized(self.clicked_index)
                self.act_real_folder.setChecked(not v)
                self.act_virtual_folder.setChecked(v)
                # show menu
                self.menu.move(self.mapToGlobal(pos))
                self.menu.show()
                event.accept()
                return

        event.ignore()


class LineEditWithClick(QLineEdit):
    def mouseDoubleClickEvent(self, event: QMouseEvent):
        path = "file://" + self.text() + "/"
        log.trace("open path:", path)
        QDesktopServices.openUrl(QUrl(path))


class MainWindow(QMainWindow, Ui_MainWindow):
    COLUMN_NUMBER = 6
    F_COL_NUM = 2

    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.modelSessions = QStandardItemModel(0, self.COLUMN_NUMBER)
        self.modelFiles = QStandardItemModel(0, self.F_COL_NUM)
        self.sessions = {}
        self.last_update_ui = 0.0
        self.transferred = 0
        self.label_port = QLabel("Listening on port %s ..." % cfg.port)
        self.label_speed = QLabel("Speed: %s/s" % bytes2human(0))
        self.label_transferred = QLabel("Transferred: %s" % bytes2human(0, precision=5))
        self.btnMenu.setStyleSheet("background-color: #f60")
        self.menu = QMenu()
        self.tray = QSystemTrayIcon()

    def show(self):
        self.init_tabs()
        self.init_table()
        self.init_status_bar()
        self.init_events()
        self.init_geometry()
        self.init_menu()
        self.init_tray()
        super().show()
        self.tableFiles.resizeColumnToContents(0)

    def init_tray(self):
        self.tray.setIcon(QIcon("HolyTFTP"))
        self.tray.setToolTip("Holy TFTP Server")
        self.tray.activated.connect(self.on_activate_tray)

    def on_activate_tray(self, reason: QSystemTrayIcon.ActivationReason):
        log.debug("tray activated:", reason)
        if reason == QSystemTrayIcon.Trigger:
            self.tray.hide()
            super().show()
            super().activateWindow()

    def changeEvent(self, event: QEvent):
        if event.type() == QEvent.WindowStateChange:
            if self.isMinimized() and cfg.min2tray:
                self.tray.show()
                self.hide()

    def init_menu(self):
        a = self.menu.addAction("Minimize to Tray")
        a.setCheckable(True)
        a.setChecked(cfg.min2tray)
        a.triggered.connect(self.on_action_min2tray)

        a = self.menu.addAction("Always on Top")
        a.setCheckable(True)
        a.setChecked(cfg.always_top)
        a.triggered.connect(self.on_action_always_top)
        self.on_action_always_top(cfg.always_top)

    @staticmethod
    def on_action_min2tray(checked: bool):
        cfg.min2tray = checked
        cfg.save()

    def on_action_always_top(self, checked: bool):
        # flags = self.windowFlags()
        # if checked:
        #     self.setWindowFlags(flags | Qt.WindowStaysOnTopHint)
        # else:
        #     self.setWindowFlags(flags & ~Qt.WindowStaysOnTopHint)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, checked)
        super(MainWindow, self).show()
        cfg.always_top = checked
        cfg.save()

    def init_geometry(self):
        g = self.geometry()
        w, h = cfg.size
        x, y = cfg.position
        if x < 0:
            x = g.x()
        if y < 0:
            y = g.y()
        if w <= 0:
            w = g.width()
        if h <= 0:
            h = g.height()
        self.setGeometry(x, y, w, h)

    def init_tabs(self):
        tbar = TabBarWithCtxMenu(self)
        self.tabWidget.setTabBar(tbar)

        self.tabWidget.removeTab(0)
        for i in range(len(cfg.tabs)):
            self.tabWidget.addTab(QWidget(), cfg.get_tab_name(i))
        self.tabWidget.addTab(QWidget(), "+")

        self.tabWidget.currentChanged.connect(self.on_activate_tab)
        self.tabWidget.setCurrentIndex(cfg.active_tab)
        self.on_activate_tab(cfg.active_tab)

    def init_table(self):
        self.tableSessions.setModel(self.modelSessions)
        self.modelSessions.setHorizontalHeaderLabels(
            [" Client ", " Status ", " Request ", " Transferred ", " % ", " File "])
        items = [self.modelSessions.horizontalHeaderItem(i) for i in range(self.COLUMN_NUMBER)]
        items[0].setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        items[2].setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        items[3].setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        items[4].setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        items[5].setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        for i in range(len(cfg.col_widths)):
            self.tableSessions.setColumnWidth(i, cfg.col_widths[i])

        self.tableFiles.setModel(self.modelFiles)
        self.modelFiles.setHorizontalHeaderLabels([" File Name ", " Real Path "])
        items = [self.modelFiles.horizontalHeaderItem(i) for i in range(self.F_COL_NUM)]
        items[0].setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        items[1].setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.tableFiles.setColumnWidth(0, 100)

    def init_status_bar(self):
        self.statusbar.addWidget(self.label_port, 1)
        self.statusbar.addWidget(self.label_speed, 1)
        self.statusbar.addWidget(self.label_transferred, 1)

        self.label_port.setIndent(10)
        self.label_port.setMargin(0)
        self.label_speed.setMargin(0)
        self.label_transferred.setMargin(0)

        self.label_port.setFrameStyle(QStyleOptionFrame.SO_Button)
        self.label_speed.setFrameStyle(QStyleOptionFrame.SO_Button)
        self.label_transferred.setFrameStyle(QStyleOptionFrame.SO_Button)

        self.label_speed.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.label_transferred.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def init_events(self):
        self.btnBrowser.clicked.connect(self.on_click_browser)
        self.btnMenu.clicked.connect(self.on_click_menu)
        self.comboPath.setLineEdit(LineEditWithClick())
        self.comboPath.currentTextChanged.connect(self.on_path_changed)
        self.btnAdd.clicked.connect(self.on_click_add)
        self.btnDelete.clicked.connect(self.on_click_del)
        self.btnClear.clicked.connect(self.on_click_clear)

    def on_click_add(self):
        path, accepts = QFileDialog.getSaveFileName(
            self, "Add virtual file", options=QFileDialog.DontConfirmOverwrite)
        if not path:
            return
        name = os.path.basename(path)
        if not cfg.add_tab_vpath(name, path):
            g.info("'%s' is in the list already." % name)
            return
        items = [QStandardItem(" %s " % name), QStandardItem(" %s " % path)]
        if not os.access(path, os.F_OK):
            items[0].setForeground(QColor(0xff0000))
            items[1].setForeground(QColor(0xff0000))
        items[1].setToolTip(path)
        self.modelFiles.appendRow(items)
        self.tableFiles.resizeColumnToContents(0)
        self.tableFiles.scrollToBottom()
        cfg.save()

    def on_click_del(self):
        indexes = self.tableFiles.selectedIndexes()
        if not indexes:
            g.info("No file is selected.")
            return
        rows = {}
        for index in indexes:
            r = index.row()
            t = self.modelFiles.item(r, 0)
            name = t.text()
            # remove leading and tailing spaces
            if name[0] == ' ':
                name = name[1:]
            if name[-1] == ' ':
                name = name[:-1]
            rows[r] = name
        if len(rows) == 1:
            ret = g.ask("Delete File", "Sure to delete '%s'?" % list(rows.values())[0])
        else:
            ret = g.ask("Delete Files", "Sure to delete the selected %d files?" % len(rows))
        if not ret:
            return
        row_list = list(rows)
        row_list.sort()
        for i in row_list[::-1]:
            self.modelFiles.removeRow(i)
            cfg.del_tab_vpath(rows[i])
        self.tableFiles.resizeColumnToContents(0)
        cfg.save()

    def on_click_clear(self):
        if not cfg.get_tab_vpaths():
            return
        if not g.ask("Warning", "Sure to delete all virtual files?"):
            return
        self.modelFiles.setRowCount(0)
        cfg.get_tab_vpaths().clear()
        cfg.save()

    def on_click_menu(self):
        if self.menu.isHidden():
            self.menu.show()
            w = self.menu.width()  # after shown, menu.width is a good value
            x = self.width() - w
            y = self.btnMenu.y() + self.btnMenu.height()
            self.menu.move(self.mapToGlobal(QPoint(x, y)))
        else:
            self.menu.hide()

    def on_click_browser(self):
        path = QFileDialog.getExistingDirectory(self, "Pick a path", cfg.get_tab_path())
        if path:
            cfg.set_tab_path(path, record=True)
            self.comboPath.clear()
            self.comboPath.addItems(cfg.get_tab_paths()[::-1])
            self.comboPath.setEditText(path)
            cfg.save()

    def on_path_changed(self, path):
        if path:
            self.comboPath.currentTextChanged.disconnect(self.on_path_changed)  # prevent recursion
            cfg.set_tab_path(path)
            self.comboPath.clear()
            self.comboPath.addItems(cfg.get_tab_paths()[::-1])
            cfg.save()
            self.comboPath.currentTextChanged.connect(self.on_path_changed)  # prevent recursion

    def on_activate_tab(self, index):
        if 0 <= index < len(cfg.tabs):
            # change index
            cfg.active_tab = index
            # change content ui
            self.enable_virtual_folder(cfg.get_tab_virtualized())
            # save
            cfg.save()
        elif index == len(cfg.tabs):
            log.debug("add a tab")
            self.tabWidget.addTab(QWidget(), "+")
            cfg.tabs.append({})

            self.tabWidget.setTabText(index, cfg.get_tab_name(index))
            self.on_activate_tab(index)

    def enable_virtual_folder(self, on, index=None):
        if index is None or index == cfg.active_tab:
            self.comboPath.setVisible(not on)
            self.btnBrowser.setVisible(not on)
            self.tableFiles.setVisible(on)
            self.frameVirtualRight.setVisible(on)
            if on:
                # load paths
                self.modelFiles.setRowCount(0)
                vpaths = cfg.get_tab_vpaths()
                for v in vpaths:
                    items = QStandardItem(" %s " % v), QStandardItem(" %s " % vpaths[v])
                    if not os.access(vpaths[v], os.F_OK):
                        items[0].setForeground(QColor(0xff0000))
                        items[1].setForeground(QColor(0xff0000))
                    items[1].setToolTip(vpaths[v])
                    self.modelFiles.appendRow(items)
                self.tableFiles.resizeColumnToContents(0)
            else:
                # load path
                self.comboPath.setEditText(cfg.get_tab_path())
                # load history
                self.comboPath.clear()
                self.comboPath.addItems(cfg.get_tab_paths()[::-1])
        cfg.set_tab_virtualized(on, index=index)
        cfg.save()

    def closeEvent(self, event: QCloseEvent):
        log.warn("terminated for window closed")
        # save window geometry
        g = self.geometry()
        cfg.position = g.x(), g.y()
        cfg.size = g.width(), g.height()
        # save column widths
        for i in range(len(cfg.col_widths)):
            cfg.col_widths[i] = self.tableSessions.columnWidth(i)
        # save to file
        cfg.save()
        sys.exit(0)

    def start_session(self, peer, is_read, file, size, filepath):
        self.sessions[peer] = Session(peer, self.modelSessions.rowCount(), is_read, size, file, filepath)

        items = [QStandardItem() for i in range(MainWindow.COLUMN_NUMBER)]

        items[0].setText(" %-15s:%d " % peer)
        items[1].setText(" Downloading... " if is_read else " Uploading... ")
        items[1].setForeground(QColor(0x009900))
        items[1].font().setBold(True)
        items[1].setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        items[2].setText(" %s %s " % ("<<" if is_read else ">>", file))
        items[2].setToolTip(file)
        items[3].setText(" 0 ")
        items[3].setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        items[4].setText(" 0 " if size > 0 else " N/A ")
        items[4].setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        items[5].setText(" %s " % filepath)
        items[5].setToolTip(filepath)

        for t in items:
            t.setForeground(QColor(0x009900))
            t.setBackground(QColor(0xf8fff8))

        self.modelSessions.appendRow(items)
        self.tableSessions.scrollToBottom()

    def update_session(self, peer, transferred):
        ss = self.sessions.get(peer)
        if not ss:
            return

        self.transferred += transferred - ss.transferred
        ss.transferred = transferred
        interval = time.time() - self.last_update_ui
        if interval < 0.2:
            return  # slowly update ui

        self.last_update_ui = time.time()
        items = [self.modelSessions.item(ss.index, i) for i in range(MainWindow.COLUMN_NUMBER)]
        items[3].setText(" {:,} ".format(transferred))
        items[3].setToolTip("<b>{}</b><br>{:,}".format(bytes2human(transferred), transferred))

        if ss.size > 0:
            items[4].setText(" %d " % (transferred * 100 / ss.size))

    def stop_session(self, peer, ok, title, detail=""):
        ss = self.sessions.get(peer)
        if not ss:
            return

        items = [self.modelSessions.item(ss.index, i) for i in range(MainWindow.COLUMN_NUMBER)]
        items[1].setText(" Completed " if ok else title)
        items[3].setText(" {:,} ".format(ss.transferred))
        items[3].setToolTip("<b>{}</b><br>{:,}".format(bytes2human(ss.transferred), ss.transferred))

        if not ok and detail:
            items[1].setToolTip(detail)

        if ss.size > 0:
            items[4].setText(" %d " % (ss.transferred * 100 / ss.size))

        for t in items:
            f = t.font()
            f.setBold(False)
            t.setFont(f)
            t.setForeground(QColor(0) if ok else QColor(0xff0000))
            t.setBackground(QColor(0xffffff))

        if os.access(ss.full_path, os.F_OK):
            # check if it's in virtual file list
            vpaths = cfg.get_tab_vpaths()
            if ss.full_path in vpaths.values():
                self.enable_virtual_folder(cfg.get_tab_virtualized())  # reset the color

        self.sessions.pop(peer)


def run_main_ui(app):
    # show in the center of screen
    qr = g.main.frameGeometry()
    cp = QDesktopWidget().availableGeometry().center()
    qr.moveCenter(cp)
    g.main.move(qr.topLeft())
    g.main.show()
    while True:
        app.processEvents()
        while app.hasPendingEvents():
            app.processEvents()
        gevent.sleep(0.1)  # if sleep(0), cpu will get high


def run_ui_timer(m, svr):
    last_time = time.time()
    last_port, last_speed, last_transferred = 0, 0, 0
    while True:
        gevent.sleep(1)
        now = time.time()
        interval = now - last_time
        speed = (m.transferred - last_transferred) / interval
        if svr.port != last_port:
            m.label_port.setText("Listening on port %d ..." % svr.port)
            last_port = svr.port
        if speed != last_speed:
            m.label_speed.setText("Speed: %s/s" % bytes2human(speed))
            last_speed = speed
        if m.transferred != last_transferred:
            m.label_transferred.setText("Transferred: %s" % bytes2human(m.transferred, precision=5))
            last_transferred = m.transferred
        last_time = time.time()


def main():
    log.trace("pid:", os.getpid())

    g.app = QApplication(sys.argv)

    g.main = MainWindow()
    g.spawn(run_main_ui, g.app)

    g.server = TftpServer(cfg.port)
    g.server.set_callback(g.main.start_session, g.main.update_session, g.main.stop_session)
    g.spawn_later(0.5, g.server.start)

    g.spawn_later(1, run_ui_timer, g.main, g.server)

    g.goin()
    # sys.exit(G.app.exec_())
    cfg.save()


if __name__ == "__main__":
    main()
