"""
This paver file is intented to help with the release process as much as
possible. It relies on virtualenv to generate 'bootstrap' environments as
independent from the user system as possible (e.g. to make sure the sphinx doc
is built against the built scipy, not an installed one).

Building a simple (no-superpack) windows installer from wine
============================================================

It assumes that blas/lapack are in c:\local\lib inside drive_c. Build python
2.5 and python 2.6 installers.

    paver bdist_wininst_simple

You will have to configure your wine python locations (WINE_PYS).

The superpack requires all the atlas libraries for every arch to be installed
(see SITECFG), and can then be built as follows::

    paver bdist_superpack

Building changelog + notes
==========================

Assumes you have git and the binaries/tarballs in installers/::

    paver write_release
    paver write_note

This automatically put the checksum into NOTES.txt, and write the Changelog
which can be uploaded to sourceforge.

TODO
====
    - the script is messy, lots of global variables
    - make it more easily customizable (through command line args)
    - missing targets: install & test, sdist test, debian packaging
    - fix bdist_mpkg: we build the same source twice -> how to make sure we use
      the same underlying python for egg install in venv and for bdist_mpkg
"""
import os
import sys
import subprocess
import re
import shutil
try:
    from hash import md5
except ImportError:
    import md5

import distutils

try:
    from paver.tasks import VERSION as _PVER
    if not _PVER >= '1.0':
        raise RuntimeError("paver version >= 1.0 required (was %s)" % _PVER)
except ImportError, e:
    raise RuntimeError("paver version >= 1.0 required")

import paver
import paver.doctools
import paver.path
from paver.easy import options, Bunch, task, needs, dry, sh, call_task

sys.path.insert(0, os.path.dirname(__file__))
try:
    setup_py = __import__("setup")
    FULLVERSION = setup_py.FULLVERSION
finally:
    sys.path.pop(0)

# Wine config for win32 builds
WINE_SITE_CFG = ""
if sys.platform == "darwin":
    WINE_PY25 = ["/Applications/Darwine/Wine.bundle/Contents/bin/wine",
                 "/Users/david/.wine/drive_c/Python25/python.exe"]
    WINE_PY26 = ["/Applications/Darwine/Wine.bundle/Contents/bin/wine",
                 "/Users/david/.wine/drive_c/Python26/python.exe"]
else:
    WINE_PY25 = ["/home/david/.wine/drive_c/Python25/python.exe"]
    WINE_PY26 = ["/home/david/.wine/drive_c/Python26/python.exe"]
WINE_PYS = {'2.6' : WINE_PY26, '2.5': WINE_PY25}
SUPERPACK_BUILD = 'build-superpack'
SUPERPACK_BINDIR = os.path.join(SUPERPACK_BUILD, 'binaries')

# XXX: fix this in a sane way
MPKG_PYTHON = {"25": "/Library/Frameworks/Python.framework/Versions/2.5/bin/python",
        "26": "/Library/Frameworks/Python.framework/Versions/2.6/bin/python"}
# Full path to the *static* gfortran runtime
LIBGFORTRAN_A_PATH = "/usr/local/lib/libgfortran.a"

# Where to put built documentation (where it will picked up for copy to
# binaries)
PDF_DESTDIR = paver.path.path('build') / 'pdf'
HTML_DESTDIR = paver.path.path('build') / 'html'
DOC_ROOT = paver.path.path("doc")
DOC_SRC = DOC_ROOT / "source"
DOC_BLD = DOC_ROOT / "build"
DOC_BLD_LATEX = DOC_BLD / "latex"

# Source of the release notes
RELEASE = 'doc/release/0.8.0-notes.rst'

# Start/end of the log (from git)
LOG_START = 'svn/tags/0.7.0'
LOG_END = 'master'

# Virtualenv bootstrap stuff
BOOTSTRAP_DIR = "bootstrap"
BOOTSTRAP_PYEXEC = "%s/bin/python" % BOOTSTRAP_DIR
BOOTSTRAP_SCRIPT = "%s/bootstrap.py" % BOOTSTRAP_DIR

# Where to put the final installers, as put on sourceforge
RELEASE_DIR = 'release'
INSTALLERS_DIR = os.path.join(RELEASE_DIR, 'installers')


