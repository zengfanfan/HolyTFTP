#!/usr/bin/python3

from setuptools import setup, find_packages
from shutil import copyfile


_name = "HolyTFTP"
_exec = _name
_icon = _name
_version = "0.1.2"
_description = "A TFTP server with GUI"
_url = "https://github.com/zengfanfan/" + _name
_author = "Zeng Fanfan"
_author_email = "zengfanfan2019@gmail.com"
_license = "LGPLv3.0"

with open("README.md", "r") as f:
    _long_description = f.read()

with open("src/shortcut.desktop", "r") as f:
    s = f.read()
    with open("%s.desktop" % _name, "w") as f2:
        f2.write(s.replace("_name", _name).replace("_exec", _exec).replace("_icon", _icon))

copyfile("src/favicon.png", "%s.png" % _name)

setup(
    name=_name,
    version=_version,
    description=_description,
    long_description=_long_description,
    long_description_content_type="text/markdown",
    url=_url,
    author=_author,
    author_email=_author_email,
    license=_license,
    packages=find_packages(),
    data_files=[
        ("/usr/share/applications", ["%s.desktop" % _name]),
        ("/usr/share/pixmaps", ["%s.png" % _icon]),
    ],
    python_requires=">=3.5",
    install_requires=["pyqt5", "gevent"],
    keywords=[_name, "holy", "tftp", "server"],
    entry_points={
        "console_scripts": [
            "%s = src.main:main" % _exec,
        ],
    },
)
