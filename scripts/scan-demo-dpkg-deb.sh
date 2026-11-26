#!/bin/sh
# Theos' Darwin default dm.pl preserves builder IDs on this runner. Use the
# native dpkg archive writer and normalize both tar archives, without chowning
# staging paths (in particular the rootless prefix or any host directory).
set -eu
exec dpkg-deb --root-owner-group "$@"