options(sphinx=Bunch(builddir="build", sourcedir="source", docroot='doc'),
        virtualenv=Bunch(script_name=BOOTSTRAP_SCRIPT,
        packages_to_install=["sphinx==0.6.1"]),
        wininst=Bunch(pyver="2.5", scratch=True))

# Bootstrap stuff
@task
def bootstrap():
    """create virtualenv in ./install"""
    install = paver.path.path(BOOTSTRAP_DIR)
    if not install.exists():
        install.mkdir()
    call_task('paver.virtual.bootstrap')
    sh('cd %s; %s bootstrap.py' % (BOOTSTRAP_DIR, sys.executable))

@task
def clean():
    """Remove build, dist, egg-info garbage."""
    d = ['build', 'dist', 'scipy.egg-info']
    for i in d:
        paver.path.path(i).rmtree()

    (paver.path.path('doc') / options.sphinx.builddir).rmtree()

@task
def clean_bootstrap():
    paver.path.path('bootstrap').rmtree()

@task
@needs('clean', 'clean_bootstrap')
def nuke():
    """Remove everything: build dir, installers, bootstrap dirs, etc..."""
    d = [SUPERPACK_BUILD, INSTALLERS_DIR]
    for i in d:
        paver.path.path(i).rmtree()

# NOTES/Changelog stuff
def compute_md5():
    released = paver.path.path(INSTALLERS_DIR).listdir()
    checksums = []
    for f in released:
        m = md5.md5(open(f, 'r').read())
        checksums.append('%s  %s' % (m.hexdigest(), f))

    return checksums

def write_release_task(filename='NOTES.txt'):
    source = paver.path.path(RELEASE)
    target = paver.path.path(filename)
    if target.exists():
        target.remove()
    source.copy(target)
    ftarget = open(str(target), 'a')
    ftarget.writelines("""
Checksums
=========

""")
    ftarget.writelines(['%s\n' % c for c in compute_md5()])

def write_log_task(filename='Changelog'):
    st = subprocess.Popen(
            ['git', 'svn', 'log',  '%s..%s' % (LOG_START, LOG_END)],
            stdout=subprocess.PIPE)

    out = st.communicate()[0]
    a = open(filename, 'w')
    a.writelines(out)
    a.close()

@task
def write_release():
    write_release_task()

@task
def write_log():
    write_log_task()

#------------
# Doc tasks
#------------
@task
def html(options):
    """Build scipy documentation and put it into build/docs"""
    # Don't use paver html target because of scipy bootstrapping problems
    subprocess.check_call(["make", "html"], cwd="doc")
    builtdocs = paver.path.path("doc") / options.sphinx.builddir / "html"
    HTML_DESTDIR.rmtree()
    builtdocs.copytree(HTML_DESTDIR)

@task
def latex():
    """Build scipy documentation in latex format."""
    subprocess.check_call(["make", "latex"], cwd="doc")

@task
@needs('latex')
def pdf():
    def build_pdf():
        subprocess.check_call(["make", "all-pdf"], cwd=str(DOC_BLD_LATEX))
    dry("Build pdf doc", build_pdf)

    PDF_DESTDIR.rmtree()
    PDF_DESTDIR.makedirs()

    user = DOC_BLD_LATEX / "scipy-user.pdf"
    user.copy(PDF_DESTDIR / "userguide.pdf")
    ref =  DOC_BLD_LATEX / "scipy-ref.pdf"
    ref.copy(PDF_DESTDIR / "reference.pdf")

def tarball_name(type='gztar'):
    root = 'scipy-%s' % FULLVERSION
    if type == 'gztar':
        return root + '.tar.gz'
    elif type == 'zip':
        return root + '.zip'
    raise ValueError("Unknown type %s" % type)

@task
def sdist():
    # To be sure to bypass paver when building sdist... paver + scipy.distutils
    # do not play well together.
    sh('python setup.py sdist --formats=gztar,zip')

    # Copy the superpack into installers dir
    if not os.path.exists(INSTALLERS_DIR):
        os.makedirs(INSTALLERS_DIR)

    for t in ['gztar', 'zip']:
        source = os.path.join('dist', tarball_name(t))
        target = os.path.join(INSTALLERS_DIR, tarball_name(t))
        shutil.copy(source, target)

