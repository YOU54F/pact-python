"""pact-python PyPI Package."""

import os
import platform
import sys
import tarfile

from zipfile import ZipFile
import shutil
import gzip

from setuptools import setup
from setuptools.command.develop import develop
from setuptools.command.install import install
from urllib.request import urlopen


IS_64 = sys.maxsize > 2 ** 32
PACT_STANDALONE_VERSION = '1.88.51'
PACT_FFI_VERSION = '0.0.1'

here = os.path.abspath(os.path.dirname(__file__))

about = {}
with open(os.path.join(here, "pact", "__version__.py")) as f:
    exec(f.read(), about)


class PactPythonDevelopCommand(develop):
    """
    Custom develop mode installer for pact-python.

    When the package is installed using `python setup.py develop` or
    `pip install -e .` it will download and unpack the appropriate Pact
    mock service and provider verifier.
    """

    def run(self):
        """Install ruby command."""
        develop.run(self)
        bin_path = os.path.join(os.path.dirname(__file__), 'pact', 'bin')
        if not os.path.exists(bin_path):
            os.mkdir(bin_path)

        install_ruby_app(bin_path)
        install_rust_app(bin_path)


class PactPythonInstallCommand(install):
    """
    Custom installer for pact-python.

    Installs the Python package and unpacks the platform appropriate version
    of the Ruby mock service and provider verifier.
    """

    def run(self):
        """Install python binary."""
        install.run(self)
        bin_path = os.path.join(self.install_lib, 'pact', 'bin')
        os.mkdir(bin_path)

        install_ruby_app(bin_path)
        install_rust_app(bin_path)


def install_rust_app(bin_path):
    """
    Download the relevant rust binaries and install it for use.

    :param bin_path: The path where binaries should be installed.
    """
    target_platform = platform.platform().lower()

    if 'darwin' in target_platform or 'macos' in target_platform:
        suffix = 'libpact_ffi-osx-x86_64'
    elif 'linux' in target_platform:
        suffix = 'libpact_ffi-linux-x86_64'
    elif 'windows' in target_platform:
        suffix = 'pact_ffi-windows-x86_64'
    else:
        msg = ('Unfortunately, {} is not a supported platform. Only Linux,'
               ' Windows, and OSX are currently supported.').format(
            platform.platform())
        raise Exception(msg)

    if 'windows' in platform.platform().lower():
        fetch_lib(bin_path, suffix, 'dll')
        fetch_lib(bin_path, suffix, 'dll.lib')
        fetch_lib(bin_path, suffix, 'lib')

    else:
        fetch_lib(bin_path, suffix, 'a')
        if 'darwin' in target_platform or 'macos' in target_platform:
            fetch_lib(bin_path, suffix, 'dylib')

        elif 'linux' in target_platform:
            fetch_lib(bin_path, suffix, 'so')


def fetch_lib(bin_path, suffix, type):
    """
    Fetch rust binaries to the bin_path.

    :param bin_path: The path where binaries should be installed.
    :param suffix: The suffix filename unique to this platform (e.g. libpact_ffi-osx-x86_64).
    :param type: The type of library (e.g. so|a|dll|dylib)
    Raises:
        RuntimeError: [description]

    """
    dest = os.path.join(bin_path, f'{suffix}.{type}')
    zipped = os.path.join(bin_path, f'{suffix}.{type}.gz')
    uri = (
        f"https://github.com/pact-foundation/pact-reference/releases"
        f"/download/libpact_ffi-v{PACT_FFI_VERSION}/{suffix}.{type}.gz")

    resp = urlopen(uri)
    with open(zipped, 'wb') as f:
        if resp.code == 200:
            f.write(resp.read())
        else:
            raise RuntimeError(
                'Received HTTP {} when downloading {}'.format(
                    resp.code, resp.url))

    with gzip.open(zipped) as g, open(dest, 'wb') as f_out:
        shutil.copyfileobj(g, f_out)


def install_ruby_app(bin_path):
    """
    Download a Ruby application and install it for use.

    :param bin_path: The path where binaries should be installed.
    """
    target_platform = platform.platform().lower()
    uri = ('https://github.com/pact-foundation/pact-ruby-standalone/releases'
           '/download/v{version}/pact-{version}-{suffix}')

    if 'darwin' in target_platform or 'macos' in target_platform:
        suffix = 'osx.tar.gz'
    elif 'linux' in target_platform and IS_64:
        suffix = 'linux-x86_64.tar.gz'
    elif 'linux' in target_platform:
        suffix = 'linux-x86.tar.gz'
    elif 'windows' in target_platform:
        suffix = 'win32.zip'
    else:
        msg = ('Unfortunately, {} is not a supported platform. Only Linux,'
               ' Windows, and OSX are currently supported.').format(
            platform.platform())
        raise Exception(msg)

    path = os.path.join(bin_path, suffix)
    resp = urlopen(uri.format(version=PACT_STANDALONE_VERSION, suffix=suffix))
    with open(path, 'wb') as f:
        if resp.code == 200:
            f.write(resp.read())
        else:
            raise RuntimeError(
                'Received HTTP {} when downloading {}'.format(
                    resp.code, resp.url))

    if 'windows' in platform.platform().lower():
        with ZipFile(path) as f:
            f.extractall(bin_path)
    else:
        with tarfile.open(path) as f:
            f.extractall(bin_path)


def read(filename):
    """Read file contents."""
    path = os.path.realpath(os.path.join(os.path.dirname(__file__), filename))
    with open(path, 'rb') as f:
        return f.read().decode('utf-8')


dependencies = [
    'click>=2.0.0',
    'psutil>=2.0.0',
    'requests>=2.5.0',
    'six>=1.9.0',
    'cffi==1.14.6'
]

if __name__ == '__main__':
    setup(
        cmdclass={
            'develop': PactPythonDevelopCommand,
            'install': PactPythonInstallCommand},
        name='pact-python',
        version=about['__version__'],
        description=(
            'Tools for creating and verifying consumer driven '
            'contracts using the Pact framework.'),
        long_description=read('README.md'),
        long_description_content_type='text/markdown',
        author='Matthew Balvanz',
        author_email='matthew.balvanz@workiva.com',
        url='https://github.com/pact-foundation/pact-python',
        entry_points='''
            [console_scripts]
            pact-verifier=pact.ffi.cli.verify:main
        ''',
        install_requires=dependencies,
        packages=['pact', 'pact.cli'],
        package_data={'pact': ['bin/*']},
        package_dir={'pact': 'pact'},
        license='MIT License')
