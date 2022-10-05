import versioneer
from setuptools import setup

if __name__ == "__main__":
    setup(
        name="migas_server",
        version=versioneer.get_version(),
        cmdclass=versioneer.get_cmdclass(),
    )
