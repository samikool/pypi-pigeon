PYTHON_VERSION = "3.10"             # e.g. "3.10", "3.11" — change here to retarget
PLATFORM = "manylinux2014_x86_64"   # pip --platform value for the airgapped target
MIRROR_DIR = "/12-tb/pypimirror-fixed"   # where bandersnatch writes the mirror on the server
MIRROR_WORKERS = 10                 # parallel bandersnatch download workers
KEEP_RELEASES = 3                   # how many releases per package to keep
PYPI_MASTER = "https://pypi.org"