#------------------
# Wine-based builds
#------------------
SSE3_CFG = {'BLAS': r'C:\local\lib\yop\sse3', 'LAPACK': r'C:\local\lib\yop\sse3'}
SSE2_CFG = {'BLAS': r'C:\local\lib\yop\sse2', 'LAPACK': r'C:\local\lib\yop\sse2'}
NOSSE_CFG = {'BLAS': r'C:\local\lib\yop\nosse', 'LAPACK': r'C:\local\lib\yop\nosse'}

SITECFG = {"sse2" : SSE2_CFG, "sse3" : SSE3_CFG, "nosse" : NOSSE_CFG}

def internal_wininst_name(arch, ismsi=False):
    """Return the name of the wininst as it will be inside the superpack (i.e.
    with the arch encoded."""
    if ismsi:
        ext = '.msi'
    else:
        ext = '.exe'
    return "scipy-%s-%s%s" % (FULLVERSION, arch, ext)

def wininst_name(pyver, ismsi=False):
    """Return the name of the installer built by wininst command."""
    # Yeah, the name logic is harcoded in distutils. We have to reproduce it
    # here
    if ismsi:
        ext = '.msi'
    else:
        ext = '.exe'
    name = "scipy-%s.win32-py%s%s" % (FULLVERSION, pyver, ext)
    return name

def bdist_wininst_arch(pyver, arch, scratch=True):
    """Arch specific wininst build."""
    if scratch:
        paver.path.path('build').rmtree()

    if not os.path.exists(SUPERPACK_BINDIR):
        os.makedirs(SUPERPACK_BINDIR)
    _bdist_wininst(pyver, SITECFG[arch])
    source = os.path.join('dist', wininst_name(pyver))
    target = os.path.join(SUPERPACK_BINDIR, internal_wininst_name(arch))
    if os.path.exists(target):
        os.remove(target)
    os.rename(source, target)

def superpack_name(pyver, numver):
    """Return the filename of the superpack installer."""
    return 'scipy-%s-win32-superpack-python%s.exe' % (numver, pyver)

def prepare_nsis_script(pyver, numver):
    if not os.path.exists(SUPERPACK_BUILD):
        os.makedirs(SUPERPACK_BUILD)

    tpl = os.path.join('tools/win32build/nsis_scripts', 'scipy-superinstaller.nsi.in')
    source = open(tpl, 'r')
    target = open(os.path.join(SUPERPACK_BUILD, 'scipy-superinstaller.nsi'), 'w')

    installer_name = superpack_name(pyver, numver)
    cnt = "".join(source.readlines())
    cnt = cnt.replace('@NUMPY_INSTALLER_NAME@', installer_name)
    for arch in ['nosse', 'sse2', 'sse3']:
        cnt = cnt.replace('@%s_BINARY@' % arch.upper(),
                          internal_wininst_name(arch))

    target.write(cnt)

@task
def bdist_wininst_nosse(options):
    """Build the nosse wininst installer."""
    bdist_wininst_arch(options.wininst.pyver, 'nosse', scratch=options.wininst.scratch)

@task
def bdist_wininst_sse2(options):
    """Build the sse2 wininst installer."""
    bdist_wininst_arch(options.wininst.pyver, 'sse2', scratch=options.wininst.scratch)

@task
def bdist_wininst_sse3(options):
    """Build the sse3 wininst installer."""
    bdist_wininst_arch(options.wininst.pyver, 'sse3', scratch=options.wininst.scratch)

@task
@needs('bdist_wininst_nosse', 'bdist_wininst_sse2', 'bdist_wininst_sse3')
def bdist_superpack(options):
    """Build all arch specific wininst installers."""
    prepare_nsis_script(options.wininst.pyver, FULLVERSION)
    subprocess.check_call(['makensis', 'scipy-superinstaller.nsi'],
            cwd=SUPERPACK_BUILD)

    # Copy the superpack into installers dir
    if not os.path.exists(INSTALLERS_DIR):
        os.makedirs(INSTALLERS_DIR)

    source = os.path.join(SUPERPACK_BUILD,
                superpack_name(options.wininst.pyver, FULLVERSION))
    target = os.path.join(INSTALLERS_DIR,
                superpack_name(options.wininst.pyver, FULLVERSION))
    shutil.copy(source, target)

