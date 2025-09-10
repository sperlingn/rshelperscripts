#!/usr/bin/env python3

# Process in the RayStation venv:

# pip install --upgrade "<PATH_TO_rshelperscripts_folder>"

# If you are planning on developing and using git to modify, then ensure the
# raystation system has git installed, and then you can use:

# pip install --upgrade "git://github.comsperlingn/rshelperscripts.git"

import setuptools

from os import path
import re
import subprocess

match_re = r'v(?P<ver>[\d.]+)-(?P<cdiff>\d+)-(?P<commit>[\w]+)'

cwd = path.abspath(path.dirname(__file__))

version = '1.0.1'
git_version = None
if path.exists(path.join(cwd, '.git')):
    git_cmd = 'git describe --long --tags'
    # Expect a version tag in the form: vM.N.S-C-H
    # M - major
    # N - minor
    # S - sub
    # C - commits since last minor
    # H - short hash of last commit

    # Rename this to the expected PEP 440 form of:
    # [N!]N(.N)*[{a|b|rc}N][.postN][.devN][+<local version label>]

    try:
        git_out = subprocess.check_output(git_cmd).decode()

        gv = re.match(match_re, git_out)
        git_version = f'{gv["ver"]}'
        if gv['cdiff'] != "0":
            git_version += f'.dev{gv["cdiff"]}+{gv["commit"]}'

    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Could not find git.\n{e}")
        git_version = None
    except (TypeError, KeyError):
        print("Could not determine version using git.\n"
              f"Git responded with: {git_out!r}")
        git_version = None

version = git_version or version

setuptools.setup(
    name='rshelperscripts',
    version=version,
    packages=['rshelperscripts'],
    package_dir={
        'rshelperscripts': '.',
    },
    install_requires=[
        'pyodbc>=5.0.1',
        'pydicom>=2.3.1,<3.0.0',
    ],
)
