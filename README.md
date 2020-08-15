# HolyTFTP

HolyTFTP is a TFTP server with GUI, written in python3.
It's a part of the HolySoftware project, which aims to provide os-independent softwares.



## Installation

```
pip install HolyTFTP
```

### Build on linux (to a single file)
```
pyinstaller -Fsn HolyTFTP src/main.py
```

### Build on windows/MacOS (to a single file)
```
pyinstaller -Fwn HolyTFTP -i src/favicon.ico src/main.py
```