@task
@needs('clean', 'bdist_wininst')
def bdist_wininst_simple():
    """Simple wininst-based installer."""
    _bdist_wininst(pyver=options.wininst.pyver)

def _bdist_wininst(pyver, cfg_env=WINE_SITE_CFG):
    subprocess.call(WINE_PYS[pyver] + ['setup.py', 'build', '-c', 'mingw32', 'bdist_wininst'], env=cfg_env)

#-------------------
# Mac OS X installer
#-------------------
def macosx_version():
    if not sys.platform == 'darwin':
        raise ValueError("Not darwin ??")
    st = subprocess.Popen(["sw_vers"], stdout=subprocess.PIPE)
    out = st.stdout.readlines()
    ver = re.compile("ProductVersion:\s+([0-9]+)\.([0-9]+)\.([0-9]+)")
    for i in out:
        m = ver.match(i)
        if m:
            return m.groups()

def mpkg_name():
    maj, min = macosx_version()[:2]
    pyver = ".".join([str(i) for i in sys.version_info[:2]])
    return "scipy-%s-py%s-macosx%s.%s.mpkg" % \
            (FULLVERSION, pyver, maj, min)

def dmg_name():
    #maj, min = macosx_version()[:2]
    pyver = ".".join([str(i) for i in sys.version_info[:2]])
    #return "scipy-%s-py%s-macosx%s.%s.dmg" % \
    #        (FULLVERSION, pyver, maj, min)
    return "scipy-%s-py%s-python.org.dmg" % \
            (FULLVERSION, pyver)

def prepare_static_gfortran_runtime(d):
    if not os.path.exists(d):
        os.makedirs(d)
    shutil.copy(LIBGFORTRAN_A_PATH, d)

@task
def bdist_mpkg():
    call_task("clean")

    prepare_static_gfortran_runtime("build")
    ldflags = "-undefined dynamic_lookup -bundle -arch i386 -arch ppc -Wl,-search_paths_first"
    ldflags += " -L%s" % os.path.join(os.path.dirname(__file__), "build")
    pyver = "".join([str(i) for i in sys.version_info[:2]])
    sh("LDFLAGS='%s' %s setupegg.py bdist_mpkg" % (ldflags, MPKG_PYTHON[pyver]))

@task
@needs("bdist_mpkg", "pdf")
def dmg():
    pyver = ".".join([str(i) for i in sys.version_info[:2]])

    dmg_n = dmg_name()
    dmg = paver.path.path('scipy-macosx-installer') / dmg_n
    if dmg.exists():
        dmg.remove()

    # Clean the image source
    content = DMG_CONTENT
    content.rmtree()
    content.mkdir()

    # Copy mpkg into image source
    mpkg_n = mpkg_name()
    mpkg_tn = "scipy-%s-py%s.mpkg" % (FULLVERSION, pyver)
    mpkg_source = paver.path.path("dist") / mpkg_n
    mpkg_target = content / mpkg_tn
    mpkg_source.copytree(content / mpkg_tn)

    # Copy docs into image source

    #html_docs = HTML_DESTDIR
    #html_docs.copytree(content / "Documentation" / "html")

    pdf_docs = DMG_CONTENT / "Documentation"
    pdf_docs.rmtree()
    pdf_docs.makedirs()

    user = PDF_DESTDIR / "userguide.pdf"
    user.copy(pdf_docs / "userguide.pdf")
    ref = PDF_DESTDIR / "reference.pdf"
    ref.copy(pdf_docs / "reference.pdf")

    # Build the dmg
    cmd = ["./create-dmg", "--window-size", "500", "500", "--background",
        "art/dmgbackground.png", "--icon-size", "128", "--icon", mpkg_tn,
        "125", "320", "--icon", "Documentation", "375", "320", "--volname", "scipy",
        dmg_n, "./content"]
    subprocess.check_call(cmd, cwd="scipy-macosx-installer")

@task
def simple_dmg():
    # Build the dmg
    image_name = dmg_name()
    image = paver.path.path(image_name)
    image.remove()
    cmd = ["hdiutil", "create", image_name, "-srcdir", str("dist")]
    sh(" ".join(cmd))

@task
def write_note_changelog():
    write_release_task(os.path.join(RELEASE_DIR, 'NOTES.txt'))
    write_log_task(os.path.join(RELEASE_DIR, 'Changelog'))
