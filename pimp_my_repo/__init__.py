from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pimp_my_repo")
except PackageNotFoundError:
    # Package is not installed (e.g., running locally during development)
    __version__ = "unknown"
