import os
from os.path import expanduser
import json
from .log import log


class Config(object):

    def __init__(self, filename=None):
        self._json = {}
        self._work_path = os.path.abspath(".")
        self._filename = filename or expanduser("~/.config/holytftp.json")
        self._max_path = 9

        self.load()

    def load(self):
        try:
            log.info("loading config from", self._filename)
            with open(self._filename, "r", encoding="utf-8") as f:
                self._json = json.load(f)
        except (FileNotFoundError, ValueError):
            pass

    def save(self, filename=None, _try_count=0):
        if filename is None:
            filename = self._filename
        try:
            log.info("saving config to", filename)
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(self._json, f, indent=4)
        except OSError as e:
            if _try_count < 5:
                os.makedirs(os.path.dirname(filename))
                self.save(filename, _try_count=_try_count + 1)
            else:
                raise e

    @property
    def active_tab(self):
        return self._json.get("active_tab", 0)

    @active_tab.setter
    def active_tab(self, value):
        self._json["active_tab"] = value

    @property
    def port(self):
        value = self._json.get("port")
        if type(value) is not int or not (0 < value < 0x10000):
            self._json["port"] = value = 69
        return value

    @port.setter
    def port(self, value):
        if type(value) is not int or not (0 < value < 0x10000):
            value = 69
        self._json["port"] = value

    @property
    def tabs(self):
        ret = self._json.get("tabs")
        if type(ret) is list and len(ret) > 0 and type(ret[0]) is dict:
            return ret
        else:
            self._json["tabs"] = [{}, {}, {}]
            return self._json["tabs"]

    def get_tab(self, index=None):
        if index is None:
            index = self.active_tab
        if index < len(self.tabs):
            return self.tabs[index]
        else:
            return {}

    def get_tab_val(self, index, name, def_val=None):
        t = self.get_tab(index)
        v = t.get(name, def_val)
        if v is def_val:
            t[name] = v
        return v

    def get_tab_name(self, index=None):
        if index is None:
            index = self.active_tab
        name = self.get_tab_val(index, "name")
        if name is None:
            max_tab_no = index
            for t in self.tabs:
                n = t.get("name", None)
                if type(n) is str and n.startswith("Tab ")\
                        and n[4:].isdigit() and int(n[4:]) > max_tab_no:
                    max_tab_no = int(n[4:])
            name = "Tab %d" % (max_tab_no + 1)
            self.tabs[index]["name"] = name
        return name

    def get_tab_path(self, index=None):
        if index is None:
            index = self.active_tab
        paths = self.get_tab_paths(index)
        if type(paths) is list and len(paths) > 0 and type(paths[0]) is str:
            return paths[-1]
        else:
            self.get_tab(index)["paths"] = [self._work_path]
            return self._work_path

    def set_tab_path(self, path, index=None, record=False):
        if index is None:
            index = self.active_tab
        t = self.get_tab(index)
        paths = self.get_tab_paths(index)
        if path in paths:
            paths.remove(path)
            paths.append(path)
        elif record:
            paths.append(path)
        else:
            paths[-1] = path
        t["paths"] = paths[-self._max_path:]

    def get_tab_paths(self, index=None):
        if index is None:
            index = self.active_tab
        return self.get_tab_val(index, "paths", [self._work_path])

    def get_tab_virtualized(self, index=None):
        if index is None:
            index = self.active_tab
        return self.get_tab_val(index, "virtualized", False)

    def set_tab_virtualized(self, on, index=None):
        if index is None:
            index = self.active_tab
        t = self.get_tab(index)
        t["virtualized"] = on

    def get_tab_vpaths(self, index=None):
        if index is None:
            index = self.active_tab
        return self.get_tab_val(index, "vpaths", {})

    def add_tab_vpath(self, name, path, index=None):
        if index is None:
            index = self.active_tab
        vpaths = self.get_tab_vpaths(index)
        if name in vpaths:
            return False
        else:
            vpaths[name] = path
            return True

    def del_tab_vpath(self, name, index=None):
        if index is None:
            index = self.active_tab
        vpaths = self.get_tab_vpaths(index)
        if name not in vpaths:
            log.trace("not found", name)
            log.trace(vpaths)
            return False
        else:
            vpaths.pop(name)
            log.trace("pop", name)
            return True

    @property
    def col_widths(self):
        ret = self._json.get("col_widths")
        if type(ret) is list and len(ret) > 0 and type(ret[0]) is int:
            return ret
        else:
            self._json["col_widths"] = [150, 130, 180, 100, 40, 400]
            return self._json["col_widths"]

    @property
    def size(self):
        return self._json.get("width", 700), self._json.get("height", 500)

    @size.setter
    def size(self, size):
        self._json["width"] = int(size[0])
        self._json["height"] = int(size[1])

    @property
    def position(self):
        return self._json.get("x", -1), self._json.get("y", -1)

    @position.setter
    def position(self, size):
        self._json["x"] = int(size[0])
        self._json["y"] = int(size[1])

    @property
    def min2tray(self):
        return self._json.get("min2tray", False)

    @min2tray.setter
    def min2tray(self, on: bool):
        self._json["min2tray"] = on

    @property
    def always_top(self):
        return self._json.get("always_top", False)

    @always_top.setter
    def always_top(self, on: bool):
        self._json["always_top"] = on

    def get_real_path(self, filename):
        if self.get_tab_virtualized():
            vpaths = self.get_tab_vpaths()
            return vpaths.get(filename)
        else:
            path = self.get_tab_path()
            return os.path.join(path, filename)


cfg = Config()
